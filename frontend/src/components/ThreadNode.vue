<script>
export default {
  name: 'ThreadNode',
  props: ['node', 'depth', 'currentId'],
  methods: {
    formatDate(d) {
      if (!d) return ''
      return d.replace('T', ' ').slice(0, 19)
    },
    shortenSender(s) {
      if (!s) return ''
      const match = s.match(/^([^<]+)/)
      return match ? match[1].trim() : s
    }
  }
}
</script>

<template>
  <div class="thread-node" :class="{ 'thread-child': depth > 0 }">
    <div class="thread-entry">
      <router-link
        :to="'/message/' + encodeURIComponent(node.message_id)"
        :class="{ current: node.message_id === currentId }"
        class="thread-subject"
      >{{ node.subject }}</router-link>
      <span class="thread-meta">{{ formatDate(node.date) }} - {{ shortenSender(node.sender) }}</span>
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

@media (prefers-color-scheme: dark) {
  .thread-entry { border-color: #444; }
  .thread-meta { color: #999; }
  .current { background: #4a3f00; }
}
</style>
