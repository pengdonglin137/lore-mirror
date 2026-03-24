<script setup>
import { ref, computed, onMounted } from 'vue'
import { getDatabaseStats } from '../api.js'

const data = ref(null)
const loading = ref(true)
const error = ref(null)
const sortBy = ref('size')  // 'size' | 'count' | 'name' | 'latest'

onMounted(async () => {
  document.title = 'Databases - lore-mirror'
  try {
    data.value = await getDatabaseStats()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})

function formatSize(bytes) {
  if (bytes >= 1e9) return (bytes / 1e9).toFixed(1) + ' GB'
  if (bytes >= 1e6) return (bytes / 1e6).toFixed(1) + ' MB'
  if (bytes >= 1e3) return (bytes / 1e3).toFixed(1) + ' KB'
  return bytes + ' B'
}

function formatCount(n) {
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'K'
  return String(n)
}

function formatDate(d) {
  if (!d) return '-'
  return d.slice(0, 10)
}

const maxSize = computed(() => {
  if (!data.value?.inboxes?.length) return 1
  return Math.max(...data.value.inboxes.map(i => i.size_bytes), 1)
})

const maxCount = computed(() => {
  if (!data.value?.inboxes?.length) return 1
  return Math.max(...data.value.inboxes.map(i => i.message_count), 1)
})

const sorted = computed(() => {
  if (!data.value?.inboxes) return []
  const list = [...data.value.inboxes]
  switch (sortBy.value) {
    case 'size': return list.sort((a, b) => b.size_bytes - a.size_bytes)
    case 'count': return list.sort((a, b) => b.message_count - a.message_count)
    case 'name': return list.sort((a, b) => a.name.localeCompare(b.name))
    case 'latest': return list.sort((a, b) => (b.latest || '').localeCompare(a.latest || ''))
    default: return list
  }
})
</script>

<template>
  <div>
    <div v-if="loading" class="loading">Loading database info...</div>
    <div v-else-if="error" class="error">Error: {{ error }}</div>
    <template v-else-if="data">

      <!-- Summary -->
      <div class="db-summary">
        <div class="summary-card">
          <div class="summary-value">{{ data.total_inboxes }}</div>
          <div class="summary-label">databases</div>
        </div>
        <div class="summary-card">
          <div class="summary-value">{{ formatCount(data.total_messages) }}</div>
          <div class="summary-label">messages</div>
        </div>
        <div class="summary-card accent">
          <div class="summary-value">{{ formatSize(data.total_size_bytes) }}</div>
          <div class="summary-label">total size</div>
        </div>
      </div>

      <!-- Sort controls -->
      <div class="sort-bar">
        Sort by:
        <button v-for="s in [{k:'size',l:'Size'},{k:'count',l:'Messages'},{k:'name',l:'Name'},{k:'latest',l:'Recent'}]"
          :key="s.k" class="sort-btn" :class="{ active: sortBy === s.k }" @click="sortBy = s.k">{{ s.l }}</button>
      </div>

      <!-- Inbox table -->
      <div class="db-table">
        <div class="db-header">
          <span class="col-name">Inbox</span>
          <span class="col-size">DB Size</span>
          <span class="col-bar"></span>
          <span class="col-count">Messages</span>
          <span class="col-earliest">Earliest</span>
          <span class="col-latest">Latest</span>
        </div>
        <div v-for="inbox in sorted" :key="inbox.name" class="db-row">
          <span class="col-name">
            <router-link :to="`/inbox/${inbox.name}`">{{ inbox.name }}</router-link>
          </span>
          <span class="col-size">{{ formatSize(inbox.size_bytes) }}</span>
          <span class="col-bar">
            <span class="bar-track">
              <span class="bar-fill size-fill" :style="{ width: (inbox.size_bytes / maxSize * 100) + '%' }"></span>
            </span>
          </span>
          <span class="col-count">{{ formatCount(inbox.message_count) }}</span>
          <span class="col-earliest">{{ formatDate(inbox.earliest) }}</span>
          <span class="col-latest">{{ formatDate(inbox.latest) }}</span>
        </div>
      </div>

    </template>
  </div>
</template>

<style scoped>
.db-summary {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.summary-card {
  background: #fff;
  border: 1px solid #d1d9e0;
  border-radius: 10px;
  padding: 16px 28px;
  text-align: center;
  flex: 1;
  min-width: 120px;
  max-width: 200px;
}

.summary-card.accent {
  border-color: #0969da;
  background: #ddf4ff;
}

.summary-value {
  font-size: 24px;
  font-weight: 700;
  color: #1f2328;
}

.summary-label {
  font-size: 12px;
  color: #656d76;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-top: 2px;
}

/* ── Sort ────────────────────────────────────── */
.sort-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 12px;
  font-size: 13px;
  color: #656d76;
}

.sort-btn {
  font-family: inherit;
  font-size: 12px;
  padding: 3px 10px;
  border: 1px solid #d1d9e0;
  border-radius: 6px;
  background: #f6f8fa;
  color: #656d76;
  cursor: pointer;
  transition: all 0.15s;
}
.sort-btn:hover { background: #eaeef2; border-color: #c4ccd4; }
.sort-btn.active { background: #0969da; color: #fff; border-color: #0969da; }

/* ── Table ───────────────────────────────────── */
.db-table {
  background: #fff;
  border: 1px solid #d1d9e0;
  border-radius: 10px;
}

.db-header, .db-row {
  display: grid;
  grid-template-columns: minmax(140px, 1fr) 80px 120px 80px 90px 90px;
  gap: 0 12px;
  padding: 8px 16px;
  align-items: center;
  font-size: 13px;
}

.db-header {
  font-weight: 600;
  color: #656d76;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.3px;
  border-bottom: 2px solid #d1d9e0;
  background: #f6f8fa;
  border-radius: 10px 10px 0 0;
}

.db-row {
  border-bottom: 1px solid #eef1f5;
  transition: background 0.1s;
}
.db-row:last-child { border-bottom: none; }
.db-row:hover { background: #f6f8fa; }

.col-size, .col-count {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.col-earliest, .col-latest {
  text-align: right;
  color: #8b949e;
  font-size: 12px;
}

.col-bar {
  display: flex;
  align-items: center;
}

.bar-track {
  width: 100%;
  height: 6px;
  background: #eef1f5;
  border-radius: 3px;
  overflow: hidden;
}

.bar-fill {
  display: block;
  height: 100%;
  border-radius: 3px;
  transition: width 0.3s;
}

.size-fill {
  background: linear-gradient(90deg, #0969da, #54aeff);
}
</style>

<style>
html.dark .summary-card { background: #161b22; border-color: #30363d; }
html.dark .summary-card.accent { background: #0d2744; border-color: #388bfd; }
html.dark .summary-value { color: #e6edf3; }
html.dark .summary-label { color: #8b949e; }
html.dark .sort-btn { background: #21262d; color: #8b949e; border-color: #30363d; }
html.dark .sort-btn:hover { background: #30363d; }
html.dark .sort-btn.active { background: #388bfd; color: #fff; border-color: #388bfd; }
html.dark .db-table { background: #161b22; border-color: #30363d; }
html.dark .db-header { background: #0d1117; border-color: #30363d; color: #8b949e; }
html.dark .db-row { border-color: #21262d; }
html.dark .db-row:hover { background: #1c2128; }
html.dark .col-earliest, html.dark .col-latest { color: #6e7681; }
html.dark .bar-track { background: #21262d; }
html.dark .size-fill { background: linear-gradient(90deg, #388bfd, #58a6ff); }
</style>
