// 前端数据类型定义

export interface Session {
  id: string
  title: string
  created_at: string
  updated_at: string
  message_count: number
}

export interface ToolCallInfo {
  tool: string
  params: Record<string, unknown>
  result: string | null
}

export interface DisplayMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  thinking: string | null
  tool_calls: ToolCallInfo[]
}

// SSE 事件类型
export type AgentEvent =
  | { type: 'thinking'; content: string }
  | { type: 'tool_start'; tool: string; params: Record<string, unknown> }
  | { type: 'tool_result'; tool: string; result: string }
  | { type: 'message'; content: string }
  | { type: 'error'; message: string }
  | { type: 'done' }

// 前端显示用消息（含实时更新状态）
export interface ChatMessage extends DisplayMessage {
  status: 'done' | 'streaming' | 'error'
}

// 工具图标映射
export const TOOL_ICONS: Record<string, string> = {
  calculator: '🔢',
  search: '🔍',
  weather: '🌤️',
  todo: '📝',
}

export const TOOL_LABELS: Record<string, string> = {
  calculator: '计算器',
  search: '搜索',
  weather: '天气',
  todo: '待办',
}
