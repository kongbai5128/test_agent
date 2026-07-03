<template>
  <div class="tool-card">
    <div class="tool-card__header" @click="expanded = !expanded">
      <span class="tool-icon">{{ TOOL_ICONS[tool] ?? '🔧' }}</span>
      <span class="tool-name">{{ TOOL_LABELS[tool] ?? tool }}</span>
      <span v-if="result === null" class="tool-status tool-status--running">
        <span class="spinner" />
        执行中…
      </span>
      <span v-else class="tool-status tool-status--done">✓ 完成</span>
      <span class="tool-expand">{{ expanded ? '▲' : '▼' }}</span>
    </div>

    <div v-if="expanded" class="tool-card__body">
      <div class="tool-section">
        <div class="tool-section__label">参数</div>
        <pre class="tool-code">{{ formattedParams }}</pre>
      </div>
      <div v-if="result !== null" class="tool-section">
        <div class="tool-section__label">结果</div>
        <pre class="tool-code tool-code--result">{{ result }}</pre>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { TOOL_ICONS, TOOL_LABELS } from '../types'

const props = defineProps<{
  tool: string
  params: Record<string, unknown>
  result: string | null
}>()

const expanded = ref(false)

const formattedParams = computed(() => JSON.stringify(props.params, null, 2))
</script>

<style scoped>
.tool-card {
  border: 1px solid var(--border);
  border-radius: 8px;
  margin: 6px 0;
  overflow: hidden;
  background: var(--bg-tool);
  font-size: 13px;
}

.tool-card__header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  cursor: pointer;
  user-select: none;
  background: var(--bg-tool-header);
  transition: background 0.15s;
}
.tool-card__header:hover {
  background: var(--bg-tool-hover);
}

.tool-icon {
  font-size: 15px;
}
.tool-name {
  font-weight: 600;
  color: var(--text-primary);
  flex: 1;
}
.tool-status {
  font-size: 11px;
  padding: 2px 7px;
  border-radius: 10px;
  font-weight: 500;
}
.tool-status--running {
  background: #fff3cd;
  color: #856404;
  display: flex;
  align-items: center;
  gap: 4px;
}
.tool-status--done {
  background: #d1e7dd;
  color: #0a3622;
}
.tool-expand {
  font-size: 10px;
  color: var(--text-muted);
}

.tool-card__body {
  padding: 10px 12px;
  border-top: 1px solid var(--border);
}
.tool-section {
  margin-bottom: 8px;
}
.tool-section:last-child {
  margin-bottom: 0;
}
.tool-section__label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
  margin-bottom: 4px;
}
.tool-code {
  background: var(--bg-code);
  border-radius: 5px;
  padding: 8px 10px;
  font-family: 'Menlo', 'Consolas', monospace;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-all;
  color: var(--text-code);
  margin: 0;
}
.tool-code--result {
  color: var(--text-result);
}

/* 旋转动画 */
.spinner {
  display: inline-block;
  width: 10px;
  height: 10px;
  border: 2px solid #856404;
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
