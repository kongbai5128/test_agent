<template>
  <div class="app-layout">
    <SessionSidebar />

    <main class="app-main">
      <template v-if="store.activeId">
        <ChatWindow
          ref="chatWindowRef"
          :messages="messages"
          :is-loading="isLoading"
          :title="store.activeSession?.title"
          :session-id="store.activeId"
          @send="handleSend"
        />
      </template>
      <div v-else class="app-empty">
        <div class="app-empty__icon">💬</div>
        <div class="app-empty__text">从左侧选择或新建对话开始</div>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { watch, ref, onMounted } from 'vue'
import { useSessionStore } from './stores/sessions'
import { useChat } from './composables/useChat'
import SessionSidebar from './components/SessionSidebar.vue'
import ChatWindow from './components/ChatWindow.vue'
import type { SendPayload } from './types'

const store = useSessionStore()
const chatWindowRef = ref<InstanceType<typeof ChatWindow> | null>(null)

const { messages, isLoading, loadMessages, sendMessage, clearMessages } = useChat(
  () => store.activeId,
)

// 初始化：加载会话列表，若无会话则自动新建一个
onMounted(async () => {
  await store.fetchSessions()
  if (store.sessions.length === 0) {
    await store.createSession()
  }
})

// 切换 session 时加载历史消息
watch(
  () => store.activeId,
  async (id) => {
    clearMessages()
    if (id) await loadMessages(id)
  },
)

// 消息更新时滚动到底部
watch(
  messages,
  () => chatWindowRef.value?.scrollToBottom(),
  { deep: true },
)

async function handleSend(payload: SendPayload) {
  if (!store.activeId) return
  await sendMessage(payload.message, payload.attachments)
}
</script>

<style scoped>
.app-layout {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

.app-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.app-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: var(--text-muted);
}
.app-empty__icon { font-size: 48px; }
.app-empty__text { font-size: 15px; }
</style>
