# AI Prompt 与问题解决记录

## 一、原始任务 Prompt

当前项目需要满足以下后端与测试要求：

1. 基本异常处理。
2. 工具调用 trace 或执行日志。
3. 工具集成至少三个：
   - 算术运算器：支持四则运算。
   - 信息检索模拟：返回预设数据。
   - 待办事项管理或天气信息查询。
4. 工具注册与调度：
   - 每个工具需注册功能名称、用途描述、参数格式说明。
   - 上层决策模块根据工具注册信息自主选择调用哪个工具。
5. 响应解析：
   - 从模型返回内容中提取推理过程、工具调用指令、最终回复。
   - 若无法解析，则直接返回原始内容。
6. 会话隔离管理：
   - 多个窗口/会话的历史、上下文、状态互不干扰。
   - 用户切回任一窗口时能恢复该窗口状态。
7. 上下文有效管理：
   - 设置最大对话轮次，超出后自动丢弃最早记录。
   - 保持完整对话历史，支持连续追问。
   - 覆盖纯文字追问和涉及工具调用的追问。
8. 针对上述功能构建测试用例。

## 二、现状分析

项目已有以下核心能力：

- `app/tools/registry.py`：工具注册表，包含 `ToolSpec`、`register()`、`all_tools()`、`execute()`、`to_openai_tools()`。
- `app/tools/calculator.py`：算术工具。
- `app/tools/search.py`：模拟检索工具。
- `app/tools/todo.py`：基于 session 的待办工具。
- `app/agent/loop.py`：Agent 循环，支持 OpenAI function calling、工具调度、SSE 事件、trace 记录。
- `app/sessions/store.py`：会话 JSON 持久化，包含 `raw_messages`、`display_messages`、`todos`、`documents`、`tool_traces`。
- `app/context/manager.py`：上下文压缩与轮次统计。
- `app/api/routes.py:171`：在聊天入口中判断是否超轮次并调用 `ctx_manager.compress()`。

## 三、问题与处理

### 1. 超过 20 轮强制压缩

`routes.py` 第 171 行已有逻辑：

```python
if ctx_manager.count_user_turns(session.raw_messages) >= ctx_manager.MAX_ROUNDS:
    session.raw_messages = ctx_manager.compress(..., force=True)
```

为避免超过 20 轮时只是“尝试压缩”但短上下文没有变化，新增 `compress(force=True)`：

- 默认 `force=False` 时，仍保持原逻辑：只有超阈值才完整截断。
- `force=True` 时，直接保留最近 `KEEP_RECENT_MESSAGES` 条并注入压缩说明。
- `routes.py:171` 的超轮次分支使用 `force=True`，确保超过 20 轮后有实际压缩效果。

处理方式：

- 小改 `app/context/manager.py`：为 `compress()` 增加 `force` 参数。
- 小改 `app/api/routes.py`：超轮次分支传入 `force=True`。
- 测试中构造已有 `MAX_ROUNDS` 个用户轮次的 session，验证调用 `chat_stream()` 后上下文被强制压缩。
- 另外单独构造超长上下文，验证 `compress()` 默认行为在超阈值时会丢弃最早记录。

### 2. 测试不依赖真实 LLM

为了让测试稳定、可重复、不依赖 API Key，测试中使用 `FakeClient` 模拟 OpenAI client：

- 模拟普通最终回复。
- 模拟带 `tool_calls` 的模型响应。
- 模拟 LLM 抛异常。

这样可以验证上层 Agent 调度、响应事件解析、工具执行和 trace，而不需要真实网络调用。

## 四、测试文件

新增：

```text
back_end/tests/test_required_features.py
```

运行命令：

```bash
cd /home/qian/ready_for_job/ms/厦门光辰智能科技-agent简单搭建/back_end
/home/qian/miniconda3/bin/python -m unittest discover -s tests -v
```

## 五、测试覆盖矩阵

| 要求 | 覆盖用例 |
|------|----------|
| 工具注册信息完整性 | `test_required_tools_are_registered_with_complete_schema` |
| 算术工具 | `test_calculator_search_and_todo_tools_execute` |
| 信息检索模拟 | `test_calculator_search_and_todo_tools_execute` |
| 待办事项管理 | `test_calculator_search_and_todo_tools_execute` |
| 基本异常处理 | `test_tool_exception_handling_returns_readable_errors`、`test_llm_exception_is_reported_as_error_event` |
| 工具注册与调度 | `test_agent_dispatches_registered_tool_and_records_trace` |
| 工具调用 trace | `test_agent_dispatches_registered_tool_and_records_trace`、`test_tool_follow_up_uses_session_context_and_trace` |
| 响应解析：推理过程 | `test_agent_dispatches_registered_tool_and_records_trace` |
| 响应解析：工具调用指令 | `test_agent_dispatches_registered_tool_and_records_trace` |
| 响应解析：最终回复 | `test_agent_dispatches_registered_tool_and_records_trace` |
| 无法解析时返回原始内容 | `test_plain_model_response_is_returned_as_original_content` |
| 多会话隔离 | `test_multiple_sessions_are_isolated_and_restorable` |
| 会话状态恢复 | `test_multiple_sessions_are_isolated_and_restorable` |
| 超轮次强制压缩 | `test_chat_route_forces_context_compression_when_round_limit_reached` |
| 超阈值上下文截断 | `test_context_threshold_drops_oldest_records` |
| 纯文字追问 | `test_text_follow_up_keeps_previous_context` |
| 工具型追问 | `test_tool_follow_up_uses_session_context_and_trace` |

## 六、验证结果

执行结果：

```text
Ran 11 tests
OK
```

同时执行：

```bash
/home/qian/miniconda3/bin/python -m compileall app tests
```

结果通过。

## 七、改动原则

本次尽量减少业务代码更新：

- 未重构 Agent 主循环。
- 未新增测试框架依赖，使用 Python 标准库 `unittest`。
- 未接入真实 LLM 或真实网络天气接口作为测试前提。
- `context/manager.py` 仅新增 `force` 参数，默认行为不变；`routes.py:171` 超轮次分支使用 `force=True`，确保超过 20 轮后强制裁剪旧上下文。
