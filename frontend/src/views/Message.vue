<script setup>
import { ref, watch, computed, onMounted, onUnmounted } from 'vue'
import { getMessage, getThread } from '../api.js'
import { useRouter } from 'vue-router'
import AddressLink from '../components/AddressLink.vue'
import MessageBody from '../components/MessageBody.vue'

const addressHeaders = new Set(['From', 'To', 'Cc', 'Reply-To', 'Sender'])

const router = useRouter()

const props = defineProps(['id'])
const msg = ref(null)
const loading = ref(true)
const error = ref(null)
const showAllHeaders = ref(false)
const rawThreadMessages = ref([])
async function load() {
  loading.value = true
  error.value = null
  rawThreadMessages.value = []
  try {
    const [msgResult, threadResult] = await Promise.allSettled([
      getMessage(props.id),
      getThread(props.id)
    ])
    if (msgResult.status === 'rejected') throw new Error(msgResult.reason?.message || 'Failed to load message')
    msg.value = msgResult.value
    document.title = `${msg.value.subject || 'message'} — lore-mirror`
    if (threadResult.status === 'fulfilled' && threadResult.value?.messages?.length > 1) {
      rawThreadMessages.value = threadResult.value.messages
    }
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

// Build reply tree and flatten via DFS for natural reading order
const threadMessages = computed(() => {
  const msgs = rawThreadMessages.value
  if (!msgs.length) return []
  const byId = new Map(msgs.map(m => [m.message_id, { ...m, children: [] }]))
  const roots = []
  for (const m of byId.values()) {
    if (m.in_reply_to && byId.has(m.in_reply_to)) {
      byId.get(m.in_reply_to).children.push(m)
    } else {
      roots.push(m)
    }
  }
  // Sort siblings by date at each level
  const sortByDate = (a, b) => (a.date || '').localeCompare(b.date || '')
  const result = []
  function dfs(nodes) {
    nodes.sort(sortByDate)
    for (const n of nodes) {
      result.push(n)
      if (n.children.length) dfs(n.children)
    }
  }
  dfs(roots)
  return result
})

const currentIndex = computed(() => {
  if (!msg.value || !threadMessages.value.length) return -1
  return threadMessages.value.findIndex(m => m.message_id === msg.value.message_id)
})

const prevMessage = computed(() => {
  const i = currentIndex.value
  return i > 0 ? threadMessages.value[i - 1] : null
})

const nextMessage = computed(() => {
  const i = currentIndex.value
  return (i >= 0 && i < threadMessages.value.length - 1) ? threadMessages.value[i + 1] : null
})

watch(() => props.id, load, { immediate: true })

const importantHeaders = ['From', 'To', 'Cc', 'Date', 'Subject', 'Message-ID', 'In-Reply-To', 'References']

function splitAddresses(raw) {
  if (!raw) return []
  // Split on commas not inside angle brackets
  const addrs = []
  let depth = 0, start = 0
  for (let i = 0; i < raw.length; i++) {
    if (raw[i] === '<') depth++
    else if (raw[i] === '>') depth--
    else if (raw[i] === ',' && depth === 0) {
      addrs.push(raw.slice(start, i).trim())
      start = i + 1
    }
  }
  addrs.push(raw.slice(start).trim())
  return addrs.filter(a => a)
}

function parseMessageIds(raw) {
  if (!raw) return []
  return [...raw.matchAll(/<([^>]+)>/g)].map(m => m[1])
}

const headerLines = computed(() => {
  if (!msg.value?.headers) return []
  const h = msg.value.headers
  const keys = showAllHeaders.value ? Object.keys(h) : importantHeaders.filter(k => h[k])
  return keys.map(k => {
    const val = Array.isArray(h[k]) ? h[k].join(', ') : h[k]
    const ids = k === 'References' ? parseMessageIds(val) : null
    // Split address headers into individual addresses
    const addrs = addressHeaders.has(k) ? splitAddresses(val) : null
    return { key: k, value: val, ids, addrs }
  })
})

const hasDiff = computed(() => {
  if (!msg.value?.body_text) return false
  const lines = msg.value.body_text.split('\n')
  return lines.some(l => l.startsWith('diff --git') || l.startsWith('---') || l.startsWith('@@'))
})

const isPatch = computed(() => {
  if (!msg.value?.subject) return false
  const subj = msg.value.subject
  return /\[PATCH/i.test(subj) && !/^\s*Re:/i.test(subj) && hasDiff.value
})

const seriesTotal = computed(() => {
  if (!msg.value?.subject) return 0
  const m = msg.value.subject.match(/\[PATCH(?:\s+\S+)*\s+\d+\/(\d+)\]/i)
  return m ? parseInt(m[1], 10) : 0
})

function onKeydown(e) {
  if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) return
  if (e.key === 'j' || e.key === 'J') {
    if (nextMessage.value) router.push(`/message/${encodeURIComponent(nextMessage.value.message_id)}`)
  } else if (e.key === 'k' || e.key === 'K') {
    if (prevMessage.value) router.push(`/message/${encodeURIComponent(prevMessage.value.message_id)}`)
  } else if (e.key === 't') {
    if (msg.value) router.push(`/thread/${encodeURIComponent(msg.value.message_id)}`)
  }
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <div>
    <div v-if="loading" class="loading">Loading...</div>
    <div v-else-if="error" class="error">Error: {{ error }}</div>
    <template v-else-if="msg">
      <div class="msg-header-card">
        <div class="msg-breadcrumb">
          <router-link to="/">lore-mirror</router-link>
          <span class="bc-sep">/</span>
          <router-link :to="`/inbox/${msg.inbox_name}`">{{ msg.inbox_name }}</router-link>
        </div>

        <pre class="msg-headers"><template v-for="h in headerLines" :key="h.key"><b>{{ h.key }}:</b> <template v-if="h.key === 'In-Reply-To' && h.value"><router-link :to="`/message/${encodeURIComponent(h.value.replace(/[<>]/g, ''))}`">{{ h.value }}</router-link></template><template v-else-if="h.ids && h.ids.length"><template v-for="(id, idx) in h.ids" :key="id"><template v-if="idx"> </template>&lt;<router-link :to="`/message/${encodeURIComponent(id)}`">{{ id }}</router-link>&gt;</template></template><template v-else-if="h.addrs && h.addrs.length"><template v-for="(addr, idx) in h.addrs" :key="idx"><template v-if="idx">, </template><AddressLink :address="addr" context="header" /></template></template><template v-else>{{ h.value }}</template>
</template></pre>

        <div class="msg-actions">
          <a href="#" @click.prevent="showAllHeaders = !showAllHeaders" class="action-btn">{{ showAllHeaders ? 'hide' : 'all' }} headers</a>
          <router-link :to="`/thread/${encodeURIComponent(msg.message_id)}`" class="action-btn">thread</router-link>
          <a :href="`/api/raw?id=${encodeURIComponent(msg.message_id)}`" class="action-btn">raw</a>
          <a :href="`https://lore.kernel.org/${msg.inbox_name}/${msg.message_id}/`" target="_blank" rel="noopener" class="action-btn">lore</a>
          <template v-if="isPatch">
            <a :href="`/api/raw?id=${encodeURIComponent(msg.message_id)}&download=1`" class="action-btn">patch</a>
            <template v-if="seriesTotal > 1">
              <a :href="`/api/series?id=${encodeURIComponent(msg.message_id)}&download=1`" class="action-btn">series mbox</a>
            </template>
          </template>
          <template v-if="prevMessage || nextMessage">
            <span class="action-sep"></span>
            <router-link v-if="prevMessage" :to="`/message/${encodeURIComponent(prevMessage.message_id)}`" :title="prevMessage.subject" class="action-btn">&larr; prev</router-link>
            <router-link v-if="nextMessage" :to="`/message/${encodeURIComponent(nextMessage.message_id)}`" :title="nextMessage.subject" class="action-btn">next &rarr;</router-link>
          </template>
        </div>
      </div>

      <MessageBody :bodyText="msg.body_text" />

      <template v-if="msg.attachments && msg.attachments.length">
        <div class="msg-attachments">
          <strong>Attachments:</strong>
          <div v-for="att in msg.attachments" :key="att.id" class="attachment-item">
            {{ att.filename || '(unnamed)' }} ({{ att.content_type }}, {{ att.size }} bytes)
          </div>
        </div>
      </template>
    </template>
  </div>
</template>

<style scoped>
.msg-header-card {
  background: #fff;
  border: 1px solid #d1d9e0;
  border-radius: 10px;
  overflow: hidden;
  margin-bottom: 0;
  border-bottom-left-radius: 0;
  border-bottom-right-radius: 0;
}

.msg-breadcrumb {
  padding: 12px 16px;
  font-size: 13px;
  display: flex;
  gap: 6px;
  border-bottom: 1px solid #eef1f5;
  background: #f6f8fa;
}

.bc-sep { color: #8b949e; }

.msg-headers {
  padding: 12px 16px;
  font-size: 13px;
  line-height: 1.7;
}

.msg-actions {
  display: flex;
  gap: 4px;
  padding: 8px 16px;
  border-top: 1px solid #eef1f5;
  background: #f6f8fa;
  flex-wrap: wrap;
}

.action-btn {
  font-size: 12px;
  padding: 3px 10px;
  border: 1px solid #d1d9e0;
  border-radius: 6px;
  color: #656d76;
  text-decoration: none !important;
  transition: all 0.15s;
  white-space: nowrap;
}

.action-btn:hover {
  background: #eaeef2;
  border-color: #0969da;
  color: #0969da;
}

.action-sep {
  width: 1px;
  background: #d1d9e0;
  margin: 2px 4px;
}

.msg-attachments {
  margin-top: 12px;
  padding: 12px 16px;
  background: #fff;
  border: 1px solid #d1d9e0;
  border-radius: 10px;
  font-size: 13px;
}

.attachment-item {
  margin-top: 4px;
  color: #656d76;
}
</style>

<style>
html.dark .msg-header-card {
  background: #161b22;
  border-color: #30363d;
}
html.dark .msg-breadcrumb { background: #0d1117; border-color: #21262d; }
html.dark .msg-actions { background: #0d1117; border-color: #21262d; }
html.dark .action-btn { color: #8b949e; border-color: #30363d; }
html.dark .action-btn:hover { background: #21262d; border-color: #58a6ff; color: #58a6ff; }
html.dark .action-sep { background: #30363d; }
html.dark .msg-attachments { background: #161b22; border-color: #30363d; }
html.dark .attachment-item { color: #8b949e; }
</style>
