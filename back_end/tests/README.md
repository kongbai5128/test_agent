# 后端测试说明

本目录用于验证作业要求中的工具集成、工具注册与调度、响应解析、会话隔离、上下文管理、异常处理和工具调用 trace。

## 运行方式

在后端目录执行：

```bash
cd /home/qian/ready_for_job/ms/厦门光辰智能科技-agent简单搭建/back_end
/home/qian/miniconda3/bin/python -m unittest discover -s tests -v
```

可选编译检查：

```bash
/home/qian/miniconda3/bin/python -m compileall app tests
```

## 测试文件

```text
test_required_features.py
```

该文件使用 Python 标准库 `unittest`，不依赖真实 LLM、API Key 或外部网络。测试中通过 `FakeClient` 模拟模型返回：

- 普通文本回复。
- 带 `tool_calls` 的回复。
- LLM 调用异常。
- 长期记忆整合时的 JSON 记忆提取结果。

## 覆盖范围

| 功能要求 | 对应用例 |
|---|---|
| 工具注册信息完整性 | `test_required_tools_are_registered_with_complete_schema` |
| 算术运算器 | `test_calculator_search_and_todo_tools_execute` |
| 信息检索模拟 | `test_calculator_search_and_todo_tools_execute` |
| 待办事项管理 | `test_calculator_search_and_todo_tools_execute` |
| 工具异常处理 | `test_tool_exception_handling_returns_readable_errors` |
| LLM 异常处理 | `test_llm_exception_is_reported_as_error_event` |
| LLM 报错轮次不落盘 | `test_chat_route_does_not_persist_failed_turn` |
| 工具注册与上层调度 | `test_agent_dispatches_registered_tool_and_records_trace` |
| 工具调用 trace / 执行日志 | `test_agent_dispatches_registered_tool_and_records_trace`、`test_tool_follow_up_uses_session_context_and_trace` |
| 响应解析：推理过程 | `test_agent_dispatches_registered_tool_and_records_trace` |
| 响应解析：工具调用指令 | `test_agent_dispatches_registered_tool_and_records_trace` |
| 响应解析：最终回复 | `test_agent_dispatches_registered_tool_and_records_trace` |
| 无法解析时返回原始内容 | `test_plain_model_response_is_returned_as_original_content` |
| 多会话隔离与恢复 | `test_multiple_sessions_are_isolated_and_restorable` |
| 上下文超阈值按 user 轮次截断 | `test_context_threshold_drops_oldest_records` |
| 上下文压缩后的工具消息合法性 | `test_context_compression_removes_orphan_tool_results` |
| 超过 20 轮强制压缩 | `test_chat_route_forces_context_compression_when_round_limit_reached` |
| 纯文字追问上下文关联 | `test_text_follow_up_keeps_previous_context` |
| 带工具追问上下文关联 | `test_tool_follow_up_uses_session_context_and_trace` |
| 自动长期记忆整合 | `test_session_consolidation_saves_relevant_long_term_memory` |

## 重点说明

### 基本异常处理

测试覆盖三类异常：

- 未知工具：`execute("missing_tool", {})` 应返回可读错误。
- 工具参数/执行错误：如计算器除零、搜索空关键词。
- LLM 调用异常：Fake LLM 抛出 `Connection error` 后，Agent 应返回 `error` 事件和 `done` 事件。
- 路由层 LLM 调用异常：失败轮次不会写入 `raw_messages`、`display_messages` 和 `tool_traces`。

### 工具调用 trace

Agent 执行工具后会记录：

- `iteration`
- `tool`
- `params`
- `result`
- `elapsed_ms`

测试会断言 `calculator` 和连续 `todo` 工具调用都写入 trace。

### 会话隔离

测试创建两个 session：

- 窗口 1：写入待办和工具 trace。
- 窗口 2：写入周报上下文。

重新加载 `SessionStore` 后验证两个窗口的 `raw_messages`、`display_messages`、`todos`、`tool_traces` 互不污染。

### 上下文管理

测试分两类：

- 构造超长上下文，验证 `compress()` 会按最近 user 轮次保留上下文，并注入 `Context 自动压缩` 说明。
- 构造压缩后残留孤立 `tool` 消息的历史，验证发送给模型前会清理成合法消息序列。
- 构造已有 `MAX_ROUNDS=20` 轮用户消息的 session，调用 `chat_stream()` 后验证旧上下文被强制裁剪。

### 长期记忆整合

测试用 fake LLM 返回结构化 JSON，验证：

- 后端能从 session 历史中构造整合 prompt。
- `consolidate_sessions_to_memory()` 能保存 `auto_consolidate` 来源的长期记忆。
- 保存后的记忆能通过 `build_memory_block()` 注入后续 system prompt。
- `_index.json` 会记录整合后的记忆数量和会话数量。

## 当前验证结果

最近一次验证：

```text
Ran 14 tests
OK
```
