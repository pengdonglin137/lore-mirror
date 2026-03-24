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
    <pre v-if="loading" class="loading">Loading statistics...</pre>
    <pre v-else-if="error" class="error">Error: {{ error }}</pre>
    <template v-else-if="data">

      <!-- Totals -->
      <pre class="stats-section"><strong>Visit Statistics</strong>

  Total visits:  {{ formatNum(data.totals.total_hits) }}
  Today:         {{ formatNum(data.totals.today_hits) }}</pre>

      <!-- Daily trend -->
      <pre class="stats-section"><strong>Daily trend</strong> ({{ days }}d)

  {{ dailySparkline }}
<template v-for="(d, i) in data.daily_trend" :key="d.day"><template v-if="i % 7 === 0 || i === data.daily_trend.length - 1">  {{ d.day }}  {{ formatNum(d.total_hits).padStart(6) }} hits
</template></template></pre>

      <!-- Hourly trend -->
      <pre class="stats-section"><strong>Hourly trend</strong> (48h)

  {{ hourlySparkline }}
</pre>

      <!-- Top endpoints -->
      <pre v-if="data.top_endpoints?.length" class="stats-section"><strong>Top endpoints</strong> ({{ days }}d)
<template v-for="ep in data.top_endpoints" :key="ep.endpoint">
  <span class="bar-row"><span class="bar" :style="{ width: barWidth(ep.hits, endpointMax) }"></span></span> {{ formatNum(ep.hits).padStart(6) }}  {{ ep.avg_ms.toFixed(0).padStart(4) }}ms  {{ ep.endpoint }}
</template></pre>

      <!-- Top inboxes -->
      <pre v-if="data.top_inboxes?.length" class="stats-section"><strong>Top inboxes</strong> ({{ days }}d)
<template v-for="ib in data.top_inboxes" :key="ib.inbox">
  <span class="bar-row"><span class="bar" :style="{ width: barWidth(ib.hits, inboxMax) }"></span></span> {{ formatNum(ib.hits).padStart(6) }}  <router-link :to="`/inbox/${ib.inbox}`">{{ ib.inbox }}</router-link>
</template></pre>

      <!-- Top messages -->
      <pre v-if="data.top_messages?.length" class="stats-section"><strong>Popular messages</strong>
<template v-for="msg in data.top_messages" :key="msg.message_id">
  {{ formatNum(msg.hits).padStart(6) }} views  <router-link :to="`/message/${encodeURIComponent(msg.message_id)}`">{{ (msg.subject || msg.message_id).slice(0, 72) }}</router-link>
     {{ msg.inbox ? '[' + msg.inbox + ']' : '' }} {{ msg.last_accessed ? msg.last_accessed.slice(0, 10) : '' }}
</template></pre>

    </template>
  </div>
</template>

<style scoped>
.stats-section {
  margin-bottom: 20px;
  line-height: 1.6;
}

.bar-row {
  display: inline-block;
  width: 120px;
  height: 12px;
  background: #eee;
  vertical-align: middle;
  overflow: hidden;
}

.bar {
  display: inline-block;
  height: 100%;
  background: #4a9eff;
  transition: width 0.3s;
}
</style>

<style>
html.dark .bar-row { background: #21262d; }
html.dark .bar { background: #58a6ff; }
</style>
