<script setup>
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { search } from '../api.js'

const route = useRoute()
const router = useRouter()
const data = ref(null)
const loading = ref(false)
const error = ref(null)

async function doSearch() {
  const q = route.query.q
  if (!q) return

  const page = parseInt(route.query.page) || 1
  loading.value = true
  error.value = null
  try {
    data.value = await search(q, {
      inbox: route.query.inbox,
      sender: route.query.sender,
      dateFrom: route.query.date_from,
      dateTo: route.query.date_to,
      page,
    })
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

function formatDate(d) {
  if (!d) return ''
  return d.replace('T', ' ').slice(0, 19)
}

function shortenSender(s) {
  if (!s) return ''
  const match = s.match(/^([^<]+)/)
  return match ? match[1].trim() : s
}
</script>

<template>
  <div>
    <pre v-if="!route.query.q">Enter a search query above.</pre>
    <pre v-else-if="loading" class="loading">Searching for "{{ route.query.q }}"...</pre>
    <pre v-else-if="error" class="error">Error: {{ error }}</pre>
    <template v-else-if="data">
      <pre>Search: "{{ data.query }}" — {{ data.total }} results (page {{ data.page }}/{{ data.pages }})
</pre>
      <div class="pagination" v-if="data.pages > 1">
        <button :disabled="data.page <= 1" @click="goPage(data.page - 1)">&lt; prev</button>
        <span>page {{ data.page }} / {{ data.pages }}</span>
        <button :disabled="data.page >= data.pages" @click="goPage(data.page + 1)">next &gt;</button>
      </div>

      <div v-for="msg in data.messages" :key="msg.id" class="search-result">
        <pre><router-link :to="`/message/${encodeURIComponent(msg.message_id)}`">{{ msg.subject }}</router-link>
{{ formatDate(msg.date) }}  {{ shortenSender(msg.sender) }}  [{{ msg.inbox_name }}]
<span v-html="msg.snippet" class="snippet"></span>
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

@media (prefers-color-scheme: dark) {
  .search-result { border-color: #333; }
  .snippet { color: #999; }
}
</style>
