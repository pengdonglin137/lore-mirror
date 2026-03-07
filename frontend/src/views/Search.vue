<script setup>
import { ref, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { search, getInboxes } from '../api.js'
import { formatDate, shortenSender } from '../utils.js'
import SearchHelp from '../components/SearchHelp.vue'

const route = useRoute()
const router = useRouter()
const data = ref(null)
const loading = ref(false)
const error = ref(null)
const inboxes = ref([])
const selectedInbox = ref('')
const showHelp = ref(false)

onMounted(async () => {
  try {
    inboxes.value = await getInboxes()
  } catch {}
  selectedInbox.value = route.query.inbox || ''
})

async function doSearch() {
  const q = route.query.q
  if (!q) return

  const page = parseInt(route.query.page) || 1
  loading.value = true
  error.value = null
  try {
    data.value = await search(q, {
      inbox: route.query.inbox,
      page,
    })
    document.title = `search: ${q} — lore-mirror`
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

watch(() => [route.query.q, route.query.page, route.query.inbox], doSearch, { immediate: true })

function goPage(p) {
  router.push({ path: '/search', query: { ...route.query, page: p } })
}

function onInboxChange() {
  const query = { ...route.query, page: 1 }
  if (selectedInbox.value) {
    query.inbox = selectedInbox.value
  } else {
    delete query.inbox
  }
  router.push({ path: '/search', query })
}


</script>

<template>
  <div>
    <div class="search-controls">
      <select v-model="selectedInbox" @change="onInboxChange" class="inbox-select">
        <option value="">all inboxes</option>
        <option v-for="ib in inboxes" :key="ib.name" :value="ib.name">{{ ib.name }}</option>
      </select>
      <a href="#" @click.prevent="showHelp = !showHelp" class="help-toggle">[{{ showHelp ? 'hide' : 'search' }} help]</a>
    </div>

    <SearchHelp v-if="showHelp" />

    <pre v-if="!route.query.q">Enter a search query above.</pre>
    <pre v-else-if="loading" class="loading">Searching for "{{ route.query.q }}"...</pre>
    <pre v-else-if="error" class="error">Error: {{ error }}</pre>
    <template v-else-if="data">
      <pre>Search: "{{ data.query }}"<template v-if="route.query.inbox"> in {{ route.query.inbox }}</template> — {{ data.total }} results (page {{ data.page }}/{{ data.pages }})
</pre>
      <div class="pagination" v-if="data.pages > 1">
        <button :disabled="data.page <= 1" @click="goPage(data.page - 1)">&lt; prev</button>
        <span>page {{ data.page }} / {{ data.pages }}</span>
        <button :disabled="data.page >= data.pages" @click="goPage(data.page + 1)">next &gt;</button>
      </div>

      <div v-for="msg in data.messages" :key="msg.id" class="search-result">
        <pre><router-link :to="`/message/${encodeURIComponent(msg.message_id)}`">{{ msg.subject }}</router-link>
{{ formatDate(msg.date) }}  {{ shortenSender(msg.sender) }}  [{{ msg.inbox_name }}]
<span v-if="msg.snippet" v-html="msg.snippet" class="snippet"></span>
</pre>
      </div>

      <div class="pagination" v-if="data.pages > 1">
        <button :disabled="data.page <= 1" @click="goPage(data.page - 1)">&lt; prev</button>
        <span>page {{ data.page }} / {{ data.pages }}</span>
        <button :disabled="data.page >= data.pages" @click="goPage(data.page + 1)">next &gt;</button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.search-controls {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.inbox-select {
  font-family: monospace;
  font-size: 13px;
  padding: 2px 6px;
  border: 1px solid #999;
}

.help-toggle {
  font-size: 12px;
}

.search-result {
  border-bottom: 1px solid #eee;
  padding: 4px 0;
}
.search-result pre {
  font-size: 13px;
}
.snippet {
  color: #666;
}

</style>

<style>
html.dark .inbox-select { background: #21262d; color: #c9d1d9; border-color: #30363d; }
html.dark .search-help { background: #161b22; border-color: #30363d; color: #8b949e; }
html.dark .search-result { border-color: #21262d; }
html.dark .snippet { color: #8b949e; }
</style>
