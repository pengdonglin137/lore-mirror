---
name: lore-mirror
description: >-
  Search and browse Linux kernel mailing list archives via local lore-mirror API.
  Use when: searching kernel patches, finding discussions about kernel subsystems,
  looking up email threads, tracing patch review history, or finding commits by developer.
  Covers all lore.kernel.org mailing lists (lkml, linux-mm, netdev, etc).
invocation_policy: automatic
---

# lore-mirror — Local Kernel Mailing List Search

## When to Use

Activate this skill when the user wants to:
- Search Linux kernel mailing list archives
- Find patches, discussions, or review threads
- Look up emails by Message-ID, author, subject, or content
- Trace patch series review history
- Find what a kernel developer has been working on
- Understand the discussion behind a kernel change

## Access Methods

**MCP (preferred in Claude Code):** If the `lore-mirror` MCP server is connected (check `/mcp`), use the `lore_*` tools directly — they wrap this API with structured parameters and error handling. Tool names: `lore_list_inboxes`, `lore_search_emails`, `lore_get_message`, `lore_get_thread`, `lore_browse_inbox`, `lore_locate_inbox`, `lore_get_raw_email`.

**REST API (fallback):** Use the HTTP endpoints below when MCP is not available.

## API Base URL

```
http://localhost:8000
```

## Workflow (ALWAYS follow this order)

### Step 1: Discover Available Inboxes (DO THIS FIRST)

```
GET /api/inboxes
```

Returns a list of available mailing lists with detailed descriptions.
**Not all ~200 lore.kernel.org lists are mirrored.** You MUST check what's available before searching. Cache the result — it rarely changes.

Each inbox has a `description` field with topic keywords. Use it to pick the right list:
- `linux-mm` → page allocator, slab, OOM, hugepages, mmap, NUMA, swap, compaction
- `linux-fsdevel` → VFS, inode/dentry cache, mount API, iomap, writeback, splice
- `linux-block` → block I/O scheduler, bio, blk-mq, loop, zoned devices
- `lkml` → general kernel development, cross-subsystem (search here if unsure)

If you need to find which list covers a topic:
```
GET /api/locate?q=keyword
```

### Step 2: Search

```
GET /api/search?q=QUERY&inbox=INBOX_NAME&per_page=20
```

**Always specify `inbox`** for better performance. Omit only for cross-inbox search.

#### Search Prefix Syntax (lore.kernel.org compatible)

| Prefix | Field | Example |
|--------|-------|---------|
| `s:` | Subject | `s:PATCH` `s:"memory leak"` |
| `f:` | From/sender | `f:torvalds` `f:akpm` |
| `b:` | Body text | `b:kasan` `b:"use after free"` |
| `bs:` | Subject + body | `bs:regression` |
| `d:` | Date range | `d:2026-01-01..2026-03-01` `d:2026-01-01..` `d:..2026-03-01` |
| `t:` | To header | `t:linux-mm@kvack.org` |
| `c:` | Cc header | `c:stable@vger.kernel.org` |
| `a:` | Any address | `a:torvalds@linux-foundation.org` |
| `m:` | Message-ID (exact) | `m:20260110-can@pengutronix.de` |

Operators: `AND` (default), `OR`, `NOT`, `"exact phrase"`, `prefix*`

Paste a bare Message-ID (containing `@`) to auto-detect and search it directly.

#### Common Search Patterns

```bash
# Find patches by author
GET /api/search?q=s:PATCH+f:torvalds+d:2026-01-01..&inbox=lkml

# Find bug fix discussions
GET /api/search?q=b:"use+after+free"+d:2026-02-01..&inbox=linux-mm

# Find patches touching a specific function/struct
GET /api/search?q=s:PATCH+b:mm_struct&inbox=linux-mm

# Find all emails from a developer in a date range
GET /api/search?q=f:akpm+d:2026-03-01..&inbox=linux-mm

# Find discussions about a specific topic
GET /api/search?q=io_uring+splice+zero+copy&inbox=lkml
```

### Step 3: Read a Message

```
GET /api/messages/{message_id}
```

Returns full email: subject, sender, date, body_text, headers, attachments.
- `body_text` contains the email body; for patches, the diff is inline
- `in_reply_to` links to the parent email
- `references_ids` is useful for thread reconstruction
- `raw_email` is excluded (use `/api/raw?id=` for RFC 2822 format)

### Step 4: Read Full Thread

```
GET /api/threads/{message_id}
```

Returns all messages in the thread, sorted by date (oldest first).
Use `in_reply_to` to reconstruct the tree structure.
The `root` field is the Message-ID of the thread root.

### Step 5 (optional): Get Raw Email

```
GET /api/raw?id={message_id}
```

Returns the original RFC 2822 email. Useful for parsing headers or forwarding.

## Tips

- **Pagination**: All list endpoints support `page` and `per_page` (max 200). Default: page=1, per_page=50.
- **Performance**: Specify `inbox` parameter in search queries — cross-inbox search is slower.
- **Large inboxes**: lkml has millions of emails. Use `d:` date prefix to narrow results.
- **Patch series**: Search for `s:"PATCH v3 0/"` to find cover letters, then get the thread.
- **Message-ID shortcut**: If you have a Message-ID, paste it directly in the search query (no prefix needed).

## Error Handling

- `404` — inbox/message/thread not found
- `422` — invalid parameters (page < 1, per_page > 200, empty query)
- Search results may include a `warning` field if a query timed out partially.
