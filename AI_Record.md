# AI 问题解决记录

## 1. LLM 调用失败 / 网络连接问题

**用户：** 出现 `LLM 调用失败：Connection error`，问是不是网络问题。

**AI：** 判断这是 LLM API 调用阶段失败，可能是 API Key、base_url、网络、代理或服务商连接异常，不是业务代码本身。

**用户：** 要求处理代理问题，并提到想改 `.bashrc`，用 `clash no` 启动代理、`clash off` 关闭代理，而且默认关闭。

**AI：** 解释可以通过 shell alias/function 管理代理环境变量，默认不设置代理，需要时手动开启。

**方案：** 后端保留 LLM 异常处理；本地环境层面按用户建议用命令开关代理，避免默认代理影响所有请求。

---

## 2. `session_id` 从哪里来

**用户：** 问 `session = _get_or_404(store, session_id)` 里的 `session_id` 怎么获得。

**AI：** 解释 `session_id` 来自 FastAPI 路由路径参数，比如 `/api/sessions/{session_id}/chat/stream`。

**用户：** 继续追问前端如何知道它。

**AI：** 说明前端创建或选择会话后，会拿到 session 的 `id`，之后请求消息、上传文档、发送聊天都把这个 id 放进 URL。

**方案：** 前端先调用 `/api/sessions` 创建/获取会话，再用该 `id` 调用后续接口。

---

## 3. `search mock` 是什么意思

**用户：** 问 `search（可 mock）` 是不是本地假逻辑。

**AI：** 确认 mock 就是本地模拟，不接真实搜索引擎，返回预设数据。

**方案：** 保留 `search.py` 的本地模拟检索；测试里用固定 query 验证返回预设结果，满足“信息检索模拟”要求。

---

## 4. 加入长期记忆 memory 功能

**用户：** 要求参考 `ref/shell-agent/src/memory` 和 `memory_tool.py`，给后端加入 memory 功能。

**AI：** 分析参考项目的 `MemoryStore`、`memory_save`、记忆类型、相关记忆注入 system prompt 的做法。

**用户：** 希望尽量贴近参考代码，同时适配当前后端。

**AI：** 实现 `app/memory`、`app/tools/memory.py`、记忆 API、system prompt 注入。

**方案：** 长期记忆保存到 `back_end/data/memory`；LLM 可调用 `memory_save`；后续对话按相关性注入 `[相关长期记忆]`。

---

## 5. `read_docs` 读取 PDF / Word / TXT

**用户：** 指出 `read_doc` 应该是读取 PDF、Word、TXT 的功能，当前 `read_docs.py` 需要大改。

**AI：** 确认 `read_docs` 不应只是简单路径读取，而应面向上传文档读取内容。

**用户：** 提出方案：文件应由前端提供，后端临时保存到 `back_end/data/doc` 再读取。

**AI：** 认可该方案更合理，因为浏览器本地文件必须通过上传进入后端，后端才能解析。

**方案：** 实现文档上传、后端落盘、文档状态、`document_id` 读取；PDF/Word/TXT/Markdown 等由 `read_docs` 统一处理。

---

## 6. 前端文件上传和发送按钮问题

**用户：** 要求前端文件获取过程仿照豆包等软件。

**AI：** 实现文件上传状态展示。

**用户：** 说文件已经后端 `201 Created`，也下载到 `data/doc` 了，但前端卡住，已就绪后仍然不能发送。

**用户：** 要求详细列出“上传文件到回答问题”的整体流程。

**AI：** 解释流程：

1. 前端选择文件。
2. 创建 attachment 状态。
3. 使用 XHR 上传。
4. 后端保存和解析。
5. 后端返回文档 metadata。
6. 前端标记 ready。
7. 发送时携带 `document_ids`。
8. 后端注入文档信息。
9. LLM 根据需要调用 `read_docs`。

**用户：** 说明前端一直显示 0%，但只要在输入框输入文字，文件会瞬间显示已就绪。

**AI：** 定位为 Vue 响应式对象更新问题。原来是：

```js
attachments.value.push(item)
uploadItem(item)
```

这样继续修改的是原始对象，computed 可能感知不到 `uploading -> ready`，所以 `hasBlockingUpload` 和 `canSend` 没重新计算。

**AI：** 按用户场景改成：

```js
attachments.value.push(item)
uploadItem(attachments.value[attachments.value.length - 1])
```

让上传状态更新作用在 Vue 响应式代理对象上。

**方案：** 发送按钮条件跟随 ready 状态重新计算；上传成功后不用输入文字也能恢复发送。

---

## 7. Markdown 表格乱格式

**用户：** 说 AI 回复里 `## xxx`、Markdown 表格没有被渲染，显示成乱格式。

**AI：** 判断是前端展示层没有做 Markdown 渲染，而是纯文本展示。

**方案：** 消息内容走 Markdown renderer，支持标题、表格等格式；不是后端模型输出的问题。

---

## 8. 作业要求测试用例构建

**用户：** 要求覆盖工具集成、工具注册、响应解析、会话隔离、上下文管理、异常处理、trace、测试说明、AI Prompt 记录。

**用户：** 还指出 `routes.py` 第 171 行已有超轮次压缩，要求尽量少改代码。

**AI：** 补 `back_end/tests/test_required_features.py`、`back_end/tests/README.md`，并把 AI Prompt 与问题解决记录放到 `work_space`。

