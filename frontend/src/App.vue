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

// Theme toggle: light <-> dark (detects system preference on first visit)
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
        <div class="search-wrap">
          <svg class="search-icon" width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><path d="M11.5 7a4.5 4.5 0 1 1-9 0 4.5 4.5 0 0 1 9 0Zm-.82 4.74a6 6 0 1 1 1.06-1.06l3.04 3.04a.75.75 0 1 1-1.06 1.06l-3.04-3.04Z"/></svg>
          <input
            v-model="query"
            type="text"
            class="nav-input"
            placeholder="s:PATCH f:torvalds ..."
            @keyup.enter="doSearchAll"
          />
        </div>
        <button class="nav-btn" @click="doLocate">locate inbox</button>
        <button class="nav-btn primary" @click="doSearchAll">search</button>
        <button class="nav-btn icon-btn" @click="showHelp = !showHelp" title="Search syntax help">?</button>
        <router-link to="/stats" class="nav-btn icon-btn" title="Visit statistics"><svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><rect x="1" y="9" width="3" height="6" rx="0.5"/><rect x="6" y="5" width="3" height="10" rx="0.5"/><rect x="11" y="1" width="3" height="14" rx="0.5"/></svg></router-link>
        <button class="nav-btn icon-btn" @click="toggleTheme" :title="isDark ? 'Switch to light' : 'Switch to dark'">{{ isDark ? '\u2600' : '\u263D' }}</button>
      </nav>
      <SearchHelp v-if="showHelp" />
    </header>
    <main>
      <router-view />
    </main>
    <div v-if="showKeys" class="keys-overlay" @click="showKeys = false">
      <div class="keys-box" @click.stop>
        <div class="keys-title">Keyboard Shortcuts</div>
        <pre class="keys-content">
  ?           toggle this help
  /  s        focus search input
  Esc         blur search input

Message view:
  j           next message in thread
  k           previous message in thread
  t           view thread

Tip: click any sender/address for quick search filters
</pre>
      </div>
    </div>
  </div>
</template>

<style>
/* ── Reset & Base ───────────────────────────── */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: 'SF Mono', 'Cascadia Code', 'Fira Code', 'JetBrains Mono', Menlo, Consolas, monospace;
  font-size: 14px;
  line-height: 1.6;
  color: #1f2328;
  background: #f6f8fa;
}

a {
  color: #0969da;
  text-decoration: none;
  transition: color 0.15s;
}
a:hover {
  color: #0550ae;
  text-decoration: underline;
}

pre {
  white-space: pre-wrap;
  word-wrap: break-word;
}

/* ── Header / Nav ───────────────────────────── */
header {
  position: sticky;
  top: 0;
  z-index: 30;
  border-bottom: 1px solid #d1d9e0;
  padding: 10px 20px;
  background: rgba(255,255,255,0.85);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}

