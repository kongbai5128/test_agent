import type { AgentEvent, DisplayMessage, DocumentAttachment, Session } from '../types'

const BASE = '/api'

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(BASE + url, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  })
  if (!resp.ok) {
    const text = await resp.text().catch(() => resp.statusText)
    throw new Error(`HTTP ${resp.status}: ${text}`)
  }
  return resp.json() as Promise<T>
}

// ── Session API ────────────────────────────────────────────────

export const api = {
  listSessions: () => request<Session[]>('/sessions'),

  createSession: (title = '') =>
    request<Session>('/sessions', {
      method: 'POST',
      body: JSON.stringify({ title }),
    }),

  getSession: (id: string) =>
    request<Session & { display_messages: DisplayMessage[]; todos: unknown[] }>(`/sessions/${id}`),

  updateSession: (id: string, title: string) =>
    request<Session>(`/sessions/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ title }),
    }),

  deleteSession: (id: string) =>
    fetch(`${BASE}/sessions/${id}`, { method: 'DELETE' }),

  getMessages: (id: string) => request<DisplayMessage[]>(`/sessions/${id}/messages`),

  getTrace: (id: string) => request<unknown[]>(`/sessions/${id}/trace`),

  uploadDocument: (
    sessionId: string,
    file: File,
    onProgress?: (progress: number) => void,
  ) =>
    uploadWithProgress<DocumentAttachment>(
      `/sessions/${sessionId}/documents`,
      file,
      onProgress,
    ),

  deleteDocument: (sessionId: string, documentId: string) =>
    fetch(`${BASE}/sessions/${sessionId}/documents/${documentId}`, { method: 'DELETE' }),

  listDocuments: (sessionId: string) =>
    request<DocumentAttachment[]>(`/sessions/${sessionId}/documents`),

  // SSE 聊天接口：返回原始 Response，由调用方处理流
  chatStream: (id: string, message: string, documentIds: string[] = []): Promise<Response> =>
    fetch(`${BASE}/sessions/${id}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, document_ids: documentIds }),
    }),
}

function uploadWithProgress<T>(
  url: string,
  file: File,
  onProgress?: (progress: number) => void,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    const form = new FormData()
    form.append('file', file)

    xhr.open('POST', BASE + url)

    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable) return
      onProgress?.(Math.round((event.loaded / event.total) * 100))
    }

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as T)
        } catch {
          reject(new Error('上传响应解析失败'))
        }
      } else {
        reject(new Error(`HTTP ${xhr.status}: ${xhr.responseText || xhr.statusText}`))
      }
    }

    xhr.onerror = () => reject(new Error('文件上传失败'))
    xhr.send(form)
  })
}

/**
 * 解析 SSE 流，按行 yield AgentEvent。
 * 处理多 chunk 分片的情况（buffer + split）。
 */
export async function* parseSSEStream(
  response: Response,
): AsyncGenerator<AgentEvent> {
  const reader = response.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? '' // 保留未完成的最后一行

    for (const line of lines) {
      const trimmed = line.trim()
      if (trimmed.startsWith('data: ')) {
        try {
          const json = trimmed.slice(6)
          const event = JSON.parse(json) as AgentEvent
          yield event
        } catch {
          // 跳过解析失败的行
        }
      }
    }
  }
}
