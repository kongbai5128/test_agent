<template>
  <div class="input-area">
    <div v-if="attachments.length > 0" class="attachment-tray">
      <div
        v-for="item in attachments"
        :key="item.localId"
        class="file-card"
        :class="`file-card--${item.status}`"
      >
        <div class="file-card__icon">{{ fileIcon(item.filename) }}</div>
        <div class="file-card__main">
          <div class="file-card__name" :title="item.filename">{{ item.filename }}</div>
          <div class="file-card__meta">
            <span>{{ formatSize(item.size) }}</span>
            <span>·</span>
            <span>{{ statusText(item) }}</span>
          </div>
          <div v-if="item.status === 'uploading'" class="file-progress">
            <span :style="{ width: `${item.progress}%` }" />
          </div>
          <div v-if="item.status === 'error'" class="file-card__error" :title="item.error || ''">
            {{ item.error || '上传失败' }}
          </div>
        </div>
        <button
          class="file-card__remove"
          type="button"
          :disabled="item.status === 'uploading'"
          title="移除文件"
          @click="removeAttachment(item.localId)"
        >
          ×
        </button>
      </div>
    </div>

    <div class="input-wrapper" :class="{ 'input-wrapper--disabled': disabled }">
      <input
        ref="fileInputRef"
        class="file-input"
        type="file"
        multiple
        accept=".pdf,.doc,.docx,.txt,.md,.markdown"
        @change="handleFiles"
      />
      <button
        class="attach-btn"
        type="button"
        :disabled="disabled || !sessionId || hasUploading"
        title="添加文件"
        @click="openFilePicker"
      >
        ＋
      </button>
      <textarea
        ref="textareaRef"
        v-model="inputText"
        class="input-textarea"
        :placeholder="placeholder"
        :disabled="disabled"
        rows="1"
        @keydown.enter.exact.prevent="handleSend"
        @keydown.enter.shift.exact="undefined"
        @input="autoResize"
      />
      <button
        class="send-btn"
        :disabled="disabled || !canSend"
        @click="handleSend"
        :title="disabled ? '正在处理…' : '发送 (Enter)'"
      >
        <span v-if="disabled" class="send-spinner" />
        <span v-else>↑</span>
      </button>
    </div>
    <div class="input-hint">
      按 <kbd>Enter</kbd> 发送 · <kbd>Shift+Enter</kbd> 换行
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, nextTick } from 'vue'
import { api } from '../api'
import type { DocumentAttachment, SendPayload, UploadItem } from '../types'

const props = defineProps<{
  disabled?: boolean
  placeholder?: string
  sessionId: string | null
}>()

const emit = defineEmits<{
  send: [payload: SendPayload]
}>()

const inputText = ref('')
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)
const attachments = ref<UploadItem[]>([])

const hasUploading = computed(() =>
  attachments.value.some((item) => item.status === 'queued' || item.status === 'uploading'),
)

const readyAttachments = computed(() =>
  attachments.value
    .filter((item) => item.status === 'ready' && item.document)
    .map((item) => item.document as DocumentAttachment),
)

const canSend = computed(() =>
  !hasUploading.value && (inputText.value.trim().length > 0 || readyAttachments.value.length > 0),
)

function openFilePicker() {
  fileInputRef.value?.click()
}

async function handleFiles(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  input.value = ''
  if (!props.sessionId || files.length === 0) return

  const remaining = Math.max(0, 8 - attachments.value.length)
  for (const file of files.slice(0, remaining)) {
    const item: UploadItem = {
      localId: `file-${Date.now()}-${Math.random().toString(16).slice(2)}`,
      file,
      filename: file.name,
      size: file.size,
      progress: 0,
      status: 'queued',
      error: null,
      document: null,
    }
    attachments.value.push(item)
    uploadItem(item)
  }
}

async function uploadItem(item: UploadItem) {
  if (!props.sessionId) return
  item.status = 'uploading'
  try {
    item.document = await api.uploadDocument(props.sessionId, item.file, (progress) => {
      item.progress = progress
    })
    item.progress = 100
    item.status = 'ready'
  } catch (error) {
    item.status = 'error'
    item.error = normalizeError(error)
  }
}

async function handleSend() {
  const text = inputText.value.trim()
  if (!canSend.value) return
  const docs = readyAttachments.value
  inputText.value = ''
  attachments.value = attachments.value.filter((item) => item.status === 'error')
  await nextTick()
  autoResize()
  emit('send', { message: text, attachments: docs })
}

function autoResize() {
  const el = textareaRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 160) + 'px'
}

