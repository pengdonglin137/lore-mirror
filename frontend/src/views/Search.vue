<script setup>
import { ref, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { search, getInboxes } from '../api.js'
import { formatDate, shortenSender } from '../utils.js'
import SearchHelp from '../components/SearchHelp.vue'
import AddressLink from '../components/AddressLink.vue'

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

// Keep dropdown in sync with URL (e.g., after nav bar search loses inbox param)
watch(() => route.query.inbox, (val) => { selectedInbox.value = val || '' })

function goPage(p) {
  p = Math.max(1, Math.min(p, data.value?.pages || 1))
  router.push({ path: '/search', query: { ...route.query, page: p } })
}

const pageInput = ref('')

function onPageInput() {
  const p = parseInt(pageInput.value)
  if (p && p >= 1 && p <= (data.value?.pages || 1)) {
    goPage(p)
  }
  pageInput.value = ''
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
      <a href="#" @click.prevent="showHelp = !showHelp" class="help-toggle">{{ showHelp ? 'hide' : 'search' }} help</a>
    </div>

    <SearchHelp v-if="showHelp" />

    <div v-if="!route.query.q" class="empty-state">Enter a search query above.</div>
    <div v-else-if="loading" class="loading">Searching for "{{ route.query.q }}"...</div>
    <div v-else-if="error" class="error">Error: {{ error }}</div>
    <template v-else-if="data">
      <div v-if="data.search_type === 'semantic'" class="semantic-banner">
        No exact matches found. Showing semantically similar results.
      </div>
      <div class="search-summary">
        Search: "<strong>{{ data.query }}</strong>"<template v-if="route.query.inbox"> in {{ route.query.inbox }}</template> &mdash; {{ data.total }} results (page {{ data.page }}/{{ data.pages }})
      </div>

      <div class="pagination" v-if="data.pages > 1">
        <button :disabled="data.page <= 1" @click="goPage(1)" title="first page">|&lt;</button>
        <button :disabled="data.page <= 1" @click="goPage(data.page - 1)">&lt; prev</button>
        <button v-if="data.pages > 10" :disabled="data.page <= 10" @click="goPage(data.page - 10)">-10</button>
        <span>page <input class="page-input" :placeholder="data.page" v-model="pageInput" @keyup.enter="onPageInput" :size="String(data.pages).length + 1" title="type page number and press Enter"> / {{ data.pages }}</span>
        <button v-if="data.pages > 10" :disabled="data.page + 10 > data.pages" @click="goPage(data.page + 10)">+10</button>
        <button :disabled="data.page >= data.pages" @click="goPage(data.page + 1)">next &gt;</button>
        <button :disabled="data.page >= data.pages" @click="goPage(data.pages)" title="last page">&gt;|</button>
      </div>

      <div class="search-results">
        <div v-for="msg in data.messages" :key="msg.id" class="search-result">
          <div class="result-title">
            <router-link :to="`/message/${encodeURIComponent(msg.message_id)}`">{{ msg.subject }}</router-link>
          </div>
          <div class="result-meta">
            <span class="result-date">{{ formatDate(msg.date) }}</span>
            <AddressLink :address="msg.sender" short />
            <router-link :to="`/inbox/${msg.inbox_name}`" class="result-inbox">{{ msg.inbox_name }}</router-link>
            <span v-if="msg.score != null" class="result-score">score: {{ msg.score.toFixed(3) }}</span>
          </div>
          <div v-if="msg.snippet" v-html="msg.snippet" class="snippet"></div>
        </div>
      </div>

      <div class="pagination" v-if="data.pages > 1">
        <button :disabled="data.page <= 1" @click="goPage(1)" title="first page">|&lt;</button>
        <button :disabled="data.page <= 1" @click="goPage(data.page - 1)">&lt; prev</button>
        <button v-if="data.pages > 10" :disabled="data.page <= 10" @click="goPage(data.page - 10)">-10</button>
        <span>page <input class="page-input" :placeholder="data.page" v-model="pageInput" @keyup.enter="onPageInput" :size="String(data.pages).length + 1" title="type page number and press Enter"> / {{ data.pages }}</span>
        <button v-if="data.pages > 10" :disabled="data.page + 10 > data.pages" @click="goPage(data.page + 10)">+10</button>
        <button :disabled="data.page >= data.pages" @click="goPage(data.page + 1)">next &gt;</button>
        <button :disabled="data.page >= data.pages" @click="goPage(data.pages)" title="last page">&gt;|</button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.search-controls {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.inbox-select {
  font-family: inherit;
  font-size: 13px;
  padding: 5px 10px;
  border: 1px solid #d1d9e0;
  border-radius: 6px;
  background: #f6f8fa;
  color: #1f2328;
  outline: none;
  transition: border-color 0.15s;
}
.inbox-select:focus {
  border-color: #0969da;
}

.help-toggle {
  font-size: 12px;
  color: #656d76;
}

.empty-state {
  text-align: center;
  padding: 48px 0;
  color: #656d76;
}

.search-summary {
  font-size: 13px;
  color: #656d76;
  margin-bottom: 12px;
}

.semantic-banner {
  font-size: 13px;
  color: #9a6700;
  background: #fff8c5;
  border: 1px solid #f0d060;
  border-radius: 6px;
  padding: 8px 12px;
  margin-bottom: 12px;
}

.result-score {
  font-size: 11px;
  background: #ddf4ff;
  padding: 1px 6px;
  border-radius: 12px;
  color: #0969da;
}

.search-results {
  background: #fff;
  border: 1px solid #d1d9e0;
  border-radius: 10px;
  overflow: hidden;
}

.search-result {
  padding: 12px 16px;
  border-bottom: 1px solid #eef1f5;
  transition: background 0.1s;
}
.search-result:last-child { border-bottom: none; }
.search-result:hover { background: #f6f8fa; }

.result-title {
  font-size: 14px;
  margin-bottom: 4px;
}

.result-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 12px;
  color: #656d76;
}

.result-date { white-space: nowrap; }

.result-inbox {
  font-size: 11px;
  background: #eef1f5;
  padding: 1px 8px;
  border-radius: 12px;
  color: #656d76;
  text-decoration: none !important;
}
.result-inbox:hover {
  background: #d1d9e0;
}

.snippet {
  font-size: 12px;
  color: #656d76;
  margin-top: 6px;
  line-height: 1.5;
}
</style>

<style>
html.dark .inbox-select { background: #0d1117; color: #e6edf3; border-color: #30363d; }
html.dark .inbox-select:focus { border-color: #58a6ff; }
html.dark .search-results { background: #161b22; border-color: #30363d; }
html.dark .search-result { border-color: #21262d; }
html.dark .search-result:hover { background: #1c2128; }
html.dark .result-inbox { background: #21262d; color: #8b949e; }
html.dark .result-inbox:hover { background: #30363d; }
html.dark .snippet { color: #8b949e; }
html.dark .search-summary { color: #8b949e; }
html.dark .semantic-banner { background: #3d2e00; color: #d29922; border-color: #6e4b00; }
html.dark .result-score { background: #0c2d6b; color: #58a6ff; }
</style>
