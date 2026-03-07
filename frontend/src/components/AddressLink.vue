<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'

const props = defineProps({
  // Full address string, e.g. "Linus Torvalds <torvalds@linux-foundation.org>"
  address: { type: String, required: true },
  // Show shortened name only (for list views)
  short: { type: Boolean, default: false },
  // Which search prefixes to show in menu
  context: { type: String, default: 'from' }, // 'from' | 'header'
})

const router = useRouter()
const showMenu = ref(false)
const menuEl = ref(null)

const parsed = computed(() => {
  const m = props.address.match(/^([^<]*)<([^>]+)>/)
  if (m) return { name: m[1].trim(), email: m[2].trim() }
  // Bare email
  if (props.address.includes('@')) return { name: '', email: props.address.trim() }
  return { name: props.address.trim(), email: '' }
})

const displayText = computed(() => {
  if (props.short) {
    return parsed.value.name || parsed.value.email
  }
  return props.address
})

const searchAddr = computed(() => parsed.value.email || parsed.value.name)

function doSearch(prefix) {
  showMenu.value = false
  router.push({ path: '/search', query: { q: `${prefix}:${searchAddr.value}` } })
}

function onClick(e) {
  e.preventDefault()
  e.stopPropagation()
  showMenu.value = !showMenu.value
}

function onClickOutside(e) {
  if (menuEl.value && !menuEl.value.contains(e.target)) {
    showMenu.value = false
  }
}

onMounted(() => document.addEventListener('click', onClickOutside, true))
onUnmounted(() => document.removeEventListener('click', onClickOutside, true))
</script>

<template>
  <span class="addr-wrap" ref="menuEl">
    <a href="#" class="addr-link" @click="onClick">{{ displayText }}</a>
    <span v-if="showMenu" class="addr-menu">
      <a href="#" @click.prevent="doSearch('f')">f: from this sender</a>
      <a href="#" @click.prevent="doSearch('a')">a: any address field</a>
      <a v-if="context === 'header'" href="#" @click.prevent="doSearch('t')">t: in To</a>
      <a v-if="context === 'header'" href="#" @click.prevent="doSearch('c')">c: in Cc</a>
    </span>
  </span>
</template>

<style scoped>
.addr-wrap {
  position: relative;
  display: inline;
}
.addr-link {
  cursor: pointer;
  border-bottom: 1px dashed #999;
  text-decoration: none;
}
.addr-link:hover {
  text-decoration: none;
  border-bottom-color: #00609f;
}
.addr-menu {
  position: absolute;
  left: 0;
  top: 1.4em;
  z-index: 50;
  background: #fff;
  border: 1px solid #ccc;
  box-shadow: 0 2px 8px rgba(0,0,0,0.12);
  padding: 4px 0;
  white-space: nowrap;
  font-size: 13px;
}
.addr-menu a {
  display: block;
  padding: 3px 12px;
  color: #333;
  text-decoration: none;
  font-family: monospace;
}
.addr-menu a:hover {
  background: #f0f0f0;
  text-decoration: none;
}
</style>

<style>
html.dark .addr-link { border-bottom-color: #484f58; }
html.dark .addr-link:hover { border-bottom-color: #58a6ff; }
html.dark .addr-menu { background: #21262d; border-color: #30363d; box-shadow: 0 2px 8px rgba(0,0,0,0.3); }
html.dark .addr-menu a { color: #c9d1d9; }
html.dark .addr-menu a:hover { background: #30363d; }
</style>