async function removeAttachment(localId: string) {
  const item = attachments.value.find((candidate) => candidate.localId === localId)
  if (!item || item.status === 'uploading') return
  attachments.value = attachments.value.filter((candidate) => candidate.localId !== localId)
  if (item.document && props.sessionId) {
    await api.deleteDocument(props.sessionId, item.document.id).catch(() => undefined)
  }
}

function normalizeError(error: unknown): string {
  const raw = error instanceof Error ? error.message : String(error)
  try {
    const jsonStart = raw.indexOf('{')
    if (jsonStart >= 0) {
      const parsed = JSON.parse(raw.slice(jsonStart))
      if (parsed.detail) return String(parsed.detail)
    }
  } catch {
    // ignore JSON parse failures
  }
  return raw.replace(/^Error:\s*/, '')
}

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

function statusText(item: UploadItem): string {
  if (item.status === 'queued') return '等待上传'
  if (item.status === 'uploading') return `上传中 ${item.progress}%`
  if (item.status === 'ready') return '已就绪'
  return '失败'
}
</script>

<style scoped>
.input-area {
  padding: 12px 16px 8px;
  background: var(--bg-input-area);
  border-top: 1px solid var(--border);
}

.attachment-tray {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  padding: 0 0 8px;
}

.file-card {
  position: relative;
  display: grid;
  grid-template-columns: 42px minmax(150px, 220px) 22px;
  gap: 9px;
  align-items: center;
  flex: 0 0 auto;
  min-height: 58px;
  padding: 8px 7px 8px 8px;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 8px;
}
.file-card--ready {
  border-color: rgba(34, 197, 94, 0.45);
}
.file-card--error {
  border-color: rgba(239, 68, 68, 0.45);
}

.file-card__icon {
  width: 42px;
  height: 42px;
  border-radius: 7px;
  background: var(--accent-light);
  color: var(--accent);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
}
.file-card__main {
  min-width: 0;
}
.file-card__name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.file-card__meta {
  display: flex;
  gap: 4px;
  align-items: center;
  margin-top: 3px;
  font-size: 11px;
  color: var(--text-muted);
  white-space: nowrap;
}
.file-card__error {
  margin-top: 3px;
  max-width: 210px;
  color: #dc2626;
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.file-progress {
  height: 3px;
  margin-top: 6px;
  background: var(--bg-code);
  border-radius: 99px;
  overflow: hidden;
}
.file-progress span {
  display: block;
  height: 100%;
  background: var(--accent);
  transition: width 0.2s ease;
}
.file-card__remove {
  width: 22px;
  height: 22px;
  border: none;
  border-radius: 50%;
  background: var(--bg-hover);
  color: var(--text-muted);
  cursor: pointer;
  font-size: 17px;
  line-height: 1;
}
.file-card__remove:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.input-wrapper {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  background: var(--bg-surface);
  border: 1.5px solid var(--border);
  border-radius: 12px;
  padding: 8px 8px 8px 14px;
  transition: border-color 0.2s;
}
.input-wrapper:focus-within {
  border-color: var(--accent);
}
.input-wrapper--disabled {
  opacity: 0.6;
}

.input-textarea {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  resize: none;
  font-family: inherit;
  font-size: 14.5px;
  line-height: 1.6;
  color: var(--text-primary);
  min-height: 24px;
  max-height: 160px;
  overflow-y: auto;
}
.input-textarea::placeholder {
  color: var(--text-placeholder);
}

.file-input {
  display: none;
}

.attach-btn {
  width: 34px;
  height: 34px;
  border-radius: 8px;
  border: none;
  background: var(--bg-hover);
  color: var(--text-primary);
  font-size: 22px;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: background 0.15s, opacity 0.15s;
}
.attach-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.attach-btn:not(:disabled):hover {
  background: var(--accent-light);
  color: var(--accent);
}

.send-btn {
  width: 34px;
  height: 34px;
  border-radius: 8px;
  border: none;
  background: var(--accent);
  color: #fff;
  font-size: 16px;
  font-weight: bold;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: background 0.15s, opacity 0.15s;
}
.send-btn:disabled {
  background: var(--border);
  cursor: not-allowed;
  opacity: 0.6;
}
.send-btn:not(:disabled):hover {
  background: var(--accent-hover);
}

.send-spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255,255,255,0.4);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.input-hint {
  font-size: 11px;
  color: var(--text-placeholder);
  text-align: right;
  margin-top: 5px;
}
kbd {
  background: var(--bg-code);
  border-radius: 3px;
  padding: 0 4px;
  font-family: monospace;
  font-size: 10px;
}
</style>
