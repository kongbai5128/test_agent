<template>
  <aside class="sidebar">
    <!-- 顶部标题 + 新建按钮 -->
    <div class="sidebar__header">
      <div class="sidebar__brand">
        <span class="brand-icon">🤖</span>
        <span class="brand-name">Agent Chat</span>
      </div>
      <button class="new-btn" @click="handleCreate" title="新建对话">
        <span>+</span>
      </button>
    </div>

    <!-- 会话列表 -->
    <div class="sidebar__list">
      <div v-if="store.loading" class="sidebar__empty">加载中…</div>
      <div v-else-if="store.sessions.length === 0" class="sidebar__empty">
        暂无对话，点击 + 新建
      </div>
      <div
        v-else
        v-for="session in store.sessions"
        :key="session.id"
        class="session-item"
        :class="{ 'session-item--active': session.id === store.activeId }"
        @click="store.setActive(session.id)"
      >
        <div class="session-item__content">
          <div
            class="session-item__title"
            :contenteditable="editingId === session.id"
            @dblclick="startEdit(session)"
            @blur="finishEdit(session, $event)"
            @keydown.enter.prevent="($event.target as HTMLElement).blur()"
            @click.stop="editingId === session.id && undefined"
          >{{ session.title }}</div>
          <div class="session-item__meta">
            {{ session.message_count }} 条 · {{ formatTime(session.updated_at) }}
          </div>
        </div>
        <button
          class="session-item__del"
          @click.stop="handleDelete(session.id)"
          title="删除"
        >✕</button>
      </div>
    </div>

    <!-- 底部统计 -->
    <div class="sidebar__footer">
      {{ store.sessions.length }} 个对话
    </div>
  </aside>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useSessionStore } from '../stores/sessions'
import type { Session } from '../types'

const store = useSessionStore()
const editingId = ref<string | null>(null)

async function handleCreate() {
  await store.createSession()
}

async function handleDelete(id: string) {
  if (confirm('确认删除此对话？')) {
    await store.deleteSession(id)
  }
}

function startEdit(session: Session) {
  editingId.value = session.id
}

async function finishEdit(session: Session, event: Event) {
  const el = event.target as HTMLElement
  const newTitle = el.innerText.trim()
  editingId.value = null
  if (newTitle && newTitle !== session.title) {
    await store.renameSession(session.id, newTitle)
  } else {
    el.innerText = session.title // 恢复原值
  }
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso)
    const now = new Date()
    const diffMs = now.getTime() - d.getTime()
    const diffMin = Math.floor(diffMs / 60000)
    if (diffMin < 1) return '刚刚'
    if (diffMin < 60) return `${diffMin} 分钟前`
    const diffHour = Math.floor(diffMin / 60)
    if (diffHour < 24) return `${diffHour} 小时前`
    return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
  } catch {
    return ''
  }
}
</script>

<style scoped>
.sidebar {
  width: 240px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: var(--bg-sidebar);
  border-right: 1px solid var(--border);
  height: 100%;
}

.sidebar__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 12px;
  border-bottom: 1px solid var(--border);
}
.sidebar__brand {
  display: flex;
  align-items: center;
  gap: 7px;
}
.brand-icon { font-size: 20px; }
.brand-name { font-size: 15px; font-weight: 700; color: var(--text-primary); }

.new-btn {
  width: 28px;
  height: 28px;
  border-radius: 7px;
  border: 1px solid var(--border);
  background: var(--bg-surface);
  color: var(--accent);
  font-size: 18px;
  font-weight: bold;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
  transition: background 0.15s;
}
.new-btn:hover { background: var(--bg-hover); }

/* 会话列表 */
.sidebar__list {
  flex: 1;
  overflow-y: auto;
  padding: 6px 6px;
}
.sidebar__empty {
  font-size: 13px;
  color: var(--text-muted);
  text-align: center;
  margin-top: 24px;
}

.session-item {
  display: flex;
  align-items: center;
  gap: 4px;
  border-radius: 8px;
  padding: 9px 10px;
  cursor: pointer;
  transition: background 0.12s;
  margin-bottom: 2px;
}
.session-item:hover {
  background: var(--bg-hover);
}
.session-item--active {
  background: var(--accent-light);
}
.session-item--active .session-item__title {
  color: var(--accent);
  font-weight: 600;
}

.session-item__content {
  flex: 1;
  min-width: 0;
}
.session-item__title {
  font-size: 13px;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  outline: none;
  border-radius: 3px;
}
.session-item__title[contenteditable="true"] {
  background: var(--bg-surface);
  padding: 1px 4px;
  white-space: normal;
}
.session-item__meta {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 2px;
}

.session-item__del {
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 11px;
  opacity: 0;
  padding: 2px 4px;
  border-radius: 4px;
  transition: opacity 0.15s, background 0.15s;
}
.session-item:hover .session-item__del {
  opacity: 1;
}
.session-item__del:hover {
  background: #fee2e2;
  color: #dc2626;
}

/* 底部 */
.sidebar__footer {
  padding: 10px 14px;
  font-size: 11px;
  color: var(--text-muted);
  border-top: 1px solid var(--border);
}
</style>
