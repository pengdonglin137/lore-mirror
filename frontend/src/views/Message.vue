<script setup>
import { ref, watch, computed, onMounted, onUnmounted } from 'vue'
import { getMessage, getThread } from '../api.js'
import { useRouter } from 'vue-router'
import { linkifyLine } from '../utils.js'

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
  expandedQuotes.value = new Set()
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
    return { key: k, value: val, ids }
  })
})

function formatBody(text) {
  if (!text) return ''
  return text
}

const trailerRe = /^(Signed-off-by|Reviewed-by|Acked-by|Tested-by|Reported-by|Suggested-by|Co-developed-by|Fixes|Cc|Link|Closes):/

function lineClass(line) {
  if (line.startsWith('diff --git')) return 'diff-header'
  if (line.startsWith('@@')) return 'diff-hunk'
  if (line.startsWith('+++') || line.startsWith('---')) return 'diff-file'
  if (line.startsWith('+')) return 'diff-add'
  if (line.startsWith('-')) return 'diff-del'
  if (line.startsWith('> >') || line.startsWith('>> ') || line.startsWith('>>>')) return 'quote-deep'
  if (line.startsWith('>')) return 'quote'
  if (trailerRe.test(line)) return 'trailer'
  return ''
}

const bodyLines = computed(() => {
  if (!msg.value?.body_text) return []
  return msg.value.body_text.split('\n')
})

// Group consecutive quote lines (>...) into collapsible blocks
const bodySegments = computed(() => {
  const lines = bodyLines.value
  const segments = []
  let i = 0
  while (i < lines.length) {
    if (lines[i].startsWith('>')) {
      const start = i
      while (i < lines.length && lines[i].startsWith('>')) i++
      segments.push({ type: 'quote', lines: lines.slice(start, i), id: start })
    } else {
      segments.push({ type: 'line', line: lines[i], id: i })
      i++
    }
  }
  return segments
})

const expandedQuotes = ref(new Set())

function toggleQuote(id) {
  if (expandedQuotes.value.has(id)) expandedQuotes.value.delete(id)
  else expandedQuotes.value.add(id)
}

const hasDiff = computed(() => {
  return bodyLines.value.some(l => l.startsWith('diff --git') || l.startsWith('---') || l.startsWith('@@'))
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
    <pre v-if="loading" class="loading">Loading...</pre>
    <pre v-else-if="error" class="error">Error: {{ error }}</pre>
    <template v-else-if="msg">
      <pre class="msg-header"><router-link to="/">lore-mirror</router-link> / <router-link :to="`/inbox/${msg.inbox_name}`">{{ msg.inbox_name }}</router-link>

<template v-for="h in headerLines" :key="h.key"><b>{{ h.key }}:</b> <template v-if="h.key === 'In-Reply-To' && h.value"><router-link :to="`/message/${encodeURIComponent(h.value.replace(/[<>]/g, ''))}`">{{ h.value }}</router-link></template><template v-else-if="h.ids && h.ids.length"><template v-for="(id, idx) in h.ids" :key="id"><template v-if="idx"> </template>&lt;<router-link :to="`/message/${encodeURIComponent(id)}`">{{ id }}</router-link>&gt;</template></template><template v-else>{{ h.value }}</template>
</template>
<a href="#" @click.prevent="showAllHeaders = !showAllHeaders">[{{ showAllHeaders ? 'hide' : 'show all' }} headers]</a>  <router-link :to="`/thread/${encodeURIComponent(msg.message_id)}`">[view thread]</router-link>  <a :href="`/api/raw?id=${encodeURIComponent(msg.message_id)}`">[raw]</a><template v-if="prevMessage || nextMessage">  <router-link v-if="prevMessage" :to="`/message/${encodeURIComponent(prevMessage.message_id)}`" :title="prevMessage.subject">[&larr; prev]</router-link><template v-if="prevMessage && nextMessage">  </template><router-link v-if="nextMessage" :to="`/message/${encodeURIComponent(nextMessage.message_id)}`" :title="nextMessage.subject">[next &rarr;]</router-link></template></pre>

      <pre class="msg-body"><template v-for="seg in bodySegments" :key="seg.id"><template v-if="seg.type === 'line'"><span :class="lineClass(seg.line)" v-html="linkifyLine(seg.line)"></span>
</template><template v-else-if="seg.lines.length < 4 || expandedQuotes.has(seg.id)"><template v-for="(line, j) in seg.lines" :key="seg.id + '-' + j"><span :class="lineClass(line)" v-html="linkifyLine(line)"></span>
</template></template><template v-else><span class="quote-collapsed" @click="toggleQuote(seg.id)"><span :class="lineClass(seg.lines[0])" v-html="linkifyLine(seg.lines[0])"></span>
<span class="quote-toggle">[{{ seg.lines.length - 1 }} more quoted lines — click to expand]</span>
</span></template></template></pre>

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
/* ── Light theme ── */
.msg-header {
  background: #f8f9fa;
  padding: 12px;
  border: 1px solid #ddd;
  border-left: 3px solid #00609f;
  margin-bottom: 0;
  border-bottom: none;
}

.msg-body {
  padding: 12px;
  border: 1px solid #e0e0e0;
  background: #fafafa;
  font-size: 13px;
}

.msg-attachments {
  margin-top: 0;
  padding: 8px 12px;
  background: #f9f9f0;
  border: 1px solid #ddd;
  border-top: 1px dashed #ccc;
}

.diff-add { color: #1a7f37; background: #dafbe1; }
.diff-del { color: #cf222e; background: #ffebe9; }
.diff-hunk { color: #6f42c1; background: #f4f0ff; }
.diff-header { color: #0550ae; font-weight: bold; }
.diff-file { color: #656d76; font-weight: bold; }
.quote { color: #57606a; border-left: 2px solid #d0d7de; padding-left: 6px; display: inline-block; }
.quote-deep { color: #8b949e; border-left: 2px solid #d0d7de; padding-left: 6px; display: inline-block; }
.trailer { color: #57606a; }
.quote-collapsed { cursor: pointer; }
.quote-toggle { color: #888; font-size: 12px; font-style: italic; }
.quote-toggle:hover { color: #00609f; text-decoration: underline; }

</style>

<style>
/* ── Dark theme (unscoped: html.dark is outside component) ── */
html.dark .msg-header {
  background: #21262d;
  border-color: #383e47;
  border-left: 3px solid #58a6ff;
}

html.dark .msg-body {
  background: #161b22;
  border-color: #30363d;
}

html.dark .msg-attachments {
  background: #1c2128;
  border-color: #30363d;
  border-top-color: #484f58;
}

html.dark .diff-add { color: #7ee787; background: #12261e; }
html.dark .diff-del { color: #ffa198; background: #2d1619; }
html.dark .diff-hunk { color: #d2a8ff; background: #1e1731; }
html.dark .diff-header { color: #79c0ff; }
html.dark .diff-file { color: #8b949e; }
html.dark .quote { color: #8b949e; border-left-color: #484f58; }
html.dark .quote-deep { color: #6e7681; border-left-color: #484f58; }
html.dark .trailer { color: #8b949e; }
html.dark .quote-toggle { color: #6e7681; }
html.dark .quote-toggle:hover { color: #58a6ff; }
</style>
