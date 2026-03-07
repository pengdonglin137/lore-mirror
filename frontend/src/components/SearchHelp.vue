<template>
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
</template>
