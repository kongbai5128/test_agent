import { nextTick, ref } from 'vue'
import { api, parseSSEStream } from '../api'
import { useSessionStore } from '../stores/sessions'
import type { ChatMessage, DocumentAttachment, ToolCallInfo } from '../types'

/**
 * Chat 逻辑 Composable。
 * 管理消息列表、SSE 流式接收、发送消息。
 */
export function useChat(sessionId: () => string | null) {
  const messages = ref<ChatMessage[]>([])
  const isLoading = ref(false)
  const streamError = ref<string | null>(null)
  const sessionStore = useSessionStore()

  /** 加载指定 session 的历史消息 */
  async function loadMessages(id: string) {
    try {
      const raw = await api.getMessages(id)
      messages.value = raw.map((m) => ({
        ...m,
        status: 'done' as const,
        tool_calls: m.tool_calls ?? [],
      }))
    } catch (e) {
      console.error('loadMessages error:', e)
    }
  }

  /** 发送消息，通过 SSE 流式接收 Agent 执行过程 */
  async function sendMessage(content: string, attachments: DocumentAttachment[] = []) {
    const id = sessionId()
    const trimmed = content.trim()
    if (!id || isLoading.value || (!trimmed && attachments.length === 0)) return

    isLoading.value = true
    streamError.value = null

    // 立即添加用户消息到列表
    const userMsg: ChatMessage = {
      id: `u-${Date.now()}`,
      role: 'user',
      content: trimmed || '请阅读并总结上传的文档。',
      thinking: null,
      tool_calls: [],
      attachments,
      status: 'done',
    }
    messages.value.push(userMsg)

    // 创建待填充的 assistant 消息（status=streaming）
    const assistantMsg: ChatMessage = {
      id: `a-${Date.now()}`,
      role: 'assistant',
      content: '',
      thinking: null,
      tool_calls: [],
      status: 'streaming',
    }
    messages.value.push(assistantMsg)
    const assistantIdx = messages.value.length - 1

    await nextTick()

    try {
      const response = await api.chatStream(
        id,
        trimmed,
        attachments.map((item) => item.id),
      )

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      for await (const event of parseSSEStream(response)) {
        const msg = messages.value[assistantIdx]

        switch (event.type) {
          case 'thinking':
            msg.thinking = (msg.thinking ?? '') + event.content
            break

          case 'tool_start':
            msg.tool_calls.push({
              tool: event.tool,
              params: event.params,
              result: null,
            } as ToolCallInfo)
            break

          case 'tool_result': {
            // 找最后一个 result 为 null 且 tool 匹配的记录
            const pending = [...msg.tool_calls]
              .reverse()
              .find((tc) => tc.tool === event.tool && tc.result === null)
            if (pending) pending.result = event.result
            break
          }

          case 'message':
            msg.content = event.content
            break

          case 'error':
            msg.content = `❌ ${event.message}`
            msg.status = 'error'
            streamError.value = event.message
            break

          case 'done':
            if (msg.status !== 'error') {
              msg.status = 'done'
            }
            // 更新侧边栏消息计数
            sessionStore.patchLocal(id, {
              message_count: messages.value.length,
              updated_at: new Date().toISOString(),
            })
            break
        }
      }
    } catch (e) {
      const errMsg = String(e)
      messages.value[assistantIdx].content = `❌ 请求失败：${errMsg}`
      messages.value[assistantIdx].status = 'error'
      streamError.value = errMsg
    } finally {
      // 确保状态清除
      if (messages.value[assistantIdx]?.status === 'streaming') {
        messages.value[assistantIdx].status = 'done'
      }
      isLoading.value = false
    }
  }

  function clearMessages() {
    messages.value = []
  }

  return { messages, isLoading, streamError, loadMessages, sendMessage, clearMessages }
}
