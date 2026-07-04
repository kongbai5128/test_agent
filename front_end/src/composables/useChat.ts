import { computed, nextTick, ref } from 'vue'
import { api, parseSSEStream } from '../api'
import { useSessionStore } from '../stores/sessions'
import type { ChatMessage, DocumentAttachment, ToolCallInfo } from '../types'

/**
 * Chat 逻辑 Composable。
 * 管理消息列表、SSE 流式接收、发送消息。
 */
export function useChat(sessionId: () => string | null) {
  const messagesBySession = ref<Record<string, ChatMessage[]>>({})
  const loadingBySession = ref<Record<string, boolean>>({})
  const errorsBySession = ref<Record<string, string | null>>({})
  const loadedSessions = new Set<string>()
  const sessionStore = useSessionStore()

  const messages = computed(() => {
    const id = sessionId()
    return id ? (messagesBySession.value[id] ?? []) : []
  })
  const isLoading = computed(() => {
    const id = sessionId()
    return id ? !!loadingBySession.value[id] : false
  })
  const streamError = computed(() => {
    const id = sessionId()
    return id ? (errorsBySession.value[id] ?? null) : null
  })

  function ensureMessages(id: string) {
    if (!messagesBySession.value[id]) {
      messagesBySession.value[id] = []
    }
    return messagesBySession.value[id]
  }

  /** 加载指定 session 的历史消息 */
  async function loadMessages(id: string) {
    if (loadingBySession.value[id] && messagesBySession.value[id]?.length) return
    if (loadedSessions.has(id) && messagesBySession.value[id]) return
    try {
      const raw = await api.getMessages(id)
      messagesBySession.value[id] = raw.map((m) => ({
        ...m,
        status: 'done' as const,
        tool_calls: m.tool_calls ?? [],
        attachments: m.attachments ?? [],
      }))
      loadedSessions.add(id)
    } catch (e) {
      console.error('loadMessages error:', e)
    }
  }

  /** 发送消息，通过 SSE 流式接收 Agent 执行过程 */
  async function sendMessage(content: string, attachments: DocumentAttachment[] = []) {
    const id = sessionId()
    const trimmed = content.trim()
    if (!id || loadingBySession.value[id] || (!trimmed && attachments.length === 0)) return

    loadingBySession.value[id] = true
    errorsBySession.value[id] = null
    const sessionMessages = ensureMessages(id)

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
    sessionMessages.push(userMsg)

    // 创建待填充的 assistant 消息（status=streaming）
    const assistantMsg: ChatMessage = {
      id: `a-${Date.now()}`,
      role: 'assistant',
      content: '',
      thinking: null,
      tool_calls: [],
      status: 'streaming',
    }
    sessionMessages.push(assistantMsg)
    const assistantIdx = sessionMessages.length - 1

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
        const msg = sessionMessages[assistantIdx]
        if (!msg) continue

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
            errorsBySession.value[id] = event.message
            break

          case 'done':
            if (msg.status !== 'error') {
              msg.status = 'done'
            }
            // 更新侧边栏消息计数
            sessionStore.patchLocal(id, {
              message_count: sessionMessages.length,
              updated_at: new Date().toISOString(),
            })
            break
        }
      }
    } catch (e) {
      const errMsg = String(e)
      if (sessionMessages[assistantIdx]) {
        sessionMessages[assistantIdx].content = `❌ 请求失败：${errMsg}`
        sessionMessages[assistantIdx].status = 'error'
      }
      errorsBySession.value[id] = errMsg
    } finally {
      // 确保状态清除
      if (sessionMessages[assistantIdx]?.status === 'streaming') {
        sessionMessages[assistantIdx].status = 'done'
      }
      loadingBySession.value[id] = false
    }
  }

  function clearMessages() {
    const id = sessionId()
    if (id) {
      messagesBySession.value[id] = []
      loadedSessions.delete(id)
    }
  }

  return { messages, isLoading, streamError, loadMessages, sendMessage, clearMessages }
}
