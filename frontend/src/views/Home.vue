<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { getInboxes, getStats, triggerSync, getSyncStatus } from '../api.js'

const route = useRoute()
const allInboxes = ref([])
const stats = ref(null)
const loading = ref(true)
const syncStatus = ref(null)
const syncError = ref('')
let pollTimer = null

onMounted(async () => {
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

const filteredInboxes = computed(() => {
  if (!locateQuery.value) return allInboxes.value
  const q = locateQuery.value.toLowerCase()
  return allInboxes.value.filter(
    ib => ib.name.toLowerCase().includes(q) || (ib.description || '').toLowerCase().includes(q)
  )
})

async function doSync() {
  syncError.value = ''
  try {
    await triggerSync()
    startPolling()
  } catch (e) {
    syncError.value = e.message
  }
}

function startPolling() {
  stopPolling()
  pollTimer = setInterval(async () => {
    try {
      syncStatus.value = await getSyncStatus()
      if (!syncStatus.value.running) {
        stopPolling()
        // Refresh inbox data
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
      <pre>local kernel mailing list archive

<template v-if="stats">Total: {{ formatCount(stats.total_messages) }} messages in {{ stats.total_inboxes }} inbox(es)
Database: {{ formatSize(stats.database_size_bytes) }}
</template>
<template v-if="locateQuery">Matching inboxes for "{{ locateQuery }}" ({{ filteredInboxes.length }} results):
</template><template v-else>Inboxes:
</template><template v-if="filteredInboxes.length === 0">  No matching inboxes found.
</template><template v-for="inbox in filteredInboxes" :key="inbox.name">
* <router-link :to="`/inbox/${inbox.name}`">{{ inbox.name }}</router-link>
  {{ inbox.description }}
  {{ formatCount(inbox.message_count) }} messages ({{ formatDate(inbox.earliest) }} ~ {{ formatDate(inbox.latest) }})
</template></pre>

      <hr class="sep" />
      <div class="sync-section">
        <button
          class="sync-btn"
          :disabled="syncStatus?.running"
          @click="doSync"
        >{{ syncStatus?.running ? 'syncing...' : 'sync now' }}</button>
        <span v-if="syncStatus?.running" class="sync-info">
          syncing {{ syncStatus.current_inbox || '...' }}
          ({{ (syncStatus.completed || []).length }}/{{ syncStatus.total_inboxes }})
        </span>
        <span v-else-if="syncStatus?.finished_at" class="sync-info">
          last sync: {{ syncStatus.finished_at }}
        </span>
        <span v-if="syncError" class="sync-error">{{ syncError }}</span>
      </div>
    </template>
  </div>
</template>

<style scoped>
.sep {
  border: none;
  border-top: 1px solid #ddd;
  margin: 16px 0 12px;
}

.sync-section {
  display: flex;
  align-items: center;
  gap: 12px;
  font-family: monospace;
  font-size: 13px;
}

.sync-btn {
  font-family: monospace;
  font-size: 13px;
  padding: 3px 12px;
  cursor: pointer;
  border: 1px solid #999;
  background: #eee;
}

.sync-btn:disabled {
  opacity: 0.6;
  cursor: default;
}

.sync-info { color: #666; }
.sync-error { color: #c00; }

@media (prefers-color-scheme: dark) {
  .sep { border-color: #444; }
  .sync-btn { background: #333; color: #ddd; border-color: #555; }
  .sync-info { color: #999; }
}
</style>
