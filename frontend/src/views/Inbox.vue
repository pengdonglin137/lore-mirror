<script setup>
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getInbox } from '../api.js'
import { formatDate, shortenSender } from '../utils.js'
import AddressLink from '../components/AddressLink.vue'

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
    <pre v-if="loading" class="loading">Loading...</pre>
    <pre v-else-if="error" class="error">Error: {{ error }}</pre>
    <template v-else-if="data">
      <pre><router-link to="/">lore-mirror</router-link> / <b>{{ data.inbox.name }}</b>  <router-link :to="`/search?q=&inbox=${data.inbox.name}`">[search this inbox]</router-link>
{{ data.inbox.description }}
{{ data.total }} messages — page {{ data.page }}/{{ data.pages }}
</pre>
      <div class="pagination">
        <button :disabled="page <= 1" @click="goPage(1)" title="first page">|&lt;</button>
        <button :disabled="page <= 1" @click="goPage(page - 1)">&lt; prev</button>
        <button v-if="data.pages > 10" :disabled="page <= 10" @click="goPage(page - 10)">-10</button>
        <span>page <input class="page-input" :placeholder="page" v-model="pageInput" @keyup.enter="onPageInput" :size="String(data.pages).length + 1" title="type page number and press Enter"> / {{ data.pages }}</span>
        <button v-if="data.pages > 10" :disabled="page + 10 > data.pages" @click="goPage(page + 10)">+10</button>
        <button :disabled="page >= data.pages" @click="goPage(page + 1)">next &gt;</button>
        <button :disabled="page >= data.pages" @click="goPage(data.pages, { last: true })" title="last page">&gt;|</button>
      </div>

      <pre class="message-list"><template v-for="msg in data.messages" :key="msg.id"
><span class="msg-date">{{ formatDate(msg.date) }}</span>  <span class="msg-sender"><AddressLink :address="msg.sender" short /></span>  <router-link :to="`/message/${encodeURIComponent(msg.message_id)}`">{{ msg.subject }}</router-link>
</template></pre>

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
.message-list {
  font-size: 13px;
  line-height: 1.6;
}
.msg-sender {
  display: inline-block;
  width: 30ch;
  overflow: visible;
  vertical-align: bottom;
}
.msg-sender :deep(.addr-link) {
  display: inline-block;
  max-width: 30ch;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: bottom;
}
</style>