header nav {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.logo-link {
  font-weight: 700;
  font-size: 16px;
  color: #1f2328;
  margin-right: 8px;
  letter-spacing: -0.3px;
  text-decoration: none !important;
}

.search-wrap {
  position: relative;
  flex: 1;
  min-width: 140px;
  max-width: 420px;
}

.search-icon {
  position: absolute;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
  color: #656d76;
  pointer-events: none;
}

.nav-input {
  font-family: inherit;
  font-size: 13px;
  padding: 6px 10px 6px 30px;
  border: 1px solid #d1d9e0;
  border-radius: 6px;
  width: 100%;
  background: #f6f8fa;
  color: #1f2328;
  transition: border-color 0.15s, box-shadow 0.15s, background 0.15s;
  outline: none;
}

.nav-input:focus {
  border-color: #0969da;
  box-shadow: 0 0 0 3px rgba(9,105,218,0.15);
  background: #fff;
}

.nav-btn {
  font-family: inherit;
  font-size: 13px;
  padding: 5px 12px;
  cursor: pointer;
  border: 1px solid #d1d9e0;
  border-radius: 6px;
  background: #f6f8fa;
  color: #1f2328;
  white-space: nowrap;
  transition: all 0.15s;
  text-decoration: none !important;
}

.nav-btn:hover {
  background: #eaeef2;
  border-color: #c4ccd4;
}

.nav-btn:active {
  background: #d1d9e0;
}

.nav-btn.primary {
  background: #0969da;
  color: #fff;
  border-color: #0969da;
}

.nav-btn.primary:hover {
  background: #0550ae;
  border-color: #0550ae;
}

.icon-btn {
  min-width: 32px;
  padding: 5px 8px;
  text-align: center;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.search-help {
  font-size: 12px;
  background: #f6f8fa;
  border-top: 1px solid #d1d9e0;
  padding: 12px 20px;
  color: #656d76;
  margin: 10px -20px -10px;
  border-radius: 0;
}

/* ── Main Content ───────────────────────────── */
main {
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px 20px;
}

/* ── Pagination ─────────────────────────────── */
.pagination {
  margin: 16px 0;
  display: flex;
  gap: 6px;
  align-items: center;
  flex-wrap: wrap;
}

.pagination button {
  font-family: inherit;
  font-size: 13px;
  padding: 4px 12px;
  cursor: pointer;
  border: 1px solid #d1d9e0;
  border-radius: 6px;
  background: #f6f8fa;
  color: #1f2328;
  transition: all 0.15s;
}

.pagination button:hover:not(:disabled) {
  background: #eaeef2;
  border-color: #c4ccd4;
}

.pagination button:disabled {
  opacity: 0.4;
  cursor: default;
}

.page-input {
  font-family: inherit;
  font-size: 13px;
  width: 4em;
  text-align: center;
  padding: 3px 6px;
  border: 1px solid #d1d9e0;
  border-radius: 6px;
  background: #fff;
  color: #1f2328;
  outline: none;
  transition: border-color 0.15s, box-shadow 0.15s;
}

.page-input:focus {
  border-color: #0969da;
  box-shadow: 0 0 0 3px rgba(9,105,218,0.15);
}

/* ── States ──────────────────────────────────── */
.loading {
  color: #656d76;
  padding: 24px 0;
}

.error {
  color: #cf222e;
  padding: 24px 0;
  background: #ffebe9;
  border: 1px solid #ffcecb;
  border-radius: 8px;
  padding: 16px 20px;
}

mark {
  background: #fff8c5;
  padding: 1px 3px;
  border-radius: 3px;
}

/* ── Keyboard shortcuts overlay ──────────────── */
.keys-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.4); z-index: 100;
  display: flex; align-items: center; justify-content: center;
  backdrop-filter: blur(4px);
}
.keys-box {
  background: #fff;
  border: 1px solid #d1d9e0;
  border-radius: 12px;
  padding: 0;
  box-shadow: 0 8px 32px rgba(0,0,0,0.12);
  overflow: hidden;
  min-width: 380px;
}
.keys-title {
  font-weight: 700;
  font-size: 14px;
  padding: 14px 20px;
  border-bottom: 1px solid #d1d9e0;
  background: #f6f8fa;
}
.keys-content {
  padding: 12px 20px 16px;
  font-size: 13px;
}

/* ── Dark Theme ──────────────────────────────── */
html.dark { color-scheme: dark; }
html.dark body { background: #010409; color: #e6edf3; }
html.dark a { color: #58a6ff; }
html.dark a:hover { color: #79c0ff; }

html.dark header {
  background: rgba(22,27,34,0.85);
  border-color: #30363d;
  backdrop-filter: blur(12px);
}
html.dark .logo-link { color: #e6edf3; }

html.dark .nav-input {
  background: #0d1117;
  color: #e6edf3;
  border-color: #30363d;
}
html.dark .nav-input:focus {
  border-color: #58a6ff;
  box-shadow: 0 0 0 3px rgba(88,166,255,0.15);
  background: #161b22;
}
html.dark .search-icon { color: #8b949e; }

html.dark .nav-btn {
  background: #21262d;
  color: #e6edf3;
  border-color: #30363d;
}
html.dark .nav-btn:hover {
  background: #30363d;
  border-color: #484f58;
}
html.dark .nav-btn.primary {
  background: #238636;
  color: #fff;
  border-color: #238636;
}
html.dark .nav-btn.primary:hover {
  background: #2ea043;
  border-color: #2ea043;
}

html.dark .pagination button {
  background: #21262d;
  color: #e6edf3;
  border-color: #30363d;
}
html.dark .pagination button:hover:not(:disabled) {
  background: #30363d;
  border-color: #484f58;
}
html.dark .page-input {
  background: #0d1117;
  color: #e6edf3;
  border-color: #30363d;
}
html.dark .page-input:focus {
  border-color: #58a6ff;
  box-shadow: 0 0 0 3px rgba(88,166,255,0.15);
}

html.dark mark { background: #3b2e00; color: #e3b341; }
html.dark .loading { color: #8b949e; }
html.dark .error { color: #ffa198; background: #2d1619; border-color: #5b2d32; }
html.dark .search-help { background: #0d1117; border-color: #30363d; color: #8b949e; }

html.dark .keys-overlay { background: rgba(0,0,0,0.6); }
html.dark .keys-box { background: #161b22; border-color: #30363d; }
html.dark .keys-title { background: #0d1117; border-color: #30363d; color: #e6edf3; }
html.dark .keys-content { color: #c9d1d9; }
</style>
