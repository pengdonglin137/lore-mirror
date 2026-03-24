<script setup>
import { ref, computed } from 'vue'
import { linkifyLine } from '../utils.js'

const props = defineProps({
  bodyText: { type: String, default: '' }
})

const expandedQuotes = ref(new Set())

const trailerRe = /^(Signed-off-by|Reviewed-by|Acked-by|Tested-by|Reported-by|Suggested-by|Co-developed-by|Fixes|Cc|Link|Closes):/

function lineClass(line) {
  if (line.startsWith('diff --git')) return 'diff-header'
  if (line.startsWith('@@')) return 'diff-hunk'
  if (line.startsWith('+++') || line.startsWith('---')) return 'diff-file'
  if (line.startsWith('+')) return 'diff-add'
  if (line.startsWith('-')) return 'diff-del'
  if (line.startsWith('> >') || line.startsWith('>> ') || line.startsWith('>>>')) return 'quote-deep'
  if (line.startsWith('>')) return 'quote'
  if (trailerRe.test(line)) return 'trailer'
  return ''
}

const bodyLines = computed(() => {
  if (!props.bodyText) return []
  return props.bodyText.split('\n')
})

const bodySegments = computed(() => {
  const lines = bodyLines.value
  const segments = []
  let i = 0
  while (i < lines.length) {
    if (lines[i].startsWith('>')) {
      const start = i
      while (i < lines.length && lines[i].startsWith('>')) i++
      segments.push({ type: 'quote', lines: lines.slice(start, i), id: start })
    } else {
      segments.push({ type: 'line', line: lines[i], id: i })
      i++
    }
  }
  return segments
})

function toggleQuote(id) {
  if (expandedQuotes.value.has(id)) expandedQuotes.value.delete(id)
  else expandedQuotes.value.add(id)
}
</script>

<template>
  <pre class="msg-body"><template v-for="seg in bodySegments" :key="seg.id"><template v-if="seg.type === 'line'"><span :class="lineClass(seg.line)" v-html="linkifyLine(seg.line)"></span>
</template><template v-else-if="seg.lines.length < 4 || expandedQuotes.has(seg.id)"><template v-for="(line, j) in seg.lines" :key="seg.id + '-' + j"><span :class="lineClass(line)" v-html="linkifyLine(line)"></span>
</template></template><template v-else><span class="quote-collapsed" @click="toggleQuote(seg.id)"><span :class="lineClass(seg.lines[0])" v-html="linkifyLine(seg.lines[0])"></span>
<span class="quote-toggle">[{{ seg.lines.length - 1 }} more quoted lines — click to expand]</span>
</span></template></template></pre>
</template>

<style scoped>
.msg-body {
  padding: 16px;
  border: 1px solid #d1d9e0;
  border-top: none;
  background: #fff;
  font-size: 13px;
  border-radius: 0 0 10px 10px;
}

.diff-add { color: #1a7f37; background: #dafbe1; padding: 0 2px; border-radius: 2px; }
.diff-del { color: #cf222e; background: #ffebe9; padding: 0 2px; border-radius: 2px; }
.diff-hunk { color: #8250df; background: #fbefff; padding: 0 2px; border-radius: 2px; }
.diff-header { color: #0550ae; font-weight: bold; }
.diff-file { color: #656d76; font-weight: bold; }
.quote { color: #57606a; border-left: 2px solid #d1d9e0; padding-left: 8px; display: inline-block; }
.quote-deep { color: #8b949e; border-left: 2px solid #d1d9e0; padding-left: 8px; display: inline-block; }
.trailer { color: #57606a; }
.quote-collapsed { cursor: pointer; }
.quote-toggle {
  color: #8b949e;
  font-size: 12px;
  font-style: italic;
  padding: 2px 8px;
  background: #f6f8fa;
  border-radius: 4px;
  display: inline-block;
  transition: all 0.15s;
}
.quote-toggle:hover { color: #0969da; background: #ddf4ff; }
</style>

<style>
html.dark .msg-body {
  background: #0d1117;
  border-color: #30363d;
}

html.dark .msg-body .diff-add { color: #7ee787; background: #12261e; }
html.dark .msg-body .diff-del { color: #ffa198; background: #2d1619; }
html.dark .msg-body .diff-hunk { color: #d2a8ff; background: #1e1731; }
html.dark .msg-body .diff-header { color: #79c0ff; }
html.dark .msg-body .diff-file { color: #8b949e; }
html.dark .msg-body .quote { color: #8b949e; border-left-color: #30363d; }
html.dark .msg-body .quote-deep { color: #6e7681; border-left-color: #30363d; }
html.dark .msg-body .trailer { color: #8b949e; }
html.dark .msg-body .quote-toggle { color: #6e7681; background: #161b22; }
html.dark .msg-body .quote-toggle:hover { color: #58a6ff; background: #0d2744; }
</style>
