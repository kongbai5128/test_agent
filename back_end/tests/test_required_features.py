from __future__ import annotations

import asyncio
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import app.tools  # noqa: F401 触发工具注册
from app.api import routes
from app.agent.loop import ToolContext, run_agent_loop
from app.context import manager as ctx_manager
from app.memory import (
    MemoryStore,
    build_memory_block,
    consolidate_sessions_to_memory,
    should_consolidate_sessions,
)
from app.sessions.store import SessionStore
from app.tools import all_tools, execute


class FakeFunction:
    def __init__(self, name: str, arguments: dict | str) -> None:
        self.name = name
        self.arguments = (
            json.dumps(arguments, ensure_ascii=False)
            if isinstance(arguments, dict)
            else arguments
        )


class FakeToolCall:
    def __init__(self, name: str, arguments: dict | str, call_id: str = "call-1") -> None:
        self.id = call_id
        self.function = FakeFunction(name, arguments)


class FakeMessage:
    def __init__(self, content: str = "", tool_calls: list[FakeToolCall] | None = None) -> None:
        self.content = content
        self.tool_calls = tool_calls or []


class FakeResponse:
    def __init__(self, content: str = "", tool_calls: list[FakeToolCall] | None = None) -> None:
        finish_reason = "tool_calls" if tool_calls else "stop"
        choice = SimpleNamespace(
            finish_reason=finish_reason,
            message=FakeMessage(content, tool_calls),
        )
        self.choices = [choice]


