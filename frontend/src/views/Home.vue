<script setup>
import { ref, onMounted } from 'vue'
import { getInboxes, getStats } from '../api.js'

const inboxes = ref([])
const stats = ref(null)
const loading = ref(true)

onMounted(async () => {
  try {
    const [inboxData, statsData] = await Promise.all([getInboxes(), getStats()])
    inboxes.value = inboxData
    stats.value = statsData
  } finally {
    loading.value = false
  }
})

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
      <pre>
<b>lore-mirror</b> — local kernel mailing list archive

<template v-if="stats">Total: {{ formatCount(stats.total_messages) }} messages in {{ stats.total_inboxes }} inbox(es)
Database: {{ formatSize(stats.database_size_bytes) }}
</template>
Inboxes:
<template v-for="inbox in inboxes" :key="inbox.id">
* <router-link :to="`/inbox/${inbox.name}`">{{ inbox.name }}</router-link>
  {{ inbox.description }}
  {{ formatCount(inbox.message_count) }} messages ({{ formatDate(inbox.earliest) }} ~ {{ formatDate(inbox.latest) }})
</template></pre>
    </template>
  </div>
</template>
