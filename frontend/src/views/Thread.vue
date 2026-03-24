<script setup>
import { ref, watch, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getThread } from '../api.js'
import { formatDate, shortenSender } from '../utils.js'
import ThreadNode from '../components/ThreadNode.vue'
import MessageBody from '../components/MessageBody.vue'
import AddressLink from '../components/AddressLink.vue'

const props = defineProps(['id'])
const route = useRoute()
const router = useRouter()

const data = ref(null)         // lightweight thread data (always loaded)
const fullData = ref(null)     // full thread data with body_text (lazy loaded)
const loading = ref(true)
const loadingFull = ref(false)
const error = ref(null)

const viewMode = computed(() => {
  const v = route.query.view
  return (v === 'flat' || v === 'nested') ? v : 'tree'
})

function setView(mode) {
  router.replace({ query: { ...route.query, view: mode === 'tree' ? undefined : mode } })
}

async function load() {
  loading.value = true
  error.value = null
  fullData.value = null
  try {
    data.value = await getThread(props.id)
    const root = data.value?.messages?.[0]
    document.title = `${root?.subject || 'thread'} — lore-mirror`
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function loadFull() {
  if (fullData.value || loadingFull.value) return
  loadingFull.value = true
  try {
    fullData.value = await getThread(props.id, { full: true })
  } catch (e) {
    error.value = e.message
  } finally {
    loadingFull.value = false
  }
}

// When switching to flat/nested, ensure full data is loaded
watch(viewMode, (mode) => {
  if (mode !== 'tree' && !fullData.value) loadFull()
}, { immediate: true })

watch(() => props.id, load, { immediate: true })

// Tree view computed (from lightweight data)
const tree = computed(() => {
  if (!data.value?.messages) return []
  const msgs = data.value.messages
  const byId = new Map(msgs.map(m => [m.message_id, { ...m, children: [] }]))
  const roots = []
  for (const m of byId.values()) {
    if (m.in_reply_to && byId.has(m.in_reply_to)) {
      byId.get(m.in_reply_to).children.push(m)
    } else {
      roots.push(m)
    }
  }
  return roots
})

// Flat view: messages sorted by date (from full data)
const flatMessages = computed(() => {
  if (!fullData.value?.messages) return []
  return [...fullData.value.messages].sort((a, b) => (a.date || '').localeCompare(b.date || ''))
})

// Nested view: messages with depth computed from in_reply_to chains
const nestedMessages = computed(() => {
  if (!fullData.value?.messages) return []
  const msgs = fullData.value.messages
  const byId = new Map(msgs.map(m => [m.message_id, { ...m, children: [] }]))
  const roots = []
  for (const m of byId.values()) {
    if (m.in_reply_to && byId.has(m.in_reply_to)) {
      byId.get(m.in_reply_to).children.push(m)
    } else {
      roots.push(m)
    }
  }

  const sortByDate = (a, b) => (a.date || '').localeCompare(b.date || '')
  const result = []
  function dfs(nodes, depth) {
    nodes.sort(sortByDate)
    for (const n of nodes) {
      result.push({ ...n, depth })
      if (n.children.length) dfs(n.children, depth + 1)
    }
  }
  dfs(roots, 0)
  return result
})

const inbox = computed(() => data.value?.inbox || '')
</script>

<template>
  <div>
    <div v-if="loading" class="loading">Loading...</div>
    <div v-else-if="error" class="error">Error: {{ error }}</div>
    <template v-else-if="data">
      <div class="thread-header-card">
        <div class="thread-breadcrumb">
          <router-link to="/">lore-mirror</router-link>
          <template v-if="inbox">
            <span class="bc-sep">/</span>
            <router-link :to="`/inbox/${inbox}`">{{ inbox }}</router-link>
          </template>
          <span class="bc-sep">&mdash;</span>
          thread ({{ data.total }} messages)
        </div>
        <div class="view-toggle">
          <button
            v-for="mode in ['tree', 'flat', 'nested']"
            :key="mode"
            class="view-btn"
            :class="{ active: viewMode === mode }"
            @click="setView(mode)"
          >{{ mode }}</button>
        </div>
      </div>

      <!-- Tree view (default) -->
      <div v-if="viewMode === 'tree'" class="thread-tree-card">
        <ThreadNode
          v-for="node in tree"
          :key="node.message_id"
          :node="node"
          :depth="0"
          :currentId="props.id"
        />
      </div>

      <!-- Flat view -->
      <template v-else-if="viewMode === 'flat'">
        <div v-if="loadingFull" class="loading">Loading full thread...</div>
        <div v-else class="thread-full">
          <div v-for="msg in flatMessages" :key="msg.message_id" class="thread-message">
            <div class="thread-msg-header">
              <AddressLink :address="msg.sender" context="header" />
              <span class="thread-msg-date">{{ formatDate(msg.date) }}</span>
              <div class="thread-msg-actions">
                <router-link :to="`/message/${encodeURIComponent(msg.message_id)}`" class="action-btn">message</router-link>
                <a :href="`/api/raw?id=${encodeURIComponent(msg.message_id)}`" class="action-btn">raw</a>
                <a :href="`https://lore.kernel.org/${inbox}/${msg.message_id}/`" target="_blank" rel="noopener" class="action-btn">lore</a>
              </div>
              <div v-if="msg.subject !== flatMessages[0]?.subject" class="thread-msg-subject">{{ msg.subject }}</div>
            </div>
            <MessageBody :bodyText="msg.body_text" />
          </div>
        </div>
      </template>

      <!-- Nested view -->
      <template v-else-if="viewMode === 'nested'">
        <div v-if="loadingFull" class="loading">Loading full thread...</div>
        <div v-else class="thread-full">
          <div
            v-for="msg in nestedMessages"
            :key="msg.message_id"
            class="thread-message"
            :style="{ marginLeft: (msg.depth * 24) + 'px' }"
          >
            <div class="thread-msg-header">
              <AddressLink :address="msg.sender" context="header" />
              <span class="thread-msg-date">{{ formatDate(msg.date) }}</span>
              <div class="thread-msg-actions">
                <router-link :to="`/message/${encodeURIComponent(msg.message_id)}`" class="action-btn">message</router-link>
                <a :href="`/api/raw?id=${encodeURIComponent(msg.message_id)}`" class="action-btn">raw</a>
                <a :href="`https://lore.kernel.org/${inbox}/${msg.message_id}/`" target="_blank" rel="noopener" class="action-btn">lore</a>
              </div>
              <div v-if="msg.subject !== nestedMessages[0]?.subject" class="thread-msg-subject">{{ msg.subject }}</div>
            </div>
            <MessageBody :bodyText="msg.body_text" />
          </div>
        </div>
      </template>
    </template>
  </div>
</template>

<style scoped>
.thread-header-card {
  background: #fff;
  border: 1px solid #d1d9e0;
  border-radius: 10px;
  padding: 12px 16px;
  margin-bottom: 12px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.thread-breadcrumb {
  font-size: 13px;
  display: flex;
  gap: 6px;
  align-items: center;
}

.bc-sep { color: #8b949e; }

.view-toggle {
  display: flex;
  gap: 0;
  border: 1px solid #d1d9e0;
  border-radius: 6px;
  overflow: hidden;
}

.view-btn {
  font-family: inherit;
  font-size: 12px;
  padding: 4px 12px;
  border: none;
  background: #f6f8fa;
  color: #656d76;
  cursor: pointer;
  transition: all 0.15s;
  border-right: 1px solid #d1d9e0;
}
.view-btn:last-child { border-right: none; }
.view-btn:hover { background: #eaeef2; }
.view-btn.active {
  background: #0969da;
  color: #fff;
}

.thread-tree-card {
  background: #fff;
  border: 1px solid #d1d9e0;
  border-radius: 10px;
  padding: 12px 16px;
}

.thread-full {
  margin-top: 0;
}

.thread-message {
  margin-bottom: 12px;
}

.thread-msg-header {
  background: #f6f8fa;
  padding: 10px 16px;
  border: 1px solid #d1d9e0;
  border-radius: 10px 10px 0 0;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.thread-msg-date {
  color: #656d76;
  font-size: 12px;
}

.thread-msg-actions {
  display: flex;
  gap: 4px;
  margin-left: auto;
}

.action-btn {
  font-size: 11px;
  padding: 2px 8px;
  border: 1px solid #d1d9e0;
  border-radius: 6px;
  color: #656d76;
  text-decoration: none !important;
  transition: all 0.15s;
}
.action-btn:hover {
  background: #eaeef2;
  border-color: #0969da;
  color: #0969da;
}

.thread-msg-subject {
  font-size: 12px;
  color: #656d76;
  width: 100%;
  margin-top: 2px;
}
</style>

<style>
html.dark .thread-header-card { background: #161b22; border-color: #30363d; }
html.dark .view-toggle { border-color: #30363d; }
html.dark .view-btn { background: #21262d; color: #8b949e; border-color: #30363d; }
html.dark .view-btn:hover { background: #30363d; }
html.dark .view-btn.active { background: #388bfd; color: #fff; }
html.dark .thread-tree-card { background: #161b22; border-color: #30363d; }
html.dark .thread-msg-header { background: #0d1117; border-color: #30363d; }
html.dark .thread-msg-date { color: #8b949e; }
html.dark .action-btn { color: #8b949e; border-color: #30363d; }
html.dark .action-btn:hover { background: #21262d; color: #58a6ff; border-color: #58a6ff; }
html.dark .thread-msg-subject { color: #8b949e; }
</style>
