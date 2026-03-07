<script setup>
import { formatDate, shortenSender } from '../utils.js'
import AddressLink from './AddressLink.vue'

defineProps(['node', 'depth', 'currentId'])
</script>
<script>
export default { name: 'ThreadNode' }
</script>

<template>
  <div class="thread-node" :class="{ 'thread-child': depth > 0 }">
    <div class="thread-entry">
      <router-link
        :to="'/message/' + encodeURIComponent(node.message_id)"
        :class="{ current: node.message_id === currentId }"
        class="thread-subject"
      >{{ node.subject }}</router-link>
      <span class="thread-meta">{{ formatDate(node.date) }} - <AddressLink :address="node.sender" short /></span>
    </div>
    <ThreadNode
      v-for="child in node.children"
      :key="child.message_id"
      :node="child"
      :depth="depth + 1"
      :currentId="currentId"
    />
  </div>
</template>

<style scoped>
.thread-child {
  margin-left: 16px;
}

.thread-entry {
  padding: 3px 0;
  border-left: 2px solid #ddd;
  padding-left: 8px;
  margin: 2px 0;
}

.thread-subject {
  display: block;
  font-family: monospace;
  font-size: 13px;
}

.thread-meta {
  display: block;
  font-family: monospace;
  font-size: 12px;
  color: #666;
}

.current {
  font-weight: bold;
  background: #fff3cd;
  padding: 1px 4px;
}

</style>

<style>
html.dark .thread-entry { border-color: #30363d; }
html.dark .thread-meta { color: #8b949e; }
html.dark .current { background: #2d2a00; color: #e3b341; }
</style>
