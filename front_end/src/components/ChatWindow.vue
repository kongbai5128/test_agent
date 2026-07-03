<template>
  <div class="chat-window">
    <!-- 顶部标题栏 -->
    <div class="chat-header">
      <div class="chat-header__info">
        <h2 class="chat-title">{{ title || '新对话' }}</h2>
        <span class="chat-subtitle">{{ messages.length }} 条消息</span>
      </div>
      <div class="chat-header__actions">
        <!-- 工具列表按钮 -->
        <button class="icon-btn" title="查看可用工具" @click="showTools = !showTools">🔧</button>
      </div>
    </div>

    <!-- 工具列表弹层 -->
    <Transition name="slide-down">
      <div v-if="showTools" class="tools-panel">
        <div class="tools-panel__title">可用工具</div>
        <div class="tools-panel__list">
          <div v-for="t in TOOLS_INFO" :key="t.name" class="tools-panel__item">
            <span class="tools-panel__icon">{{ t.icon }}</span>
            <div>
              <div class="tools-panel__name">{{ t.label }}</div>
              <div class="tools-panel__desc">{{ t.desc }}</div>
            </div>
          </div>
        </div>
      </div>
    </Transition>

    <!-- 消息列表 -->
    <div ref="scrollRef" class="messages-container">
      <div v-if="messages.length === 0" class="empty-state">
        <div class="empty-state__icon">🤖</div>
        <div class="empty-state__title">Agent 已就绪</div>
        <div class="empty-state__subtitle">试试问我：帮我查北京天气、计算 2**32、搜索 FastAPI</div>
        <div class="quick-prompts">
          <button
            v-for="p in QUICK_PROMPTS"
            :key="p"
            class="quick-prompt-btn"
            @click="$emit('send', p)"
          >{{ p }}</button>
        </div>
      </div>

      <MessageItem
        v-for="msg in messages"
        :key="msg.id"
        :msg="msg"
      />

      <!-- 流式占位 -->
      <div v-if="isLoading && messages[messages.length - 1]?.role !== 'assistant'" class="typing-indicator">
        <span /><span /><span />
      </div>
    </div>

    <!-- 底部输入区 -->
    <InputArea
      :disabled="isLoading"
      placeholder="输入消息…（支持多轮追问）"
      @send="$emit('send', $event)"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import MessageItem from './MessageItem.vue'
import InputArea from './InputArea.vue'
import type { ChatMessage } from '../types'

defineProps<{
  messages: ChatMessage[]
  isLoading: boolean
  title?: string
}>()

defineEmits<{
  send: [message: string]
}>()

const scrollRef = ref<HTMLDivElement | null>(null)
const showTools = ref(false)

const TOOLS_INFO = [
  { name: 'calculator', icon: '🔢', label: '计算器', desc: '执行数学运算' },
  { name: 'search',     icon: '🔍', label: '搜索',   desc: '查询互联网信息（模拟）' },
  { name: 'weather',    icon: '🌤️', label: '天气',   desc: '查询城市实时天气（模拟）' },
  { name: 'todo',       icon: '📝', label: '待办',   desc: '管理本会话的待办事项' },
]

const QUICK_PROMPTS = [
  '帮我查北京今天的天气',
  '计算 (123 + 456) * 7 / 3',
  '搜索 FastAPI 的介绍',
  '添加一个待办：学习 Agent 开发',
]

// 消息列表变化时自动滚动到底部
watch(
  () => scrollRef.value,
  (el) => el && el.scrollTo({ top: el.scrollHeight }),
)

function scrollToBottom() {
  nextTick(() => {
    const el = scrollRef.value
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  })
}

defineExpose({ scrollToBottom })
</script>

<style scoped>
.chat-window {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-main);
}

/* 顶部栏 */
.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-surface);
  flex-shrink: 0;
}
.chat-header__info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.chat-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  max-width: 400px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.chat-subtitle {
  font-size: 11px;
  color: var(--text-muted);
}
.icon-btn {
  background: none;
  border: 1px solid var(--border);
  border-radius: 7px;
  width: 32px;
  height: 32px;
  cursor: pointer;
  font-size: 15px;
  transition: background 0.15s;
}
.icon-btn:hover { background: var(--bg-hover); }

/* 工具面板 */
.tools-panel {
  padding: 12px 20px;
  background: var(--bg-tool);
  border-bottom: 1px solid var(--border);
}
.tools-panel__title {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 8px;
}
.tools-panel__list {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.tools-panel__item {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 7px 12px;
}
.tools-panel__icon { font-size: 18px; }
.tools-panel__name { font-size: 13px; font-weight: 600; }
.tools-panel__desc { font-size: 11px; color: var(--text-muted); }

/* 消息区 */
.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  scroll-behavior: smooth;
}

/* 空状态 */
.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: var(--text-muted);
  padding: 40px 20px;
  text-align: center;
}
.empty-state__icon { font-size: 48px; }
.empty-state__title { font-size: 17px; font-weight: 600; color: var(--text-primary); }
.empty-state__subtitle { font-size: 13px; }

.quick-prompts {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
  margin-top: 4px;
}
.quick-prompt-btn {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 6px 14px;
  font-size: 13px;
  cursor: pointer;
  color: var(--text-primary);
  transition: background 0.15s, border-color 0.15s;
}
.quick-prompt-btn:hover {
  background: var(--bg-hover);
  border-color: var(--accent);
  color: var(--accent);
}

/* 打字指示器 */
.typing-indicator {
  display: flex;
  gap: 5px;
  padding: 14px 16px;
  align-items: center;
}
.typing-indicator span {
  width: 8px;
  height: 8px;
  background: var(--text-muted);
  border-radius: 50%;
  animation: bounce 1.2s infinite ease-in-out;
}
.typing-indicator span:nth-child(2) { animation-delay: 0.2s; }
.typing-indicator span:nth-child(3) { animation-delay: 0.4s; }
@keyframes bounce {
  0%, 80%, 100% { transform: scale(0.7); opacity: 0.5; }
  40%           { transform: scale(1.0); opacity: 1; }
}

/* 动画 */
.slide-down-enter-active, .slide-down-leave-active {
  transition: all 0.2s ease;
}
.slide-down-enter-from, .slide-down-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
</style>
