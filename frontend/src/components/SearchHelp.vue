<template>
  <div class="search-help-card">
    <pre class="search-help">Search prefixes (compatible with lore.kernel.org):

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
  </div>
</template>

<style scoped>
.search-help-card {
  margin: 10px -20px -10px;
  border-top: 1px solid #d1d9e0;
}

.search-help {
  font-size: 12px;
  background: #f6f8fa;
  padding: 12px 20px;
  color: #656d76;
  margin: 0;
  line-height: 1.6;
}
</style>

<style>
html.dark .search-help-card { border-color: #30363d; }
html.dark .search-help { background: #0d1117; color: #8b949e; }
</style>
