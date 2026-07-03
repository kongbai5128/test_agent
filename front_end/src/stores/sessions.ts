import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api } from '../api'
import type { Session } from '../types'

export const useSessionStore = defineStore('sessions', () => {
  const sessions = ref<Session[]>([])
  const activeId = ref<string | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const activeSession = computed(() =>
    sessions.value.find((s) => s.id === activeId.value) ?? null,
  )

  async function fetchSessions() {
    loading.value = true
    error.value = null
    try {
      sessions.value = await api.listSessions()
      // 默认激活第一个会话
      if (sessions.value.length > 0 && !activeId.value) {
        activeId.value = sessions.value[0].id
      }
    } catch (e) {
      error.value = String(e)
    } finally {
      loading.value = false
    }
  }

  async function createSession(title = '') {
    const session = await api.createSession(title)
    sessions.value.unshift(session)
    activeId.value = session.id
    return session
  }

  async function deleteSession(id: string) {
    await api.deleteSession(id)
    sessions.value = sessions.value.filter((s) => s.id !== id)
    if (activeId.value === id) {
      activeId.value = sessions.value[0]?.id ?? null
    }
  }

  async function renameSession(id: string, title: string) {
    const updated = await api.updateSession(id, title)
    const idx = sessions.value.findIndex((s) => s.id === id)
    if (idx !== -1) sessions.value[idx] = updated
  }

  function setActive(id: string) {
    activeId.value = id
  }

  /** 更新本地会话元数据（消息数、标题等）*/
  function patchLocal(id: string, patch: Partial<Session>) {
    const idx = sessions.value.findIndex((s) => s.id === id)
    if (idx !== -1) {
      sessions.value[idx] = { ...sessions.value[idx], ...patch }
    }
  }

  return {
    sessions,
    activeId,
    activeSession,
    loading,
    error,
    fetchSessions,
    createSession,
    deleteSession,
    renameSession,
    setActive,
    patchLocal,
  }
})
