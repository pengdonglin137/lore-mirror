<script setup>
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getInbox } from '../api.js'
import { formatDate, shortenSender } from '../utils.js'
import AddressLink from '../components/AddressLink.vue'
import DateLink from '../components/DateLink.vue'

const props = defineProps(['name'])
const route = useRoute()
const router = useRouter()

const data = ref(null)
const loading = ref(true)
const error = ref(null)
const page = ref(1)

async function load() {
  loading.value = true
  error.value = null
  try {
    const p = parseInt(route.query.page) || 1
    const after = route.query.after || null
    const isLast = route.query.last === '1'
    data.value = await getInbox(props.name, { page: p, after, last: isLast })
    page.value = data.value.page  // server may adjust page number for last=1
    document.title = `${props.name} — lore-mirror`
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

watch(() => [props.name, route.query.page, route.query.after, route.query.last], load, { immediate: true })

function goPage(p, opts = {}) {
  const maxPage = data.value?.pages || 1
  p = Math.max(1, Math.min(p, maxPage))
  if (p === page.value && !opts.last) return
  // Use keyset cursor only for +1 (next page), otherwise fall back to offset
  if (p === page.value + 1 && data.value?.next_cursor) {
    router.push({ path: `/inbox/${props.name}`, query: { page: p, after: data.value.next_cursor } })
  } else if (opts.last) {
    router.push({ path: `/inbox/${props.name}`, query: { last: '1' } })
  } else {
    router.push({ path: `/inbox/${props.name}`, query: { page: p } })
  }
}

const pageInput = ref('')

function onPageInput(e) {
  const p = parseInt(pageInput.value)
  if (p && p >= 1 && p <= (data.value?.pages || 1)) {
    goPage(p)
  }
  pageInput.value = ''
}


</script>

<template>
  <div>
    <div v-if="loading" class="loading">Loading...</div>
    <div v-else-if="error" class="error">Error: {{ error }}</div>
    <template v-else-if="data">
      <div class="inbox-header-card">
        <div class="inbox-breadcrumb">
          <router-link to="/">lore-mirror</router-link>
          <span class="bc-sep">/</span>
          <strong>{{ data.inbox.name }}</strong>
          <router-link :to="`/search?q=&inbox=${data.inbox.name}`" class="inbox-search-link">search this inbox</router-link>
        </div>
        <div v-if="data.inbox.description" class="inbox-header-desc">{{ data.inbox.description }}</div>
        <div class="inbox-meta">{{ data.total }} messages &mdash; page {{ data.page }}/{{ data.pages }}</div>
      </div>

      <div class="pagination">
        <button :disabled="page <= 1" @click="goPage(1)" title="first page">|&lt;</button>
        <button :disabled="page <= 1" @click="goPage(page - 1)">&lt; prev</button>
        <button v-if="data.pages > 10" :disabled="page <= 10" @click="goPage(page - 10)">-10</button>
        <span>page <input class="page-input" :placeholder="page" v-model="pageInput" @keyup.enter="onPageInput" :size="String(data.pages).length + 1" title="type page number and press Enter"> / {{ data.pages }}</span>
        <button v-if="data.pages > 10" :disabled="page + 10 > data.pages" @click="goPage(page + 10)">+10</button>
        <button :disabled="page >= data.pages" @click="goPage(page + 1)">next &gt;</button>
        <button :disabled="page >= data.pages" @click="goPage(data.pages, { last: true })" title="last page">&gt;|</button>
      </div>

      <div class="message-list">
        <div v-for="msg in data.messages" :key="msg.id" class="msg-row">
          <span class="msg-date"><DateLink :date="msg.date" :inbox="props.name" /></span>
          <span class="msg-sender"><AddressLink :address="msg.sender" short /></span>
          <router-link :to="`/message/${encodeURIComponent(msg.message_id)}`" class="msg-subject">{{ msg.subject }}</router-link>
        </div>
      </div>

      <div class="pagination">
        <button :disabled="page <= 1" @click="goPage(1)" title="first page">|&lt;</button>
        <button :disabled="page <= 1" @click="goPage(page - 1)">&lt; prev</button>
        <button v-if="data.pages > 10" :disabled="page <= 10" @click="goPage(page - 10)">-10</button>
        <span>page <input class="page-input" :placeholder="page" v-model="pageInput" @keyup.enter="onPageInput" :size="String(data.pages).length + 1" title="type page number and press Enter"> / {{ data.pages }}</span>
        <button v-if="data.pages > 10" :disabled="page + 10 > data.pages" @click="goPage(page + 10)">+10</button>
        <button :disabled="page >= data.pages" @click="goPage(page + 1)">next &gt;</button>
        <button :disabled="page >= data.pages" @click="goPage(data.pages, { last: true })" title="last page">&gt;|</button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.inbox-header-card {
  background: #fff;
  border: 1px solid #d1d9e0;
  border-radius: 10px;
  padding: 16px 20px;
  margin-bottom: 16px;
}

.inbox-breadcrumb {
  font-size: 14px;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.bc-sep { color: #8b949e; }

.inbox-search-link {
  font-size: 12px;
  margin-left: auto;
  color: #656d76;
  border: 1px solid #d1d9e0;
  border-radius: 6px;
  padding: 2px 10px;
  transition: all 0.15s;
}
.inbox-search-link:hover {
  background: #f6f8fa;
  border-color: #0969da;
  color: #0969da;
  text-decoration: none;
}

.inbox-header-desc {
  font-size: 13px;
  color: #656d76;
  margin-top: 6px;
  line-height: 1.5;
}

.inbox-meta {
  font-size: 12px;
  color: #8b949e;
  margin-top: 8px;
}

/* ── Message list ────────────────────────────── */
.message-list {
  background: #fff;
  border: 1px solid #d1d9e0;
  border-radius: 10px;
}

.msg-row {
  display: grid;
  grid-template-columns: 19ch 20ch 1fr;
  gap: 0 1.5ch;
  padding: 6px 16px;
  font-size: 13px;
  line-height: 1.6;
  border-bottom: 1px solid #eef1f5;
  transition: background 0.1s;
}

.msg-row:last-child { border-bottom: none; }

.msg-row:hover {
  background: #f6f8fa;
}

.msg-date {
  white-space: nowrap;
  color: #8b949e;
}

.msg-sender {
  white-space: nowrap;
  overflow: visible;
  color: #1f2328;
  position: relative;
}

.msg-sender :deep(.addr-link) {
  color: #1f2328;
  font-weight: 500;
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: bottom;
}

.msg-sender :deep(.addr-link:hover) {
  color: #0969da;
}

.msg-subject {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
  color: #0969da;
}
</style>

<style>
html.dark .inbox-header-card {
  background: #161b22;
  border-color: #30363d;
}
html.dark .inbox-header-desc { color: #8b949e; }
html.dark .inbox-meta { color: #6e7681; }
html.dark .inbox-search-link { color: #8b949e; border-color: #30363d; }
html.dark .inbox-search-link:hover { background: #21262d; color: #58a6ff; border-color: #58a6ff; }

html.dark .message-list {
  background: #161b22;
  border-color: #30363d;
}
html.dark .msg-row { border-color: #21262d; }
html.dark .msg-row:hover { background: #1c2128; }
html.dark .msg-date { color: #6e7681; }
html.dark .msg-sender { color: #e6edf3; }
html.dark .msg-sender .addr-link { color: #e6edf3; }
html.dark .msg-sender .addr-link:hover { color: #58a6ff; }
html.dark .msg-subject { color: #58a6ff; }
</style>
