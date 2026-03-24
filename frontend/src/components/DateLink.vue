<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { formatDate } from '../utils.js'

const props = defineProps({
  date: { type: String, required: true },
  inbox: { type: String, default: '' },
})

const router = useRouter()
const showMenu = ref(false)
const menuEl = ref(null)

// Parse "2026-03-12T10:30:00" → { dateStr: "2026-03-12", monthStr: "2026-03" }
const parsed = computed(() => {
  const d = props.date || ''
  const dateStr = d.slice(0, 10)          // YYYY-MM-DD
  const monthStr = d.slice(0, 7)          // YYYY-MM
  const year = d.slice(0, 4)
  const month = d.slice(5, 7)
  const day = parseInt(d.slice(8, 10)) || 1

  // Compute week range (+-3 days)
  const dt = new Date(dateStr)
  const weekStart = new Date(dt)
  weekStart.setDate(dt.getDate() - 3)
  const weekEnd = new Date(dt)
  weekEnd.setDate(dt.getDate() + 3)
  const fmt = (dd) => dd.toISOString().slice(0, 10)

  // Month range: first to last day
  const lastDay = new Date(parseInt(year), parseInt(month), 0).getDate()
  const monthStart = `${monthStr}-01`
  const monthEnd = `${monthStr}-${String(lastDay).padStart(2, '0')}`

  return { dateStr, monthStr, year, weekStart: fmt(weekStart), weekEnd: fmt(weekEnd), monthStart, monthEnd }
})

function doSearch(query) {
  showMenu.value = false
  const routeQuery = { q: query }
  if (props.inbox) routeQuery.inbox = props.inbox
  router.push({ path: '/search', query: routeQuery })
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
  <span class="date-wrap" ref="menuEl">
    <a href="#" class="date-link" @click="onClick">{{ formatDate(date) }}</a>
    <Transition name="menu">
      <span v-if="showMenu" class="date-menu">
        <a href="#" @click.prevent="doSearch(`d:${parsed.dateStr}`)">d: this date ({{ parsed.dateStr }})</a>
        <a href="#" @click.prevent="doSearch(`d:${parsed.weekStart}..${parsed.weekEnd}`)">d: this week (+-3 days)</a>
        <a href="#" @click.prevent="doSearch(`d:${parsed.monthStart}..${parsed.monthEnd}`)">d: this month ({{ parsed.monthStr }})</a>
        <span class="date-sep"></span>
        <a href="#" @click.prevent="doSearch(`d:${parsed.dateStr}..`)">d: from this date onward</a>
        <a href="#" @click.prevent="doSearch(`d:..${parsed.dateStr}`)">d: up to this date</a>
      </span>
    </Transition>
  </span>
</template>

<style scoped>
.date-wrap {
  position: relative;
  display: inline;
}
.date-link {
  cursor: pointer;
  text-decoration: none;
  color: inherit;
}
.date-link:hover {
  text-decoration: none;
  color: #0969da;
}
.date-menu {
  position: absolute;
  left: 0;
  top: 1.6em;
  z-index: 50;
  background: #fff;
  border: 1px solid #d1d9e0;
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.1);
  padding: 6px 0;
  white-space: nowrap;
  font-size: 13px;
}
.date-menu a {
  display: block;
  padding: 5px 14px;
  color: #1f2328;
  text-decoration: none;
  transition: background 0.1s;
}
.date-menu a:hover {
  background: #f6f8fa;
  text-decoration: none;
}
.date-sep {
  display: block;
  height: 1px;
  background: #d1d9e0;
  margin: 4px 0;
}

/* Transition */
.menu-enter-active, .menu-leave-active { transition: opacity 0.15s, transform 0.15s; }
.menu-enter-from, .menu-leave-to { opacity: 0; transform: translateY(-4px); }
</style>

<style>
html.dark .date-link:hover { color: #58a6ff; }
html.dark .date-menu { background: #161b22; border-color: #30363d; box-shadow: 0 4px 16px rgba(0,0,0,0.3); }
html.dark .date-menu a { color: #e6edf3; }
html.dark .date-menu a:hover { background: #21262d; }
html.dark .date-sep { background: #30363d; }
</style>
