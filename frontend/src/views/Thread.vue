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
    <pre v-if="loading" class="loading">Loading...</pre>
    <pre v-else-if="error" class="error">Error: {{ error }}</pre>
    <template v-else-if="data">
      <pre class="thread-header"><router-link to="/">lore-mirror</router-link><template v-if="inbox"> / <router-link :to="`/inbox/${inbox}`">{{ inbox }}</router-link></template> — thread ({{ data.total }} messages)

<span class="view-toggle">[<template v-for="(mode, i) in ['tree', 'flat', 'nested']" :key="mode"><template v-if="i"> | </template><a
  v-if="viewMode !== mode"
  href="#"
  @click.prevent="setView(mode)"
>{{ mode }}</a><b v-else>{{ mode }}</b></template>]</span>
</pre>

      <!-- Tree view (default) -->
      <div v-if="viewMode === 'tree'" class="thread-tree">
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
        <pre v-if="loadingFull" class="loading">Loading full thread...</pre>
        <div v-else class="thread-full">
          <div v-for="msg in flatMessages" :key="msg.message_id" class="thread-message">
            <div class="thread-msg-header"><AddressLink :address="msg.sender" context="header" /> <span class="thread-msg-date">{{ formatDate(msg.date) }}</span> <router-link :to="`/message/${encodeURIComponent(msg.message_id)}`" class="thread-msg-link">[message]</router-link> <a :href="`/api/raw?id=${encodeURIComponent(msg.message_id)}`" class="thread-msg-link">[raw]</a> <a :href="`https://lore.kernel.org/${inbox}/${msg.message_id}/`" target="_blank" rel="noopener" class="thread-msg-link">[lore]</a>
              <div v-if="msg.subject !== flatMessages[0]?.subject" class="thread-msg-subject">{{ msg.subject }}</div>
            </div>
            <MessageBody :bodyText="msg.body_text" />
          </div>
        </div>
      </template>

      <!-- Nested view -->
      <template v-else-if="viewMode === 'nested'">
        <pre v-if="loadingFull" class="loading">Loading full thread...</pre>
        <div v-else class="thread-full">
          <div
            v-for="msg in nestedMessages"
            :key="msg.message_id"
            class="thread-message"
            :style="{ marginLeft: (msg.depth * 24) + 'px' }"
          >
            <div class="thread-msg-header"><AddressLink :address="msg.sender" context="header" /> <span class="thread-msg-date">{{ formatDate(msg.date) }}</span> <router-link :to="`/message/${encodeURIComponent(msg.message_id)}`" class="thread-msg-link">[message]</router-link> <a :href="`/api/raw?id=${encodeURIComponent(msg.message_id)}`" class="thread-msg-link">[raw]</a> <a :href="`https://lore.kernel.org/${inbox}/${msg.message_id}/`" target="_blank" rel="noopener" class="thread-msg-link">[lore]</a>
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
.thread-tree {
  margin-top: 8px;
  font-family: monospace;
}

.thread-header {
  margin-bottom: 0;
}

.view-toggle a {
  cursor: pointer;
}

.thread-full {
  margin-top: 8px;
}

.thread-message {
  margin-bottom: 16px;
}

.thread-msg-header {
  background: #f8f9fa;
  padding: 6px 12px;
  border: 1px solid #ddd;
  border-left: 3px solid #00609f;
  margin-bottom: 0;
  border-bottom: none;
  font-family: monospace;
  font-size: 13px;
}

.thread-msg-date {
  color: #666;
}

.thread-msg-link {
  font-size: 12px;
  color: #888;
}

.thread-msg-subject {
  font-size: 12px;
  color: #555;
  margin-top: 2px;
}
</style>

<style>
html.dark .thread-msg-header {
  background: #21262d;
  border-color: #383e47;
  border-left: 3px solid #58a6ff;
}
html.dark .thread-msg-date { color: #8b949e; }
html.dark .thread-msg-link { color: #6e7681; }
html.dark .thread-msg-subject { color: #8b949e; }
</style>