class FakeCompletions:
    def __init__(self, responses: list[FakeResponse | Exception]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> FakeResponse:
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeClient:
    def __init__(self, responses: list[FakeResponse | Exception]) -> None:
        self.chat = SimpleNamespace(completions=FakeCompletions(responses))


class EmptyMemoryStore:
    def find_relevant(self, query: str, top_k: int = 3) -> list[Any]:
        return []

    def load_all(self) -> list[Any]:
        return []


async def collect_agent_events(
    *,
    client: FakeClient,
    session_id: str = "session-a",
    user_input: str = "测试输入",
    raw_messages: list[dict] | None = None,
    session_store: SessionStore | None = None,
    traces: list[dict] | None = None,
) -> tuple[list[dict], list[dict], list[dict]]:
    if raw_messages is None:
        raw_messages = []
    if traces is None:
        traces = []
    if session_store is None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SessionStore(Path(tmp) / "sessions")
            session = store.create("默认会话")
            return await collect_agent_events(
                client=client,
                session_id=session.id,
                user_input=user_input,
                raw_messages=raw_messages,
                session_store=store,
                traces=traces,
            )

    events: list[dict] = []
    async for event in run_agent_loop(
        session_id=session_id,
        user_input=user_input,
        raw_messages=raw_messages,
        system_prompt="测试系统提示",
        client=client,  # type: ignore[arg-type]
        model="fake-model",
        max_iterations=5,
        session_store=session_store,
        memory_store=None,
        document_store=None,
        tool_traces=traces,
    ):
        events.append(event)
    return events, raw_messages, traces


async def collect_stream_text(response: Any) -> str:
    chunks: list[str] = []
    async for chunk in response.body_iterator:
        if isinstance(chunk, bytes):
            chunks.append(chunk.decode("utf-8"))
        else:
            chunks.append(str(chunk))
    return "".join(chunks)


class ToolRegistrationAndExecutionTests(unittest.TestCase):
    def test_required_tools_are_registered_with_complete_schema(self) -> None:
        required = {"calculator", "search", "todo"}
        specs = {tool.name: tool for tool in all_tools()}

        self.assertTrue(required.issubset(specs))
        for name in required:
            spec = specs[name]
            self.assertTrue(spec.name)
            self.assertTrue(spec.description)
            self.assertIsInstance(spec.parameters, dict)
            self.assertEqual(spec.parameters.get("type"), "object")
            self.assertIsInstance(spec.parameters.get("properties"), dict)
            self.assertIsInstance(spec.parameters.get("required", []), list)
            for param_name, schema in spec.parameters["properties"].items():
                self.assertTrue(param_name)
                self.assertIn("description", schema)
                self.assertTrue("type" in schema or "enum" in schema)

        self.assertEqual(
            specs["search"].parameters["properties"]["num_results"].get("default"),
            3,
        )

    def test_calculator_search_and_todo_tools_execute(self) -> None:
        calc = execute("calculator", {"expression": "(8 + 4) * 3 / 2 - 5"})
        self.assertIn("= 13", calc)

        search = execute("search", {"query": "FastAPI", "num_results": 1})
        self.assertIn("FastAPI 官方文档", search)

        with tempfile.TemporaryDirectory() as tmp:
            store = SessionStore(Path(tmp) / "sessions")
            session = store.create("待办会话")
            ctx = ToolContext(session_id=session.id, session_store=store)
            result = execute("todo", {"action": "add", "content": "写周报"}, ctx)
            self.assertIn("已添加待办", result)
            self.assertEqual(store.get(session.id).todos[0]["content"], "写周报")  # type: ignore[union-attr]

    def test_tool_exception_handling_returns_readable_errors(self) -> None:
        self.assertIn("未知工具", execute("missing_tool", {}))
        self.assertIn("除数不能为零", execute("calculator", {"expression": "1 / 0"}))
        self.assertIn("不能为空", execute("search", {"query": ""}))


class AgentLoopParsingAndTraceTests(unittest.IsolatedAsyncioTestCase):
    async def test_agent_dispatches_registered_tool_and_records_trace(self) -> None:
        client = FakeClient(
            [
                FakeResponse(
                    "我需要先计算。",
                    [FakeToolCall("calculator", {"expression": "2 + 3 * 4"})],
                ),
                FakeResponse("最终结果是 14。"),
            ]
        )

        events, raw_messages, traces = await collect_agent_events(client=client)

        self.assertIn({"type": "thinking", "content": "我需要先计算。"}, events)
        self.assertIn(
            {"type": "tool_start", "tool": "calculator", "params": {"expression": "2 + 3 * 4"}},
            events,
        )
        self.assertTrue(any(e["type"] == "tool_result" and "14" in e["result"] for e in events))
        self.assertEqual(events[-2], {"type": "message", "content": "最终结果是 14。"})
        self.assertEqual(events[-1], {"type": "done"})
        self.assertEqual(traces[0]["tool"], "calculator")
        self.assertIn("14", traces[0]["result"])
        self.assertEqual(raw_messages[-1]["content"], "最终结果是 14。")

        first_call = client.chat.completions.calls[0]
        tool_names = {item["function"]["name"] for item in first_call["tools"]}
        self.assertIn("calculator", tool_names)
        self.assertEqual(first_call["tool_choice"], "auto")

    async def test_plain_model_response_is_returned_as_original_content(self) -> None:
        original = "这是普通回复：## 标题\n| 项目 | 数据 |"
        client = FakeClient([FakeResponse(original)])

        events, _, traces = await collect_agent_events(client=client)

        self.assertEqual(events, [{"type": "message", "content": original}, {"type": "done"}])
        self.assertEqual(traces, [])

    async def test_llm_exception_is_reported_as_error_event(self) -> None:
        client = FakeClient([RuntimeError("Connection error")])

        with self.assertLogs("app.agent.loop", level="ERROR") as logs:
            events, _, traces = await collect_agent_events(client=client)

        self.assertEqual(events[-1], {"type": "done"})
        self.assertEqual(events[0]["type"], "error")
        self.assertIn("LLM 调用失败", events[0]["message"])
        self.assertTrue(any("LLM API error" in message for message in logs.output))
        self.assertEqual(traces, [])

    async def test_text_follow_up_keeps_previous_context(self) -> None:
        raw_messages: list[dict] = []
        first_client = FakeClient([FakeResponse("周报主题是项目进展。")])
        second_client = FakeClient([FakeResponse("继续上文，补充风险。")])

        await collect_agent_events(
            client=first_client,
            user_input="帮我写周报",
            raw_messages=raw_messages,
        )
        events, _, _ = await collect_agent_events(
            client=second_client,
            user_input="补充风险",
            raw_messages=raw_messages,
        )

        sent_messages = second_client.chat.completions.calls[0]["messages"]
        contents = "\n".join(str(item.get("content", "")) for item in sent_messages)
        self.assertIn("帮我写周报", contents)
        self.assertIn("周报主题是项目进展。", contents)
        self.assertEqual(events[-2]["content"], "继续上文，补充风险。")

    async def test_tool_follow_up_uses_session_context_and_trace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SessionStore(Path(tmp) / "sessions")
            session = store.create("工具追问")
            raw_messages: list[dict] = []
            traces: list[dict] = []

            first_client = FakeClient(
                [
                    FakeResponse(
                        "先添加待办。",
                        [FakeToolCall("todo", {"action": "add", "content": "写周报"})],
                    ),
                    FakeResponse("已记录。"),
                ]
            )
            second_client = FakeClient(
                [
                    FakeResponse(
                        "继续查看刚才的待办。",
                        [FakeToolCall("todo", {"action": "list"})],
                    ),
                    FakeResponse("刚才的待办是写周报。"),
                ]
            )

            await collect_agent_events(
                client=first_client,
                session_id=session.id,
                user_input="帮我记一个待办：写周报",
                raw_messages=raw_messages,
                session_store=store,
                traces=traces,
            )
            events, _, traces = await collect_agent_events(
                client=second_client,
                session_id=session.id,
                user_input="列出刚才的待办",
                raw_messages=raw_messages,
                session_store=store,
                traces=traces,
            )

            self.assertEqual([trace["tool"] for trace in traces], ["todo", "todo"])
            self.assertIn("写周报", traces[-1]["result"])
            self.assertEqual(store.get(session.id).todos[0]["content"], "写周报")  # type: ignore[union-attr]
            self.assertEqual(events[-2]["content"], "刚才的待办是写周报。")


class SessionAndContextManagementTests(unittest.TestCase):
    def test_multiple_sessions_are_isolated_and_restorable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SessionStore(Path(tmp) / "sessions")
            window_one = store.create("窗口1")
            window_two = store.create("窗口2")

            window_one.raw_messages.append({"role": "user", "content": "查天气并记待办"})
            todo_result = execute(
                "todo",
                {"action": "add", "content": "带伞"},
                ToolContext(session_id=window_one.id, session_store=store),
            )
            self.assertIn("已添加待办", todo_result)
            window_one = store.get(window_one.id)
            self.assertIsNotNone(window_one)
            window_one.tool_traces.append({"tool": "todo", "params": {"action": "add"}})
            store.save(window_one)

            window_two.raw_messages.append({"role": "user", "content": "写周报"})
            window_two.display_messages.append(
                {
                    "id": "msg-b",
                    "role": "assistant",
                    "content": "周报草稿",
                    "thinking": None,
                    "tool_calls": [],
                }
            )
            store.save(window_two)

            reloaded = SessionStore(Path(tmp) / "sessions")
            restored_one = reloaded.get(window_one.id)
            restored_two = reloaded.get(window_two.id)

            self.assertEqual(restored_one.todos[0]["content"], "带伞")  # type: ignore[union-attr]
            self.assertEqual(restored_one.tool_traces[0]["tool"], "todo")  # type: ignore[union-attr]
            self.assertEqual(restored_two.raw_messages[0]["content"], "写周报")  # type: ignore[union-attr]
            self.assertEqual(restored_two.display_messages[0]["content"], "周报草稿")  # type: ignore[union-attr]
            self.assertEqual(restored_two.todos, [])  # type: ignore[union-attr]

    def test_context_threshold_drops_oldest_records(self) -> None:
        messages: list[dict] = []
        for i in range(ctx_manager.KEEP_RECENT_USER_TURNS + 4):
            messages.append({"role": "user", "content": f"user-{i}" + "x" * 4000})
            messages.append({"role": "assistant", "content": f"assistant-{i}"})

        compressed = ctx_manager.compress(messages, "system")
        contents = "\n".join(str(item.get("content", "")) for item in compressed)

        self.assertLess(len(compressed), len(messages))
        self.assertEqual(compressed[0]["role"], "system")
        self.assertIn("Context 自动压缩", compressed[0]["content"])
        self.assertNotIn("user-0", contents)
        self.assertEqual(
            ctx_manager.count_user_turns(compressed),
            ctx_manager.KEEP_RECENT_USER_TURNS,
        )
        self.assertIn(f"user-{ctx_manager.KEEP_RECENT_USER_TURNS + 3}", contents)

    def test_context_compression_removes_orphan_tool_results(self) -> None:
        messages = [
            {
                "role": "assistant",
                "content": "先读取文档。",
                "tool_calls": [
                    {
                        "id": "call-lost",
                        "type": "function",
                        "function": {
                            "name": "read_docs",
                            "arguments": "{}",
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call-lost",
                "content": "这条工具结果被截断后会变成孤立 tool。",
            },
        ]
        for i in range(ctx_manager.KEEP_RECENT_USER_TURNS + 1):
            messages.append({"role": "user", "content": f"追问-{i}"})

        compressed = ctx_manager.compress(messages, "system", force=True)

        self.assertEqual(compressed[0]["role"], "system")
        self.assertNotEqual(compressed[1]["role"], "tool")
        self.assertFalse(_has_orphan_tool_message(compressed))

    def test_chat_route_forces_context_compression_when_round_limit_reached(self) -> None:
        async def run_case() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                store = SessionStore(Path(tmp) / "sessions")
                session = store.create("超轮次会话")
                for i in range(ctx_manager.MAX_ROUNDS):
                    session.raw_messages.append({"role": "user", "content": f"user-{i}"})
                    session.raw_messages.append({"role": "assistant", "content": f"assistant-{i}"})
                store.save(session)

                await routes.chat_stream(
                    session_id=session.id,
                    body=routes.ChatRequest(message="继续刚才的话题"),
                    store=store,
                    client=FakeClient([FakeResponse("不会真正消费")]),  # type: ignore[arg-type]
                    model="fake-model",
                    max_iter=1,
                    memory_store=EmptyMemoryStore(),  # type: ignore[arg-type]
                    document_store=SimpleNamespace(),  # type: ignore[arg-type]
                )

                contents = "\n".join(
                    str(item.get("content", "")) for item in session.raw_messages
                )
                self.assertLess(len(session.raw_messages), ctx_manager.MAX_ROUNDS * 2)
                self.assertEqual(session.raw_messages[0]["role"], "system")
                self.assertIn("Context 自动压缩", session.raw_messages[0]["content"])
                self.assertEqual(
                    ctx_manager.count_user_turns(session.raw_messages),
                    ctx_manager.KEEP_RECENT_USER_TURNS,
                )
                self.assertNotIn("user-0", contents)
                self.assertIn(f"user-{ctx_manager.MAX_ROUNDS - 1}", contents)

        asyncio.run(run_case())

    def test_chat_route_does_not_persist_failed_turn(self) -> None:
        async def run_case() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                store = SessionStore(Path(tmp) / "sessions")
                session = store.create("失败回滚")
                session.raw_messages.append({"role": "user", "content": "已有历史"})
                session.display_messages.append(
                    {
                        "id": "msg-old",
                        "role": "user",
                        "content": "已有历史",
                        "thinking": None,
                        "tool_calls": [],
                    }
                )
                store.save(session)

                before_raw = copy.deepcopy(session.raw_messages)
                before_display = copy.deepcopy(session.display_messages)
                before_traces = copy.deepcopy(session.tool_traces)

                response = await routes.chat_stream(
                    session_id=session.id,
                    body=routes.ChatRequest(message="这一轮会失败"),
                    store=store,
                    client=FakeClient([RuntimeError("Connection error")]),  # type: ignore[arg-type]
                    model="fake-model",
                    max_iter=1,
                    memory_store=EmptyMemoryStore(),  # type: ignore[arg-type]
                    document_store=SimpleNamespace(),  # type: ignore[arg-type]
                )
                with self.assertLogs("app.agent.loop", level="ERROR"):
                    stream_text = await collect_stream_text(response)

                self.assertIn("LLM 调用失败", stream_text)
                self.assertEqual(session.raw_messages, before_raw)
                self.assertEqual(session.display_messages, before_display)
                self.assertEqual(session.tool_traces, before_traces)

        asyncio.run(run_case())


def _has_orphan_tool_message(messages: list[dict]) -> bool:
    expected_ids: set[str] = set()
    for message in messages:
        role = message.get("role")
        if role == "assistant":
            expected_ids = {
                str(call.get("id"))
                for call in message.get("tool_calls", [])
                if isinstance(call, dict) and call.get("id")
            }
            continue
        if role == "tool":
            tool_call_id = str(message.get("tool_call_id", ""))
            if tool_call_id not in expected_ids:
                return True
            expected_ids.discard(tool_call_id)
            continue
        expected_ids = set()
    return False


class LongTermMemoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_session_consolidation_saves_relevant_long_term_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            session_store = SessionStore(Path(tmp) / "sessions")
            memory_store = MemoryStore(Path(tmp) / "memory")
            session = session_store.create("偏好会话")
            session.raw_messages.extend(
                [
                    {
                        "role": "user",
                        "content": "以后回答我尽量简洁，不要重复解释。",
                    },
                    {
                        "role": "assistant",
                        "content": "好的，我会保持简洁。",
                    },
                ]
            )
            session_store.save(session)

            self.assertTrue(should_consolidate_sessions(session_store, memory_store))

            client = FakeClient(
                [
                    FakeResponse(
                        json.dumps(
                            {
                                "memories": [
                                    {
                                        "type": "user",
                                        "content": "用户偏好回答尽量简洁，不喜欢重复解释。",
                                        "tags": ["偏好", "回复风格"],
                                        "importance": 4,
                                    }
                                ]
                            },
                            ensure_ascii=False,
                        )
                    )
                ]
            )

            result = await consolidate_sessions_to_memory(
                client=client,
                model="fake-model",
                session_store=session_store,
                memory_store=memory_store,
                force=True,
            )

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["created"], 1)
            memories = memory_store.load_all()
            self.assertEqual(len(memories), 1)
            self.assertEqual(memories[0].type, "user")
            self.assertEqual(memories[0].source_session, "auto_consolidate")
            self.assertIn("尽量简洁", memories[0].content)

            memory_block = build_memory_block("简洁", memory_store, top_k=3)
            self.assertIn("[相关长期记忆]", memory_block)
            self.assertIn("用户偏好回答尽量简洁", memory_block)

            index = memory_store.get_index()
            self.assertEqual(index.total_memories, 1)
            self.assertEqual(index.session_count_at_last_consolidation, 1)
            self.assertFalse(should_consolidate_sessions(session_store, memory_store))

            sent_messages = client.chat.completions.calls[0]["messages"]
            prompt_text = "\n".join(str(item.get("content", "")) for item in sent_messages)
            self.assertIn("偏好会话", prompt_text)
            self.assertIn("以后回答我尽量简洁", prompt_text)


if __name__ == "__main__":
    unittest.main()
