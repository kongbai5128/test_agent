<template>
  <div class="input-area">
    <div class="input-wrapper" :class="{ 'input-wrapper--disabled': disabled }">
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
        :disabled="disabled || !inputText.trim()"
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
import { ref, nextTick } from 'vue'

defineProps<{
  disabled?: boolean
  placeholder?: string
}>()

const emit = defineEmits<{
  send: [message: string]
}>()

const inputText = ref('')
const textareaRef = ref<HTMLTextAreaElement | null>(null)

async function handleSend() {
  const text = inputText.value.trim()
  if (!text) return
  inputText.value = ''
  await nextTick()
  autoResize()
  emit('send', text)
}

function autoResize() {
  const el = textareaRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 160) + 'px'
}
</script>

<style scoped>
.input-area {
  padding: 12px 16px 8px;
  background: var(--bg-input-area);
  border-top: 1px solid var(--border);
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
