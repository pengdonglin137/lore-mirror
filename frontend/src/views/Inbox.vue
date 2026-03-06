<script setup>
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getInbox } from '../api.js'

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
    data.value = await getInbox(props.name, { page: p, after })
    page.value = p
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

watch(() => [props.name, route.query.page, route.query.after], load, { immediate: true })

function goNext() {
  if (data.value?.next_cursor) {
    router.push({ path: `/inbox/${props.name}`, query: { page: page.value + 1, after: data.value.next_cursor } })
  }
}

function goPrev() {
  if (page.value > 1) {
    router.push({ path: `/inbox/${props.name}`, query: { page: page.value - 1 } })
  }
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
    <pre v-if="loading" class="loading">Loading...</pre>
    <pre v-else-if="error" class="error">Error: {{ error }}</pre>
    <template v-else-if="data">
      <pre><router-link to="/">lore-mirror</router-link> / <b>{{ data.inbox.name }}</b>
{{ data.inbox.description }}
{{ data.total }} messages — page {{ data.page }}/{{ data.pages }}
</pre>
      <div class="pagination">
        <button :disabled="page <= 1" @click="goPrev">&lt; prev</button>
        <span>page {{ page }} / {{ data.pages }}</span>
        <button :disabled="!data.next_cursor" @click="goNext">next &gt;</button>
      </div>

      <pre class="message-list"><template v-for="msg in data.messages" :key="msg.id"
>{{ formatDate(msg.date) }}  {{ shortenSender(msg.sender).padEnd(30).slice(0,30) }}  <router-link :to="`/message/${encodeURIComponent(msg.message_id)}`">{{ msg.subject }}</router-link>
</template></pre>

      <div class="pagination">
        <button :disabled="page <= 1" @click="goPrev">&lt; prev</button>
        <span>page {{ page }} / {{ data.pages }}</span>
        <button :disabled="!data.next_cursor" @click="goNext">next &gt;</button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.message-list {
  font-size: 13px;
  line-height: 1.6;
}
</style>
