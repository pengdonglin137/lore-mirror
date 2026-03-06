<script setup>
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const query = ref('')
const showHelp = ref(false)

function doLocate() {
  router.push({ path: '/', query: query.value.trim() ? { locate: query.value.trim() } : {} })
}

function doSearchAll() {
  if (!query.value.trim()) return
  router.push({ path: '/search', query: { q: query.value.trim() } })
}

// Theme toggle: system → dark → light → system
const theme = ref(localStorage.getItem('theme') || 'system')
const themeIcons = { system: '\u25D1', dark: '\u263D', light: '\u2600' }

function applyTheme() {
  const dark = theme.value === 'dark' ||
    (theme.value === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)
  document.documentElement.classList.toggle('dark', dark)
}

function cycleTheme() {
  const order = ['system', 'dark', 'light']
  theme.value = order[(order.indexOf(theme.value) + 1) % 3]
}

watch(theme, () => {
  localStorage.setItem('theme', theme.value)
  applyTheme()
})

const mql = window.matchMedia('(prefers-color-scheme: dark)')
function onSystemChange() { if (theme.value === 'system') applyTheme() }
onMounted(() => { applyTheme(); mql.addEventListener('change', onSystemChange) })
onUnmounted(() => mql.removeEventListener('change', onSystemChange))
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
          @keyup.enter="doSearchAll"
        />
        <button class="nav-btn" @click="doLocate">locate inbox</button>
        <button class="nav-btn" @click="doSearchAll">search all inboxes</button>
        <button class="nav-btn help-btn" @click="showHelp = !showHelp" title="Search syntax help">?</button>
        <button class="nav-btn theme-btn" @click="cycleTheme" :title="`Theme: ${theme}`">{{ themeIcons[theme] }}</button>
      </nav>
      <pre v-if="showHelp" class="search-help">Search prefixes (compatible with lore.kernel.org):

  s:keyword        Subject              s:"memory leak"    s:PATCH
  f:name           From/sender          f:torvalds
  b:keyword        Body text            b:use-after-free   b:kasan
  bs:keyword       Subject + body       bs:regression
  d:range          Date range           d:2026-01-01..2026-03-01
                                        d:2026-01-01..     d:..2026-03-01
  t:addr           To header            t:linux-mm@kvack.org
  c:addr           Cc header            c:stable@vger.kernel.org
  a:addr           Any address          a:torvalds@linux-foundation.org
  tc:addr          To + Cc              tc:netdev@vger.kernel.org
  m:id             Message-ID (exact)   m:20260110-can@pengutronix.de

Operators: AND (default), OR, NOT, "exact phrase", prefix*
Paste a Message-ID (with @) to search it directly.

Examples:
  s:PATCH f:torvalds d:2026-01-01..          patches from Torvalds since Jan 2026
  b:"use after free" d:2026-02-01..          UAF bugs since Feb 2026
  s:PATCH b:mm_struct                        patches mentioning mm_struct
</pre>
    </header>
    <main>
      <router-view />
    </main>
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

html.dark body { background: #1a1a1a; color: #ddd; }
html.dark a { color: #6cb6ff; }
html.dark header { background: #252525; border-color: #444; }
html.dark .logo-link { color: #ddd; }
html.dark .nav-input, html.dark .nav-btn, html.dark .pagination button {
  background: #333; color: #ddd; border-color: #555;
}
html.dark mark { background: #665500; color: #fff; }
html.dark .search-help { background: #222; border-color: #444; color: #999; }
</style>
