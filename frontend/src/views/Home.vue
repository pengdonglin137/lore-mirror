<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { getInboxes, getStats } from '../api.js'

const route = useRoute()
const allInboxes = ref([])
const stats = ref(null)
const loading = ref(true)

onMounted(async () => {
  try {
    const [inboxData, statsData] = await Promise.all([getInboxes(), getStats()])
    allInboxes.value = inboxData
    stats.value = statsData
  } finally {
    loading.value = false
  }
})

const locateQuery = computed(() => route.query.locate || '')

const filteredInboxes = computed(() => {
  if (!locateQuery.value) return allInboxes.value
  const q = locateQuery.value.toLowerCase()
  return allInboxes.value.filter(
    ib => ib.name.toLowerCase().includes(q) || (ib.description || '').toLowerCase().includes(q)
  )
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
    </template>
  </div>
</template>