**方案：** 使用 Python 标准库 `unittest`，用 fake LLM 测工具、调度、解析、多会话、上下文、异常、trace，避免真实 API 和网络依赖。

---

## 9. 超过 20 轮强制压缩

**用户：** 先说“不用改 Step 2，只保留最近 KEEP_RECENT_MESSAGES 条 + 注入压缩说明更合理”。

**用户：** 后来改成“超过 20 次强行压缩吧，要不然没区别了”。

**AI：** 给 `compress()` 加 `force=True`，在超过轮次时强制压缩。

**用户：** 后续又指出这里的 20 应该是 20 条 user 对话，不是 20 个 list 对象。

**AI：** 确认触发条件已经用 `count_user_turns()` 统计 user，但裁剪窗口仍按 list 对象。

**方案：** 改为 `MAX_ROUNDS = 20` 表示 20 个用户轮次；压缩后用 `KEEP_RECENT_USER_TURNS` 保留最近 N 个 user 轮次及其后续 assistant/tool 消息。

---

## 10. `attached_docs` 为空为什么还 `_infer_recent_documents`

**用户：** 问 `if not attached_docs: attached_docs = _infer_recent_documents(...)`，为空不就是没上传文档吗？

**AI：** 解释 `attached_docs` 为空只代表本次请求没显式传 `document_ids`，不代表 session 没有已上传文档。

**用户：** 关心为什么要重新赋值。

**AI：** 说明这是为了支持用户上传完文档后直接说“总结这篇文档”，即使前端没传 id，后端也能推断最近 ready 文档。

**方案：** 保留 `_infer_recent_documents()`，作为文档追问的容错体验。

---

## 11. 基本异常处理和工具 trace 在哪里体现

**用户：** 问“基本异常处理、工具调用 trace 或执行日志”在哪里体现。

**AI：** 指出三层体现：工具执行错误返回可读错误；LLM 调用异常返回 `error` SSE；工具调用写入 `session.tool_traces`。

**用户：** 要求测试说明写进 `back_end/tests`。

**AI：** 补 `README.md`，列出每个功能对应测试。

**方案：** 测试覆盖未知工具、计算器除零、搜索空 query、LLM 异常、工具 trace 写入与读取。

---

## 12. 测试是否使用真实大模型

**用户：** 问测试里有没有使用大模型，比如长期记忆测试。

**AI：** 说明当前测试不调用真实大模型，使用 `FakeClient/FakeResponse/FakeToolCall`。

**用户：** 问长期记忆是否测了。

**AI：** 补长期记忆测试，用 fake LLM 返回结构化 JSON，验证保存、检索、注入 prompt。

**方案：** 默认单测保持稳定、无网络、无 API Key；真实 LLM 可另做可选 integration test。

---

## 13. `data/memory` 为空

**用户：** 问为什么 `back_end/data/memory` 什么都没有，而 `data/sessions` 有内容。

**AI：** 解释 session 是每轮对话自动保存；memory 只有调用 `memory_save` 或 `/api/memories` 才会写。

**用户：** 想加入“自动把所有 session 总结成长期记忆”的逻辑，并要求参考 `ref/shell-agent`。

**AI：** 参考 Dream 思路，实现轻量 session consolidation。

**方案：** 新增 `consolidate_sessions_to_memory()`；聊天结束后后台尝试整合；也提供 `POST /api/memories/consolidate?force=true` 手动触发，生成 `mem-xxxx.json`。

---

## 14. DeepSeek 报 `tool` 消息不合法

**用户：** 报错 `Messages with role 'tool' must be a response to a preceding message with 'tool_calls'`。

**AI：** 定位为压缩历史时裁掉了 assistant `tool_calls`，却留下了孤立的 `tool` 消息。

**用户：** 同时要求“20 条压缩改成与 20 条 user 对话的压缩，而不是单纯 20 个 list 对象”。

**AI：** 新增 `sanitize_chat_messages()`，压缩后和发送前清理不合法 tool 消息链。

**AI：** 同时把压缩窗口改成按 user 轮次裁剪，避免工具调用产生多条 assistant/tool 后扰乱计数。

**方案：** 旧 session 下次发送前会自动清理孤立 tool；压缩按 user 轮次执行；补 orphan tool 回归测试。

---

## 15. LLM 报错的对话不应保存和展示

**用户：** 指出报错的对话不应该保持并展示，`user_display_msg` 不应该提前添加，应等用户输入结束后统一确认是否添加。

**AI：** 确认当前逻辑确实先 append 了 user display，且 `run_agent_loop` 也会先把 user 写入 raw_messages。

**AI：** 改成事务式提交：本轮开始前备份 raw_messages，构建 user/assistant display 但不写入；如果出现 error，回滚 raw_messages，不保存 display，不保存 trace；成功后统一提交。

**方案：** 失败轮次不会落盘，刷新后不会继续显示；新增 `test_chat_route_does_not_persist_failed_turn`。

---

## 16. 当前最终验证状态

**用户：** 持续要求修正并验证。

**AI：** 每次修改后运行测试。

**方案：** 当前测试覆盖增至 14 条，包含工具、调度、解析、多会话、上下文、长期记忆、异常回滚等。

验证结果：

```text
Ran 14 tests
OK
```

同时 `compileall` 和 `git diff --check` 通过。
