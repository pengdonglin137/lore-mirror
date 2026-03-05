<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { getInboxes, getStats, locateInbox } from '../api.js'

const router = useRouter()
const inboxes = ref([])
const stats = ref(null)
const loading = ref(true)
const homeQuery = ref('')
const locateResults = ref(null)

onMounted(async () => {
  try {
    const [inboxData, statsData] = await Promise.all([getInboxes(), getStats()])
    inboxes.value = inboxData
    stats.value = statsData
  } finally {
    loading.value = false
  }
})

async function doLocate() {
  if (!homeQuery.value.trim()) return
  locateResults.value = null
  const data = await locateInbox(homeQuery.value.trim())
  locateResults.value = data.matches
}

function doSearchAll() {
  if (!homeQuery.value.trim()) return
  router.push({ path: '/search', query: { q: homeQuery.value.trim() } })
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
      <div class="home-search">
        <input
          v-model="homeQuery"
          type="text"
          placeholder="Search..."
          class="home-input"
          @keyup.enter="doSearchAll"
        />
        <button class="home-btn" @click="doLocate">locate inbox</button>
        <button class="home-btn" @click="doSearchAll">search all inboxes</button>
      </div>

      <div v-if="locateResults !== null" class="locate-results">
        <pre v-if="locateResults.length === 0">No matching inboxes found.</pre>
        <pre v-else><template v-for="m in locateResults" :key="m.name">* <router-link :to="`/inbox/${m.name}`">{{ m.name }}</router-link>  {{ m.description }}
</template></pre>
      </div>

      <pre>
<b>lore-mirror</b> — local kernel mailing list archive

<template v-if="stats">Total: {{ formatCount(stats.total_messages) }} messages in {{ stats.total_inboxes }} inbox(es)
Database: {{ formatSize(stats.database_size_bytes) }}
</template>
Inboxes:
<template v-for="inbox in inboxes" :key="inbox.name">
* <router-link :to="`/inbox/${inbox.name}`">{{ inbox.name }}</router-link>
  {{ inbox.description }}
  {{ formatCount(inbox.message_count) }} messages ({{ formatDate(inbox.earliest) }} ~ {{ formatDate(inbox.latest) }})
</template></pre>
    </template>
  </div>
</template>

<style scoped>
.home-search {
  display: flex;
  gap: 4px;
  margin-bottom: 12px;
  align-items: center;
}

.home-input {
  font-family: monospace;
  font-size: 14px;
  padding: 4px 8px;
  border: 1px solid #999;
  flex: 0 1 300px;
}

.home-btn {
  font-family: monospace;
  font-size: 14px;
  padding: 4px 12px;
  cursor: pointer;
  border: 1px solid #999;
  background: #eee;
  white-space: nowrap;
}

.locate-results {
  margin-bottom: 12px;
  padding: 8px;
  background: #f9f9f9;
  border: 1px solid #ddd;
}

@media (prefers-color-scheme: dark) {
  .home-input, .home-btn { background: #333; color: #ddd; border-color: #555; }
  .locate-results { background: #252525; border-color: #444; }
}
</style>
