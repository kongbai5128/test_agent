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

      <!-- 用户附件 -->
      <div v-if="msg.attachments?.length" class="message__attachments">
        <div
          v-for="doc in msg.attachments"
          :key="doc.id"
          class="attachment-card"
        >
          <div class="attachment-card__icon">{{ fileIcon(doc.filename) }}</div>
          <div class="attachment-card__main">
            <div class="attachment-card__name" :title="doc.filename">{{ doc.filename }}</div>
            <div class="attachment-card__meta">{{ formatSize(doc.size) }} · 已上传</div>
          </div>
        </div>
      </div>

      <!-- 消息内容 -->
      <div class="message__content" :class="{ 'message__content--empty': !msg.content && msg.status === 'streaming' }">
        <span v-if="!msg.content && msg.status === 'streaming'" class="cursor-blink">▌</span>
        <div v-else class="markdown-body" v-html="renderedContent" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import ToolCallCard from './ToolCallCard.vue'
import { renderMarkdown } from '../utils/markdown'
import type { ChatMessage } from '../types'

const props = defineProps<{ msg: ChatMessage }>()

const showThinking = ref(false)
const renderedContent = computed(() => renderMarkdown(props.msg.content || ''))

function formatSize(size: number): string {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

function fileIcon(filename: string): string {
  const lower = filename.toLowerCase()
  if (lower.endsWith('.pdf')) return 'PDF'
  if (lower.endsWith('.doc') || lower.endsWith('.docx')) return 'DOC'
  if (lower.endsWith('.md')) return 'MD'
  return 'TXT'
}
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
  word-break: break-word;
  font-size: 14.5px;
  overflow-x: auto;
}
.message__content--empty {
  min-height: 38px;
}
.markdown-body {
  max-width: 100%;
}
.markdown-body :deep(*) {
  max-width: 100%;
}
.markdown-body :deep(> :first-child) {
  margin-top: 0;
}
.markdown-body :deep(> :last-child) {
  margin-bottom: 0;
}
.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4) {
  margin: 0.65em 0 0.35em;
  line-height: 1.3;
  font-weight: 700;
}
.markdown-body :deep(h1) {
  font-size: 1.35em;
}
.markdown-body :deep(h2) {
  font-size: 1.2em;
}
.markdown-body :deep(h3) {
  font-size: 1.08em;
}
.markdown-body :deep(p),
.markdown-body :deep(ul),
.markdown-body :deep(ol),
.markdown-body :deep(blockquote),
.markdown-body :deep(pre),
.markdown-body :deep(table) {
  margin: 0.45em 0;
}
.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  padding-left: 1.4em;
}
.markdown-body :deep(li + li) {
  margin-top: 0.2em;
}
.markdown-body :deep(table) {
  display: block;
  width: max-content;
  max-width: 100%;
  overflow-x: auto;
  border-collapse: collapse;
}
.markdown-body :deep(th),
.markdown-body :deep(td) {
  padding: 6px 9px;
  border: 1px solid var(--border);
  text-align: left;
  vertical-align: top;
  white-space: nowrap;
}
.markdown-body :deep(th) {
  background: var(--bg-hover);
  font-weight: 700;
}
.markdown-body :deep(code) {
  padding: 2px 5px;
  border-radius: 5px;
  background: var(--bg-code);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 0.92em;
}
.markdown-body :deep(pre) {
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--bg-code);
  overflow-x: auto;
}
.markdown-body :deep(pre code) {
  padding: 0;
  background: transparent;
  white-space: pre;
}
.markdown-body :deep(blockquote) {
  padding-left: 10px;
  border-left: 3px solid var(--border);
  color: var(--text-muted);
}
.markdown-body :deep(a) {
  color: inherit;
  text-decoration: underline;
  text-underline-offset: 2px;
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

.message__attachments {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
}
.message--assistant .message__attachments {
  justify-content: flex-start;
}
.attachment-card {
  display: grid;
  grid-template-columns: 38px minmax(120px, 220px);
  gap: 8px;
  align-items: center;
  padding: 7px 9px 7px 7px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-surface);
}
.attachment-card__icon {
  width: 38px;
  height: 38px;
  border-radius: 7px;
  background: var(--accent-light);
  color: var(--accent);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-weight: 700;
}
.attachment-card__main {
  min-width: 0;
}
.attachment-card__name {
  font-size: 13px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.attachment-card__meta {
  margin-top: 2px;
  font-size: 11px;
  color: var(--text-muted);
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
