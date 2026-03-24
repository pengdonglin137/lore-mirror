<script setup>
import { ref, computed, onMounted } from 'vue'
import { getVisitStats } from '../api.js'

const data = ref(null)
const loading = ref(true)
const error = ref(null)
const days = ref(30)

onMounted(async () => {
  document.title = 'Stats - lore-mirror'
  await loadStats()
})

async function loadStats() {
  loading.value = true
  error.value = null
  try {
    data.value = await getVisitStats({ days: days.value })
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

// Unicode sparkline from an array of numbers
const SPARK_CHARS = ' \u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588'
function sparkline(values) {
  if (!values.length) return ''
  const max = Math.max(...values, 1)
  return values.map(v => SPARK_CHARS[Math.round((v / max) * 8)]).join('')
}

function barWidth(value, max) {
  if (!max) return '0%'
  return Math.round((value / max) * 100) + '%'
}

function formatNum(n) {
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'K'
  return String(n)
}

const dailySparkline = computed(() => {
  if (!data.value?.daily_trend) return ''
  return sparkline(data.value.daily_trend.map(d => d.total_hits))
})

const hourlySparkline = computed(() => {
  if (!data.value?.hourly_trend) return ''
  return sparkline(data.value.hourly_trend.map(d => d.hits))
})

const endpointMax = computed(() => {
  if (!data.value?.top_endpoints?.length) return 1
  return data.value.top_endpoints[0].hits
})

const inboxMax = computed(() => {
  if (!data.value?.top_inboxes?.length) return 1
  return data.value.top_inboxes[0].hits
})
</script>

<template>
  <div>
    <div v-if="loading" class="loading">Loading statistics...</div>
    <div v-else-if="error" class="error">Error: {{ error }}</div>
    <template v-else-if="data">

      <!-- Summary cards -->
      <div class="stats-summary">
        <div class="stat-card">
          <div class="stat-value">{{ formatNum(data.totals.total_hits) }}</div>
          <div class="stat-label">total visits</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ formatNum(data.totals.today_hits) }}</div>
          <div class="stat-label">today</div>
        </div>
      </div>

      <!-- Daily trend -->
      <div class="stats-card">
        <div class="card-title">Daily Trend <span class="card-subtitle">({{ days }}d)</span></div>
        <div class="sparkline-row">{{ dailySparkline }}</div>
        <div class="trend-table">
          <template v-for="(d, i) in data.daily_trend" :key="d.day">
            <div v-if="i % 7 === 0 || i === data.daily_trend.length - 1" class="trend-row">
              <span class="trend-date">{{ d.day }}</span>
              <span class="trend-bar-track">
                <span class="trend-bar-fill" :style="{ width: barWidth(d.total_hits, Math.max(...data.daily_trend.map(x => x.total_hits), 1)) }"></span>
              </span>
              <span class="trend-value">{{ formatNum(d.total_hits) }}</span>
            </div>
          </template>
        </div>
      </div>

      <!-- Hourly trend -->
      <div class="stats-card">
        <div class="card-title">Hourly Trend <span class="card-subtitle">(48h)</span></div>
        <div class="sparkline-row">{{ hourlySparkline }}</div>
      </div>

      <!-- Top endpoints -->
      <div v-if="data.top_endpoints?.length" class="stats-card">
        <div class="card-title">Top Endpoints <span class="card-subtitle">({{ days }}d)</span></div>
        <div v-for="ep in data.top_endpoints" :key="ep.endpoint" class="bar-row">
          <span class="bar-track"><span class="bar-fill" :style="{ width: barWidth(ep.hits, endpointMax) }"></span></span>
          <span class="bar-value">{{ formatNum(ep.hits) }}</span>
          <span class="bar-extra">{{ ep.avg_ms.toFixed(0) }}ms</span>
          <span class="bar-label">{{ ep.endpoint }}</span>
        </div>
      </div>

      <!-- Top inboxes -->
      <div v-if="data.top_inboxes?.length" class="stats-card">
        <div class="card-title">Popular Inboxes <span class="card-subtitle">({{ days }}d)</span></div>
        <div v-for="ib in data.top_inboxes" :key="ib.inbox" class="bar-row">
          <span class="bar-track"><span class="bar-fill inbox-fill" :style="{ width: barWidth(ib.hits, inboxMax) }"></span></span>
          <span class="bar-value">{{ formatNum(ib.hits) }}</span>
          <router-link :to="`/inbox/${ib.inbox}`" class="bar-label">{{ ib.inbox }}</router-link>
        </div>
      </div>

      <!-- Top messages -->
      <div v-if="data.top_messages?.length" class="stats-card">
        <div class="card-title">Popular Messages</div>
        <div v-for="msg in data.top_messages" :key="msg.message_id" class="popular-msg">
          <span class="msg-hits">{{ formatNum(msg.hits) }} views</span>
          <router-link :to="`/message/${encodeURIComponent(msg.message_id)}`" class="msg-title">{{ (msg.subject || msg.message_id).slice(0, 80) }}</router-link>
          <span class="msg-inbox" v-if="msg.inbox">[{{ msg.inbox }}]</span>
        </div>
      </div>

    </template>
  </div>
