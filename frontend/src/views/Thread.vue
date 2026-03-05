<script setup>
import { ref, watch, computed } from 'vue'
import { getThread } from '../api.js'
import ThreadNode from '../components/ThreadNode.vue'

const props = defineProps(['id'])
const data = ref(null)
const loading = ref(true)
const error = ref(null)

async function load() {
  loading.value = true
  error.value = null
  try {
    data.value = await getThread(props.id)
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

watch(() => props.id, load, { immediate: true })

const tree = computed(() => {
  if (!data.value?.messages) return []
  const msgs = data.value.messages
  const byId = new Map(msgs.map(m => [m.message_id, { ...m, children: [] }]))

  const roots = []
  for (const m of byId.values()) {
    if (m.in_reply_to && byId.has(m.in_reply_to)) {
      byId.get(m.in_reply_to).children.push(m)
    } else {
      roots.push(m)
    }
  }
  return roots
})
</script>

<template>
  <div>
    <pre v-if="loading" class="loading">Loading...</pre>
    <pre v-else-if="error" class="error">Error: {{ error }}</pre>
    <template v-else-if="data">
      <pre><router-link to="/">lore-mirror</router-link> — thread ({{ data.total }} messages)
</pre>
      <div class="thread-tree">
        <ThreadNode
          v-for="node in tree"
          :key="node.message_id"
          :node="node"
          :depth="0"
          :currentId="props.id"
        />
      </div>
    </template>
  </div>
</template>

<style scoped>
.thread-tree {
  margin-top: 8px;
  font-family: monospace;
}
</style>
