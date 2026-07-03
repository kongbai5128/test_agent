<template>
  <div class="message" :class="[`message--${msg.role}`, { 'message--streaming': msg.status === 'streaming' }]">
    <!-- 头像 -->
    <div class="message__avatar">
      {{ msg.role === 'user' ? '🙋' : '🤖' }}
    </div>

    <div class="message__body">
      <!-- 思考过程（可折叠）-->
      <div v-if="msg.thinking" class="message__thinking">
        <div class="thinking-toggle" @click="showThinking = !showThinking">
          <span>💭 思考过程</span>
          <span>{{ showThinking ? '▲' : '▼' }}</span>
        </div>
        <div v-if="showThinking" class="thinking-content">
          {{ msg.thinking }}
        </div>
      </div>

      <!-- 工具调用卡片列表 -->
      <div v-if="msg.tool_calls.length > 0" class="message__tools">
        <ToolCallCard
          v-for="(tc, i) in msg.tool_calls"
          :key="i"
          :tool="tc.tool"
          :params="tc.params"
          :result="tc.result"
        />
      </div>

      <!-- 消息内容 -->
      <div class="message__content" :class="{ 'message__content--empty': !msg.content && msg.status === 'streaming' }">
        <span v-if="!msg.content && msg.status === 'streaming'" class="cursor-blink">▌</span>
        <span v-else>{{ msg.content }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import ToolCallCard from './ToolCallCard.vue'
import type { ChatMessage } from '../types'

defineProps<{ msg: ChatMessage }>()

const showThinking = ref(false)
</script>

<style scoped>
.message {
  display: flex;
  gap: 12px;
  padding: 14px 16px;
  border-radius: 12px;
  margin-bottom: 4px;
  max-width: 100%;
  animation: fadeIn 0.2s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(6px); }
  to   { opacity: 1; transform: translateY(0); }
}

.message--user {
  background: var(--bg-user-msg);
  flex-direction: row-reverse;
}
.message--user .message__body {
  align-items: flex-end;
}
.message--user .message__content {
  background: var(--accent);
  color: #fff;
  border-radius: 12px 2px 12px 12px;
}

.message--assistant {
  background: var(--bg-assistant-msg);
}
.message--assistant .message__content {
  background: var(--bg-bubble);
  border-radius: 2px 12px 12px 12px;
}

.message__avatar {
  font-size: 24px;
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.message__body {
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex: 1;
  min-width: 0;
}

.message__content {
  padding: 10px 14px;
  line-height: 1.65;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 14.5px;
}
.message__content--empty {
  min-height: 38px;
}

/* 思考过程 */
.message__thinking {
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  font-size: 13px;
}
.thinking-toggle {
  display: flex;
  justify-content: space-between;
  padding: 6px 10px;
  cursor: pointer;
  background: var(--bg-thinking-header);
  color: var(--text-muted);
  user-select: none;
}
.thinking-toggle:hover {
  background: var(--bg-thinking-hover);
}
.thinking-content {
  padding: 8px 10px;
  color: var(--text-muted);
  white-space: pre-wrap;
  word-break: break-word;
  font-style: italic;
  background: var(--bg-thinking);
  line-height: 1.5;
}

.message__tools {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

/* 流式光标 */
.cursor-blink {
  animation: blink 1s step-end infinite;
  color: var(--accent);
}
@keyframes blink {
  50% { opacity: 0; }
}
</style>
