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
  margin-left: 20px;
}

.thread-entry {
  padding: 5px 10px;
  border-left: 2px solid #d1d9e0;
  margin: 2px 0;
  border-radius: 0 6px 6px 0;
  transition: background 0.1s;
}

.thread-entry:hover {
  background: #f6f8fa;
}

.thread-subject {
  display: block;
  font-size: 13px;
}

.thread-meta {
  display: block;
  font-size: 12px;
  color: #656d76;
  margin-top: 1px;
}

.current {
  font-weight: bold;
  background: #ddf4ff;
  padding: 2px 6px;
  border-radius: 4px;
  display: inline;
}

</style>

<style>
html.dark .thread-entry { border-color: #30363d; }
html.dark .thread-entry:hover { background: #1c2128; }
html.dark .thread-meta { color: #8b949e; }
html.dark .current { background: #0d2744; color: #58a6ff; }
</style>