</template>

<style scoped>
.stats-summary {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
}

.stat-card {
  background: #fff;
  border: 1px solid #d1d9e0;
  border-radius: 10px;
  padding: 20px 32px;
  text-align: center;
  flex: 1;
  max-width: 200px;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: #1f2328;
}

.stat-label {
  font-size: 12px;
  color: #656d76;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-top: 2px;
}

.stats-card {
  background: #fff;
  border: 1px solid #d1d9e0;
  border-radius: 10px;
  padding: 16px 20px;
  margin-bottom: 16px;
}

.card-title {
  font-weight: 700;
  font-size: 14px;
  margin-bottom: 12px;
  color: #1f2328;
}

.card-subtitle {
  font-weight: 400;
  color: #8b949e;
  font-size: 12px;
}

.sparkline-row {
  font-size: 20px;
  letter-spacing: 1px;
  color: #0969da;
  line-height: 1;
  margin-bottom: 12px;
}

.trend-table {
  margin-top: 8px;
}

.trend-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 3px 0;
  font-size: 12px;
}

.trend-date {
  width: 80px;
  color: #656d76;
}

.trend-bar-track {
  flex: 1;
  height: 6px;
  background: #eef1f5;
  border-radius: 3px;
  overflow: hidden;
}

.trend-bar-fill {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, #0969da, #54aeff);
  border-radius: 3px;
  transition: width 0.3s;
}

.trend-value {
  width: 50px;
  text-align: right;
  font-weight: 600;
  color: #1f2328;
}

/* ── Bar rows ────────────────────────────────── */
.bar-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 5px 0;
  font-size: 13px;
}

.bar-track {
  width: 120px;
  height: 8px;
  background: #eef1f5;
  border-radius: 4px;
  overflow: hidden;
  flex-shrink: 0;
}

.bar-fill {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, #0969da, #54aeff);
  border-radius: 4px;
  transition: width 0.3s;
}

.inbox-fill {
  background: linear-gradient(90deg, #2da44e, #56d364);
}

.bar-value {
  width: 50px;
  text-align: right;
  font-weight: 600;
  font-size: 12px;
  color: #1f2328;
}

.bar-extra {
  width: 40px;
  text-align: right;
  font-size: 11px;
  color: #8b949e;
}

.bar-label {
  font-size: 12px;
  color: #656d76;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ── Popular messages ────────────────────────── */
.popular-msg {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding: 5px 0;
  font-size: 13px;
  border-bottom: 1px solid #eef1f5;
}
.popular-msg:last-child { border-bottom: none; }

.msg-hits {
  font-size: 11px;
  color: #8b949e;
  white-space: nowrap;
  min-width: 60px;
}

.msg-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.msg-inbox {
  font-size: 11px;
  color: #8b949e;
  white-space: nowrap;
}
</style>

<style>
html.dark .stat-card { background: #161b22; border-color: #30363d; }
html.dark .stat-value { color: #e6edf3; }
html.dark .stat-label { color: #8b949e; }
html.dark .stats-card { background: #161b22; border-color: #30363d; }
html.dark .card-title { color: #e6edf3; }
html.dark .sparkline-row { color: #58a6ff; }
html.dark .trend-date { color: #8b949e; }
html.dark .trend-bar-track { background: #21262d; }
html.dark .trend-bar-fill { background: linear-gradient(90deg, #388bfd, #58a6ff); }
html.dark .trend-value { color: #e6edf3; }
html.dark .bar-track { background: #21262d; }
html.dark .bar-fill { background: linear-gradient(90deg, #388bfd, #58a6ff); }
html.dark .inbox-fill { background: linear-gradient(90deg, #238636, #3fb950); }
html.dark .bar-value { color: #e6edf3; }
html.dark .bar-label { color: #8b949e; }
html.dark .popular-msg { border-color: #21262d; }
</style>
