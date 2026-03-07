<script setup>
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import SearchHelp from './components/SearchHelp.vue'

const router = useRouter()
const route = router.currentRoute
const query = ref(route.value.query.q || route.value.query.locate || '')
const showHelp = ref(false)

// Keep nav bar input in sync with URL query
watch(() => route.value.query, (q) => {
  query.value = q.q || q.locate || ''
})
const showKeys = ref(false)

function doLocate() {
  router.push({ path: '/', query: query.value.trim() ? { locate: query.value.trim() } : {} })
}

function doSearchAll() {
  if (!query.value.trim()) return
  const current = router.currentRoute.value
  const q = { q: query.value.trim() }
  // Preserve inbox filter when already on search page
  if (current.path === '/search' && current.query.inbox) {
    q.inbox = current.query.inbox
  }
  router.push({ path: '/search', query: q })
}

// Theme toggle: light ↔ dark (detects system preference on first visit)
const stored = localStorage.getItem('theme')
const isDark = ref(stored ? stored === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches)

function applyTheme() {
  document.documentElement.classList.toggle('dark', isDark.value)
  document.documentElement.style.cssText = isDark.value ? 'background:#0d1117;color-scheme:dark' : ''
}

function toggleTheme() {
  isDark.value = !isDark.value
}

watch(isDark, () => {
  localStorage.setItem('theme', isDark.value ? 'dark' : 'light')
  applyTheme()
})

function onGlobalKey(e) {
  if (e.key === 'Escape') {
    showKeys.value = false
    document.activeElement?.blur()
    return
  }
  if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) return
  if (e.key === '?') showKeys.value = !showKeys.value
  else if (e.key === '/' || e.key === 's') {
    e.preventDefault()
    document.querySelector('.nav-input')?.focus()
  }
}

onMounted(() => { applyTheme(); window.addEventListener('keydown', onGlobalKey) })
onUnmounted(() => window.removeEventListener('keydown', onGlobalKey))
</script>

<template>
  <div class="app">
    <header>
      <nav>
        <router-link to="/" class="logo-link">lore-mirror</router-link>
        <input
          v-model="query"
          type="text"
          class="nav-input"
          placeholder="s:PATCH f:torvalds ..."
          @keyup.enter="doSearchAll"
        />
        <button class="nav-btn" @click="doLocate">locate inbox</button>
        <button class="nav-btn" @click="doSearchAll">search all inboxes</button>
        <button class="nav-btn help-btn" @click="showHelp = !showHelp" title="Search syntax help">?</button>
        <button class="nav-btn theme-btn" @click="toggleTheme" :title="isDark ? 'Switch to light' : 'Switch to dark'">{{ isDark ? '\u2600' : '\u263D' }}</button>
      </nav>
      <SearchHelp v-if="showHelp" />
    </header>
    <main>
      <router-view />
    </main>
    <div v-if="showKeys" class="keys-overlay" @click="showKeys = false">
      <pre class="keys-box" @click.stop>Keyboard shortcuts

  ?           toggle this help
  /  s        focus search input
  Esc         blur search input

Message view:
  j           next message in thread
  k           previous message in thread
  t           view thread
</pre>
    </div>
  </div>
</template>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: monospace;
  font-size: 14px;
  line-height: 1.5;
  color: #333;
  background: #fff;
}

a {
  color: #00609f;
  text-decoration: none;
}
a:hover {
  text-decoration: underline;
}

pre {
  white-space: pre-wrap;
  word-wrap: break-word;
}

header {
  border-bottom: 1px solid #ccc;
  padding: 8px 16px;
  background: #f6f6f6;
}

header nav {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.logo-link {
  font-weight: bold;
  font-size: 16px;
  color: #333;
  margin-right: 8px;
}

.nav-input {
  font-family: monospace;
  font-size: 14px;
  padding: 2px 6px;
  border: 1px solid #999;
  width: 200px;
  min-width: 120px;
  flex: 1;
  max-width: 400px;
}

.nav-btn {
  font-family: monospace;
  font-size: 14px;
  padding: 2px 8px;
  cursor: pointer;
  border: 1px solid #999;
  background: #eee;
  white-space: nowrap;
}

.help-btn, .theme-btn {
  font-weight: bold;
  min-width: 26px;
  text-align: center;
  padding: 2px 6px;
}

.search-help {
  font-size: 12px;
  background: #f0f0f0;
  border-top: 1px solid #ddd;
  padding: 8px 16px;
  color: #555;
  margin: 0;
}

main {
  padding: 16px;
}

.pagination {
  margin: 16px 0;
  display: flex;
  gap: 8px;
  align-items: center;
}

.pagination button {
  font-family: monospace;
  padding: 4px 12px;
  cursor: pointer;
  border: 1px solid #999;
  background: #eee;
}

.pagination button:disabled {
  opacity: 0.5;
  cursor: default;
}

.loading {
  color: #666;
  padding: 20px 0;
}

.error {
  color: #c00;
  padding: 20px 0;
}

mark {
  background: #ff0;
  padding: 0 1px;
}

html.dark { color-scheme: dark; }
html.dark body { background: #0d1117; color: #c9d1d9; }
html.dark a { color: #58a6ff; }
html.dark header { background: #161b22; border-color: #30363d; }
html.dark .logo-link { color: #c9d1d9; }
html.dark .nav-input, html.dark .nav-btn, html.dark .pagination button {
  background: #21262d; color: #c9d1d9; border-color: #30363d;
}
html.dark .nav-btn:hover { background: #30363d; }
html.dark mark { background: #5a4a00; color: #e3b341; }
html.dark .loading { color: #8b949e; }
html.dark .error { color: #f85149; }
html.dark .search-help { background: #161b22; border-color: #30363d; color: #8b949e; }

.keys-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.4); z-index: 100;
  display: flex; align-items: center; justify-content: center;
}
.keys-box {
  background: #fff; border: 1px solid #ccc; padding: 16px 24px;
  font-size: 13px; box-shadow: 0 4px 12px rgba(0,0,0,0.15);
}
html.dark .keys-overlay { background: rgba(0,0,0,0.6); }
html.dark .keys-box { background: #161b22; border-color: #30363d; color: #c9d1d9; }
</style>
