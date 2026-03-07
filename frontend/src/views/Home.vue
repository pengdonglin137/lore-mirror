<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { getInboxes, getStats, getSyncStatus } from '../api.js'

const route = useRoute()
const allInboxes = ref([])
const stats = ref(null)
const loading = ref(true)
const syncStatus = ref(null)
let pollTimer = null

onMounted(async () => {
  document.title = 'lore-mirror'
  try {
    const [inboxData, statsData, syncData] = await Promise.all([
      getInboxes(), getStats(), getSyncStatus(),
    ])
    allInboxes.value = inboxData
    stats.value = statsData
    syncStatus.value = syncData
    if (syncData.running) startPolling()
  } finally {
    loading.value = false
  }
})

onUnmounted(() => stopPolling())

const locateQuery = computed(() => route.query.locate || '')

const syncingInboxes = computed(() =>
  (syncStatus.value?.inboxes || []).filter(s => s.running)
)

const lastFinished = computed(() => {
  const finished = (syncStatus.value?.inboxes || []).filter(s => s.finished_at && !s.running)
  if (!finished.length) return null
  return finished.reduce((a, b) => (a.finished_at > b.finished_at ? a : b))
})

const filteredInboxes = computed(() => {
  if (!locateQuery.value) return allInboxes.value
  const q = locateQuery.value.toLowerCase()
  return allInboxes.value.filter(
    ib => ib.name.toLowerCase().includes(q) || (ib.description || '').toLowerCase().includes(q)
  )
})

function startPolling() {
  stopPolling()
  pollTimer = setInterval(async () => {
    try {
      syncStatus.value = await getSyncStatus()
      if (!syncStatus.value.running) {
        stopPolling()
        const [inboxData, statsData] = await Promise.all([getInboxes(), getStats()])
        allInboxes.value = inboxData
        stats.value = statsData
      }
    } catch {}
  }, 3000)
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

function formatCount(n) {
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'K'
  return n
}

function formatSize(bytes) {
  if (bytes >= 1e9) return (bytes / 1e9).toFixed(1) + ' GB'
  if (bytes >= 1e6) return (bytes / 1e6).toFixed(1) + ' MB'
  return (bytes / 1e3).toFixed(1) + ' KB'
}

function formatDate(d) {
  if (!d) return ''
  return d.slice(0, 10)
}
</script>

<template>
  <div>
    <pre v-if="loading" class="loading">Loading...</pre>
    <template v-else>
      <pre v-if="locateQuery">Matching inboxes for "{{ locateQuery }}" ({{ filteredInboxes.length }} results):
</pre>
      <pre><template v-if="filteredInboxes.length === 0">  No matching inboxes found.
</template><template v-for="inbox in filteredInboxes" :key="inbox.name">
<router-link :to="`/inbox/${inbox.name}`">{{ inbox.name.padEnd(24) }}</router-link> {{ formatCount(inbox.message_count).toString().padStart(7) }} msgs  {{ formatDate(inbox.earliest) }} ~ {{ formatDate(inbox.latest) }}
  <span class="inbox-desc">{{ inbox.description }}</span>
</template></pre>

      <div class="status-bar">
        <span v-if="stats">{{ formatCount(stats.total_messages) }} messages, {{ stats.total_inboxes }} inbox(es), {{ formatSize(stats.database_size_bytes) }}</span>
        <template v-if="syncStatus?.inboxes?.length">
          <span v-if="syncingInboxes.length">
            | syncing: {{ syncingInboxes.map(s => s.inbox).join(', ') }}
          </span>
          <span v-else-if="lastFinished">
            | last sync: {{ lastFinished.finished_at }}
          </span>
        </template>
      </div>
    </template>
  </div>
</template>

<style scoped>
.inbox-desc { color: #666; }

.status-bar {
  font-family: monospace;
  font-size: 12px;
  color: #888;
  border-top: 1px solid #ddd;
  margin-top: 12px;
  padding-top: 6px;
}

</style>

<style>
html.dark .status-bar { border-color: #30363d; color: #6e7681; }
html.dark .inbox-desc { color: #8b949e; }
</style>
