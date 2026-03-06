<script setup>
import { ref, watch, computed } from 'vue'
import { getMessage, getThread } from '../api.js'

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

const headerLines = computed(() => {
  if (!msg.value?.headers) return []
  const h = msg.value.headers
  const keys = showAllHeaders.value ? Object.keys(h) : importantHeaders.filter(k => h[k])
  return keys.map(k => {
    const val = Array.isArray(h[k]) ? h[k].join(', ') : h[k]
    return { key: k, value: val }
  })
})

function formatBody(text) {
  if (!text) return ''
  return text
}

function isDiffLine(line) {
  if (line.startsWith('+') && !line.startsWith('+++')) return 'diff-add'
  if (line.startsWith('-') && !line.startsWith('---')) return 'diff-del'
  if (line.startsWith('@@')) return 'diff-hunk'
  if (line.startsWith('diff --git')) return 'diff-header'
  return ''
}

const bodyLines = computed(() => {
  if (!msg.value?.body_text) return []
  return msg.value.body_text.split('\n')
})

const hasDiff = computed(() => {
  return bodyLines.value.some(l => l.startsWith('diff --git') || l.startsWith('---') || l.startsWith('@@'))
})
</script>

<template>
  <div>
    <pre v-if="loading" class="loading">Loading...</pre>
    <pre v-else-if="error" class="error">Error: {{ error }}</pre>
    <template v-else-if="msg">
      <pre class="msg-header"><router-link to="/">lore-mirror</router-link> / <router-link :to="`/inbox/${msg.inbox_name}`">{{ msg.inbox_name }}</router-link>

<template v-for="h in headerLines" :key="h.key"><b>{{ h.key }}:</b> <template v-if="h.key === 'In-Reply-To' && h.value"><router-link :to="`/message/${encodeURIComponent(h.value.replace(/[<>]/g, ''))}`">{{ h.value }}</router-link></template><template v-else>{{ h.value }}</template>
</template>
<a href="#" @click.prevent="showAllHeaders = !showAllHeaders">[{{ showAllHeaders ? 'hide' : 'show all' }} headers]</a>  <router-link :to="`/thread/${encodeURIComponent(msg.message_id)}`">[view thread]</router-link>  <a :href="`/api/raw?id=${encodeURIComponent(msg.message_id)}`">[raw]</a><template v-if="prevMessage || nextMessage">  <router-link v-if="prevMessage" :to="`/message/${encodeURIComponent(prevMessage.message_id)}`" :title="prevMessage.subject">[&larr; prev]</router-link><template v-if="prevMessage && nextMessage">  </template><router-link v-if="nextMessage" :to="`/message/${encodeURIComponent(nextMessage.message_id)}`" :title="nextMessage.subject">[next &rarr;]</router-link></template></pre>

      <pre class="msg-body"><template v-for="(line, i) in bodyLines" :key="i"><span :class="isDiffLine(line)">{{ line }}</span>
</template></pre>

      <template v-if="msg.attachments && msg.attachments.length">
        <pre class="msg-attachments">
<b>Attachments:</b>
<template v-for="att in msg.attachments" :key="att.id">  {{ att.filename || '(unnamed)' }} ({{ att.content_type }}, {{ att.size }} bytes)
</template></pre>
      </template>
    </template>
  </div>
</template>

<style scoped>
.msg-header {
  background: #f6f6f6;
  padding: 12px;
  border: 1px solid #ddd;
  margin-bottom: 8px;
}

.msg-body {
  padding: 12px;
  border: 1px solid #eee;
  font-size: 13px;
}

.msg-attachments {
  margin-top: 8px;
  padding: 8px 12px;
  background: #f9f9f0;
  border: 1px solid #ddd;
}

.diff-add { color: #22863a; background: #f0fff4; }
.diff-del { color: #cb2431; background: #ffeef0; }
.diff-hunk { color: #6f42c1; }
.diff-header { color: #005cc5; font-weight: bold; }

:global(html.dark) .msg-header { background: #252525; border-color: #444; }
:global(html.dark) .msg-body { border-color: #333; }
:global(html.dark) .msg-attachments { background: #2a2a20; border-color: #444; }
:global(html.dark) .diff-add { color: #56d364; background: #0d1117; }
:global(html.dark) .diff-del { color: #f85149; background: #1a0000; }
:global(html.dark) .diff-hunk { color: #bc8cff; }
:global(html.dark) .diff-header { color: #79c0ff; }
</style>
