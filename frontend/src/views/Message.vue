<script setup>
import { ref, watch, computed } from 'vue'
import { getMessage } from '../api.js'

const props = defineProps(['id'])
const msg = ref(null)
const loading = ref(true)
const error = ref(null)
const showAllHeaders = ref(false)

async function load() {
  loading.value = true
  error.value = null
  try {
    msg.value = await getMessage(props.id)
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

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
<a href="#" @click.prevent="showAllHeaders = !showAllHeaders">[{{ showAllHeaders ? 'hide' : 'show all' }} headers]</a>  <router-link :to="`/thread/${encodeURIComponent(msg.message_id)}`">[view thread]</router-link>  <a :href="`/api/messages/${encodeURIComponent(msg.message_id)}/raw`">[raw]</a></pre>

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

@media (prefers-color-scheme: dark) {
  .msg-header { background: #252525; border-color: #444; }
  .msg-body { border-color: #333; }
  .msg-attachments { background: #2a2a20; border-color: #444; }
  .diff-add { color: #56d364; background: #0d1117; }
  .diff-del { color: #f85149; background: #1a0000; }
  .diff-hunk { color: #bc8cff; }
  .diff-header { color: #79c0ff; }
}
</style>
