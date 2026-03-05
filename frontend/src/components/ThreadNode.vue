<script>
export default {
  name: 'ThreadNode',
  props: ['node', 'depth', 'currentId'],
  computed: {
    indent() { return '  '.repeat(this.depth) }
  },
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
<span>{{ indent }}<router-link
  :to="'/message/' + encodeURIComponent(node.message_id)"
  :class="{ current: node.message_id === currentId }"
>{{ node.subject }}</router-link>
{{ indent }}  {{ formatDate(node.date) }} {{ shortenSender(node.sender) }}
<template v-for="child in node.children" :key="child.message_id"><ThreadNode :node="child" :depth="depth + 1" :currentId="currentId" /></template></span>
</template>
