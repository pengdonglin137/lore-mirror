<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const query = ref('')

function doLocate() {
  router.push({ path: '/', query: query.value.trim() ? { locate: query.value.trim() } : {} })
}

function doSearchAll() {
  if (!query.value.trim()) return
  router.push({ path: '/search', query: { q: query.value.trim() } })
}
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
      </nav>
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
  max-width: 1200px;
  margin: 0 auto;
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

main {
  max-width: 1200px;
  margin: 0 auto;
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

@media (prefers-color-scheme: dark) {
  body { background: #1a1a1a; color: #ddd; }
  a { color: #6cb6ff; }
  header { background: #252525; border-color: #444; }
  .logo-link { color: #ddd; }
  .nav-input, .nav-btn, .pagination button {
    background: #333; color: #ddd; border-color: #555;
  }
  mark { background: #665500; color: #fff; }
}
</style>
