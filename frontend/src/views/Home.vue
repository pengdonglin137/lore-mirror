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

// Relative activity bar width based on max message count
const maxCount = computed(() => {
  const counts = filteredInboxes.value.map(ib => ib.message_count)
  return Math.max(...counts, 1)
})
</script>

<template>
  <div>
    <div v-if="loading" class="loading">Loading...</div>
    <template v-else>

      <!-- Stats summary cards -->
      <div v-if="stats" class="summary-row">
        <div class="summary-card">
          <div class="summary-value">{{ formatCount(stats.total_messages) }}</div>
          <div class="summary-label">messages</div>
        </div>
        <div class="summary-card">
          <div class="summary-value">{{ stats.total_inboxes }}</div>
          <div class="summary-label">inboxes</div>
        </div>
        <div class="summary-card">
          <div class="summary-value">{{ formatSize(stats.database_size_bytes) }}</div>
          <div class="summary-label">database</div>
        </div>
        <div v-if="syncingInboxes.length" class="summary-card syncing">
          <div class="summary-value">{{ syncingInboxes.length }}</div>
          <div class="summary-label">syncing</div>
        </div>
        <div v-else-if="lastFinished" class="summary-card">
          <div class="summary-value">{{ lastFinished.finished_at?.slice(11, 16) || '--' }}</div>
          <div class="summary-label">last sync</div>
        </div>
      </div>

      <!-- Filter info -->
      <div v-if="locateQuery" class="filter-bar">
        Matching "<strong>{{ locateQuery }}</strong>" &mdash; {{ filteredInboxes.length }} results
      </div>

      <!-- No results -->
      <div v-if="filteredInboxes.length === 0" class="empty-state">
        No matching inboxes found.
      </div>

      <!-- Inbox card grid -->
      <div class="inbox-grid">
        <router-link
          v-for="inbox in filteredInboxes"
          :key="inbox.name"
          :to="`/inbox/${inbox.name}`"
          class="inbox-card"
        >
          <div class="inbox-card-header">
            <span class="inbox-name">{{ inbox.name }}</span>
            <span class="inbox-count">{{ formatCount(inbox.message_count) }}</span>
          </div>
          <div class="inbox-desc" v-if="inbox.description">{{ inbox.description }}</div>
          <div class="inbox-card-footer">
            <span class="inbox-dates">{{ formatDate(inbox.earliest) }} ~ {{ formatDate(inbox.latest) }}</span>
            <div class="inbox-bar-track">
              <div class="inbox-bar-fill" :style="{ width: (inbox.message_count / maxCount * 100) + '%' }"></div>
            </div>
          </div>
        </router-link>
      </div>
    </template>
  </div>
</template>

<style scoped>
/* ── Summary Cards ───────────────────────────── */
.summary-row {
  display: flex;
  gap: 12px;
  margin-bottom: 24px;
  flex-wrap: wrap;
}

.summary-card {
  background: #fff;
  border: 1px solid #d1d9e0;
  border-radius: 10px;
  padding: 16px 24px;
  min-width: 120px;
  flex: 1;
  text-align: center;
  transition: box-shadow 0.2s;
}

.summary-card:hover {
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}

.summary-card.syncing {
  border-color: #0969da;
  background: #ddf4ff;
}

.summary-value {
  font-size: 24px;
  font-weight: 700;
  color: #1f2328;
  line-height: 1.2;
}

.summary-label {
  font-size: 12px;
  color: #656d76;
  margin-top: 2px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

/* ── Filter bar ──────────────────────────────── */
.filter-bar {
  background: #ddf4ff;
  border: 1px solid #a8d4f5;
  border-radius: 8px;
  padding: 10px 16px;
  margin-bottom: 16px;
  font-size: 13px;
  color: #0969da;
}

.empty-state {
  text-align: center;
  padding: 48px 0;
  color: #656d76;
  font-size: 15px;
}

/* ── Inbox Cards Grid ────────────────────────── */
.inbox-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 12px;
}

.inbox-card {
  display: block;
  background: #fff;
  border: 1px solid #d1d9e0;
  border-radius: 10px;
  padding: 16px;
  text-decoration: none !important;
  color: inherit;
  transition: border-color 0.15s, box-shadow 0.15s, transform 0.15s;
}

.inbox-card:hover {
  border-color: #0969da;
  box-shadow: 0 4px 12px rgba(9,105,218,0.1);
  transform: translateY(-1px);
}

.inbox-card-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 6px;
}

.inbox-name {
  font-weight: 700;
  font-size: 15px;
  color: #0969da;
}

.inbox-count {
  font-size: 13px;
  font-weight: 600;
  color: #656d76;
  background: #eef1f5;
  padding: 1px 8px;
  border-radius: 12px;
}

.inbox-desc {
  font-size: 12px;
  color: #656d76;
  line-height: 1.5;
  margin-bottom: 10px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.inbox-card-footer {
  display: flex;
  align-items: center;
  gap: 12px;
}

.inbox-dates {
  font-size: 11px;
  color: #8b949e;
  white-space: nowrap;
}

.inbox-bar-track {
  flex: 1;
  height: 4px;
  background: #eef1f5;
  border-radius: 2px;
  overflow: hidden;
}

.inbox-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, #0969da, #54aeff);
  border-radius: 2px;
  transition: width 0.3s ease;
}
</style>

<style>
/* ── Dark theme ──────────────────────────────── */
html.dark .summary-card {
  background: #161b22;
  border-color: #30363d;
}
html.dark .summary-card:hover {
  box-shadow: 0 2px 8px rgba(0,0,0,0.2);
}
html.dark .summary-card.syncing {
  background: #0d2744;
  border-color: #388bfd;
}
html.dark .summary-value { color: #e6edf3; }
html.dark .summary-label { color: #8b949e; }

html.dark .filter-bar {
  background: #0d2744;
  border-color: #1f6feb;
  color: #58a6ff;
}

html.dark .empty-state { color: #8b949e; }

html.dark .inbox-card {
  background: #161b22;
  border-color: #30363d;
}
html.dark .inbox-card:hover {
  border-color: #58a6ff;
  box-shadow: 0 4px 12px rgba(88,166,255,0.08);
}
html.dark .inbox-name { color: #58a6ff; }
html.dark .inbox-count {
  color: #8b949e;
  background: #21262d;
}
html.dark .inbox-desc { color: #8b949e; }
html.dark .inbox-dates { color: #6e7681; }
html.dark .inbox-bar-track { background: #21262d; }
html.dark .inbox-bar-fill { background: linear-gradient(90deg, #388bfd, #58a6ff); }
</style>
