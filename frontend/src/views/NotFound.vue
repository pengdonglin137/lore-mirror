<script setup>
document.title = '404 — lore-mirror'
</script>

<template>
  <div class="not-found">
    <div class="not-found-code">404</div>
    <div class="not-found-text">Page not found</div>
    <div class="not-found-desc">The page you requested does not exist.</div>
    <router-link to="/" class="not-found-link">&larr; back to lore-mirror</router-link>
  </div>
</template>

<style scoped>
.not-found {
  text-align: center;
  padding: 64px 0;
}
.not-found-code {
  font-size: 64px;
  font-weight: 700;
  color: #d1d9e0;
  line-height: 1;
}
.not-found-text {
  font-size: 20px;
  font-weight: 600;
  color: #1f2328;
  margin-top: 8px;
}
.not-found-desc {
  color: #656d76;
  margin-top: 8px;
}
.not-found-link {
  display: inline-block;
  margin-top: 20px;
  padding: 8px 20px;
  border: 1px solid #d1d9e0;
  border-radius: 8px;
  transition: all 0.15s;
}
.not-found-link:hover {
  background: #f6f8fa;
  border-color: #0969da;
  text-decoration: none;
}
</style>

<style>
html.dark .not-found-code { color: #30363d; }
html.dark .not-found-text { color: #e6edf3; }
html.dark .not-found-desc { color: #8b949e; }
html.dark .not-found-link { border-color: #30363d; }
html.dark .not-found-link:hover { background: #161b22; border-color: #58a6ff; }
</style>
