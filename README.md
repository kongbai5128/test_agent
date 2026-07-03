# 最小可用 Agent 系统

基于 Python FastAPI + Vue 3 的最小可用 Agent，从零实现，不依赖任何 Agent 框架。

## 项目结构

```
back_end/         FastAPI 后端
  app/
    main.py           FastAPI 应用入口（CORS、lifespan）
    config.py         配置（LLM provider、API Key 自动检测）
    agent/
      loop.py         Agent 核心循环（AsyncGenerator + SSE）
      system_prompt.py 系统提示词
    tools/
      registry.py     工具注册机制（ToolSpec + JSON Schema）
      calculator.py   计算器工具（AST 安全求值）
      search.py       搜索工具（模拟数据）
      weather.py      天气工具（模拟数据）
      todo.py         待办事项工具（会话隔离）
      read_docs.py    文档读取工具（PDF / Word / 文本）
      memory.py       长期记忆保存工具
    memory/
      store.py        长期记忆存储与相关性检索
    sessions/
      store.py        Session CRUD（JSON 文件持久化）
    context/
      manager.py      Context 压缩（microcompact + 完整截断）
    api/
      routes.py       FastAPI 路由（含 SSE 流式接口）
  run.py              启动入口

front_end/        Vue 3 前端
  src/
    App.vue           根组件（布局）
    components/
      SessionSidebar.vue  会话列表（创建/切换/重命名/删除）
      ChatWindow.vue      聊天主区域（消息列表 + 快捷提示）
      MessageItem.vue     消息气泡（用户/助手，含思考过程折叠）
      ToolCallCard.vue    工具调用卡片（可展开参数/结果）
      InputArea.vue       输入框（Enter 发送，Shift+Enter 换行）
    stores/sessions.ts    Pinia 状态管理
    composables/useChat.ts Chat 逻辑（SSE 流式处理）
    api/index.ts          API 客户端 + SSE 解析
    types/index.ts        TypeScript 类型定义
```

## 核心功能实现

### Agent Loop（`agent/loop.py`）

```
Step 1 → 接收用户输入，追加到 raw_messages
Step 2 → 调用 LLM（带工具 Schema），判断：直接回复 or 调用工具
Step 3 → 若有工具调用：执行工具，追加结果到 raw_messages
Step 4 → 继续循环，直到 LLM 给出最终答案 or 达到最大迭代次数
```

每个步骤通过 SSE 实时推送给前端（tool_start / tool_result / thinking / message）。

### 工具注册机制

每个工具通过 `ToolSpec` 注册，包含：

- `name`：工具名（LLM 用于调用）
- `description`：工具描述（LLM 用于决策）
- `parameters`：JSON Schema（LLM 用于填参数）
- `handler`：Python 函数

LLM 基于完整 Schema 自主决策是否调用及如何填参数，无硬编码路由。

### Session 管理

- 每个会话有独立 ID，数据持久化到 `data/sessions/` 目录
- `raw_messages`：OpenAI 格式消息，用于 LLM 上下文
- `display_messages`：格式化消息，供前端渲染
- `todos`：本会话独立的待办事项列表
- 多窗口完全隔离，互不影响

### 长期记忆

- 长期记忆持久化到 `data/memory/` 目录，每条记忆一个 JSON 文件
- LLM 可通过 `memory_save` 保存用户偏好、纠正反馈、项目背景和外部资源
- 每轮对话会按用户输入检索相关记忆，并注入 system prompt
- 支持通过 `/api/memories` 手动新增、检索和删除记忆

### Context 压缩（`context/manager.py`）

- **microcompact**：截断旧工具结果（保留结构，节省 token）
- **完整压缩**：仅保留最近 8 条消息 + 注入压缩说明
- 触发阈值：估算字符数 > 30,000
- 最大轮次限制：20 轮（超过时强制压缩）

## 快速启动

### 1. 配置 API Key

```bash
cd back_end
cp .env.example .env
# 编辑 .env，填入 API Key：
# DEEPSEEK_API_KEY=your_key_here；注意deepseek不要使用代理
```

支持的 LLM Provider（自动检测，哪个有 key 用哪个）：

- DeepSeek（推荐，`DEEPSEEK_API_KEY`）
- OpenAI（`OPENAI_API_KEY`）
- Anthropic（`ANTHROPIC_API_KEY`）


### 2. 启动后端

```bash
cd back_end
pip install -r requirements.txt
python run.py
# 后端运行在 http://localhost:8000
# API 文档：http://localhost:8000/docs
```

### 3. 启动前端

```bash
cd front_end
npm install
npm run dev
# 前端运行在 http://localhost:5173
```

## API 接口

| Method | Path                           | 说明                   |
| ------ | ------------------------------ | ---------------------- |
| GET    | /api/sessions                  | 获取会话列表           |
| POST   | /api/sessions                  | 创建会话               |
| GET    | /api/sessions/{id}             | 获取会话详情           |
| PATCH  | /api/sessions/{id}             | 修改会话标题           |
| DELETE | /api/sessions/{id}             | 删除会话               |
| POST   | /api/sessions/{id}/chat/stream | **SSE 发送消息** |
| GET    | /api/sessions/{id}/messages    | 获取格式化消息列表     |
| GET    | /api/sessions/{id}/trace       | 获取工具调用日志       |
| GET    | /api/sessions/{id}/todos       | 获取待办事项           |
| GET    | /api/memories                  | 获取/搜索长期记忆      |
| POST   | /api/memories                  | 手动新增长期记忆       |
| DELETE | /api/memories/{id}             | 删除长期记忆           |
| GET    | /api/tools                     | 获取已注册工具列表     |
| GET    | /api/health                    | 健康检查               |

## 扩展工具

在 `back_end/app/tools/` 目录新建文件，参考 `calculator.py` 的模式注册即可，
然后在 `tools/__init__.py` 中 import 触发注册。
