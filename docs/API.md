# lore-mirror API Reference

Base URL: `http://localhost:8000` (production) or `http://localhost:3000` (dev, proxied)

All responses are JSON. Dates are ISO 8601 format.

**MCP Server:** An MCP server (`server/mcp_server.py`) wraps this REST API with 7 structured tools for direct AI access. Claude Code auto-discovers it via `.mcp.json` (stdio transport). See [MCP Server](#mcp-server) section below for setup and tool details.

---

## Overview

This is a local mirror of lore.kernel.org. It stores Linux kernel mailing list emails in per-inbox SQLite databases with full-text search. Use these APIs to browse inboxes, read emails, trace discussion threads, and search across all archived messages.

### Quick Start for AI Agents

**Important: Always start by discovering available inboxes.** Not all ~200 lore.kernel.org mailing lists may be mirrored locally. Passing an unavailable inbox name to the search API will return no results.

1. **First**, call `GET /api/inboxes` to get the list of available mailing lists with descriptions
   - Each inbox has a detailed `description` field listing the topics and keywords it covers
   - Use this to determine which inbox is relevant to your query
   - If unsure, use `GET /api/locate?q=keyword` to fuzzy-match inbox names and descriptions
2. Call `GET /api/search?q=your+query&inbox={name}` to search within a specific inbox
   - Always specify `inbox` parameter for better performance and precision
   - Omit `inbox` only when you need to search across all available inboxes
3. Call `GET /api/messages/{message_id}` to read a specific email
4. Call `GET /api/threads/{message_id}` to see the full discussion thread

**Example workflow:**
```
GET /api/inboxes                              → find linux-mm covers "OOM killer, hugepages"
GET /api/search?q=OOM+reaper&inbox=linux-mm   → find relevant emails
GET /api/messages/{message_id}                → read the email
GET /api/threads/{message_id}                 → read the full discussion
```

---

## Endpoints

### GET /api/stats

Overall statistics.

**Response:**
```json
{
  "total_messages": 113357,
  "total_inboxes": 1,
  "database_size_bytes": 2941018112,
  "latest_message": {
    "date": "2026-03-05T17:01:39+09:00",
    "subject": "Re: [PATCH v5 2/9] ...",
    "sender": "Name <email@example.com>"
  }
}
```

---

### GET /api/inboxes

List all available inboxes (mailing lists) with message counts and date ranges.

**Response:**
```json
[
  {
    "name": "lkml",
    "description": "The Linux Kernel Mailing List",
    "message_count": 113357,
    "earliest": "2025-10-01T19:15:46+02:00",
    "latest": "2026-03-05T17:01:39+09:00"
  }
]
```

---

### GET /api/locate?q={query}

Fuzzy-match inbox names and descriptions. Useful for finding which mailing list covers a topic.

**Parameters:**
| Name | Required | Description |
|------|----------|-------------|
| q | yes | Search string to match against inbox name or description |

**Example:** `GET /api/locate?q=filesystem`

**Response:**
```json
{
  "query": "filesystem",
  "matches": [
    {"name": "linux-fsdevel", "description": "Linux filesystem development"},
    {"name": "linux-xfs", "description": "Linux XFS filesystem development"},
    {"name": "linux-btrfs", "description": "Linux Btrfs filesystem development"}
  ]
}
```

---

### GET /api/inboxes/{name}

Browse messages in a specific inbox, newest first, with pagination.

**Parameters:**
| Name | Required | Default | Description |
|------|----------|---------|-------------|
| name | yes (path) | | Inbox name (e.g. `lkml`) |
| page | no | 1 | Page number (1-based) |
| per_page | no | 50 | Results per page (1-200) |
| after | no | | Keyset cursor from previous page's `next_cursor` (overrides page offset) |
| last | no | 0 | Set to 1 to efficiently fetch the last page (uses reverse index scan, avoids large OFFSET) |

**Pagination modes:**
- **Offset** (default): `?page=N` — simple but slow for large page numbers
- **Keyset** (recommended for sequential): `?page=N&after=CURSOR` — uses `next_cursor` from previous response, efficient for any depth
- **Last page**: `?last=1` — fetches the last page via reverse index scan, instant even on million-row inboxes
- **Reverse scan optimization**: Pages in the second half are automatically served via reverse index scan, so pages near the end are just as fast as pages near the beginning

**Example:** `GET /api/inboxes/lkml?page=1&per_page=20`

**Response:**
```json
{
  "inbox": {"name": "lkml", "description": "The Linux Kernel Mailing List"},
  "total": 113357,
  "page": 1,
  "per_page": 20,
  "pages": 5668,
  "messages": [
    {
      "id": 113374,
      "message_id": "DGUOW0UMG5DY.GYRK410GIRUJ@nvidia.com",
      "subject": "Re: [PATCH v5 2/9] gpu: nova-core: ...",
      "sender": "Name <email@example.com>",
      "date": "2026-03-05T17:01:39+09:00",
      "in_reply_to": "24b74629-87e8-463c-ad21-376a5097823e@nvidia.com"
    }
  ]
}
```

---

### GET /api/messages/{message_id}

Get full details of a single email. Searches across all inboxes automatically.

**Parameters:**
| Name | Required | Description |
|------|----------|-------------|
| message_id | yes (path) | The email's Message-ID header value (URL-encode `@` as `%40`) |

**Example:** `GET /api/messages/DGUOW0UMG5DY.GYRK410GIRUJ%40nvidia.com`

**Response:**
```json
{
  "id": 113374,
  "message_id": "DGUOW0UMG5DY.GYRK410GIRUJ@nvidia.com",
  "inbox_name": "lkml",
  "subject": "Re: [PATCH v5 2/9] gpu: nova-core: ...",
  "sender": "Eliot Courtney <ecourtney@nvidia.com>",
  "date": "2026-03-05T17:01:39+09:00",
  "in_reply_to": "24b74629-87e8-463c-ad21-376a5097823e@nvidia.com",
  "references_ids": ["first-msg-id@example.com", "second@example.com"],
  "body_text": "The full plain-text body of the email...",
  "body_html": "",
  "headers": {
    "From": "Eliot Courtney <ecourtney@nvidia.com>",
    "To": "...",
    "Cc": "...",
    "Subject": "...",
    "Date": "...",
    "Message-ID": "<DGUOW0UMG5DY.GYRK410GIRUJ@nvidia.com>"
  },
  "git_commit": "49da48c255140a99794681352597808a404cf08b",
  "epoch": 18,
  "attachments": [
    {"id": 1, "filename": "patch.diff", "content_type": "text/x-diff", "size": 4096}
  ]
}
```

**Notes:**
- `body_text` contains the email body. For patch emails, the diff is inline in the body.
- `raw_email` is excluded from this endpoint (use `/api/raw` instead).
- `headers` is the complete parsed email headers as a JSON object.
- `references_ids` is a list of Message-IDs in the References header, useful for thread reconstruction.
- `in_reply_to` is the Message-ID of the parent email.

---

### GET /api/raw?id={message_id}

Download the original raw email (RFC 2822 format). Useful for AI parsing or forwarding.

**Parameters:**
| Name | Required | Default | Description |
|------|----------|---------|-------------|
| id | yes (query) | | Message-ID |
| download | no | 0 | Set to 1 to download as `.patch` file (attachment disposition). Default returns `.eml` file. |

**Response:** Raw email bytes with `Content-Type: message/rfc822` and a subject-based filename.

---

### GET /api/series?id={message_id}

Get patch series metadata (JSON) or download as mbox with review trailers injected. Implements b4-like intelligence: version detection, cover letter exclusion, and trailer collection from review replies.

**Parameters:**
| Name | Required | Default | Description |
|------|----------|---------|-------------|
| id | yes (query) | | Any Message-ID in the patch thread |
| download | no | 0 | Set to 1 to download mboxrd file instead of JSON metadata |

**JSON response** (default, `download=0`):
```json
{
  "version": 2,
  "total": 3,
  "cover_letter": { "message_id": "...", "subject": "...", "sender": "..." },
  "patches": [
    { "number": 1, "message_id": "...", "subject": "...", "trailers": ["Reviewed-by: A <a@b>"] }
  ],
  "total_trailers": 5,
  "download_url": "/api/series?id=...&download=1"
}
```

**Download response** (`download=1`): mboxrd file with:
- Only the latest version patches (e.g. v2 patches if thread contains v1 and v2)
- Cover letter (0/N) excluded
- Review trailers (Reviewed-by, Acked-by, etc.) from reply emails injected into each patch before the `---` separator

---

### GET /api/threads/{message_id}

Get the full discussion thread containing the specified message. The API walks up to find the root message, then walks down to find all replies.

**Parameters:**
| Name | Required | Description |
|------|----------|-------------|
| message_id | yes (path) | Any Message-ID in the thread |

**Example:** `GET /api/threads/5b5c8a8b-5832-4566-af45-dee6818fa44c%40hartkopp.net`

**Response:**
```json
{
  "root": "20260110-can_usb-fix-memory-leak-v1-0-4a7c082a7081@pengutronix.de",
  "total": 9,
  "inbox": "lkml",
  "messages": [
    {
      "id": 30139,
      "message_id": "20260110-can_usb-fix-memory-leak-v1-0-4a7c082a7081@pengutronix.de",
      "subject": "[PATCH can 0/5] can: usb: fix URB memory leaks",
      "sender": "Marc Kleine-Budde <mkl@pengutronix.de>",
      "date": "2026-01-10T18:28:51+01:00",
      "in_reply_to": ""
    },
    {
      "id": 30138,
      "message_id": "20260110-can_usb-fix-memory-leak-v1-1-4a7c082a7081@pengutronix.de",
      "subject": "[PATCH can 1/5] can: ems_usb: ...: fix URB memory leak",
      "sender": "Marc Kleine-Budde <mkl@pengutronix.de>",
      "date": "2026-01-10T18:28:52+01:00",
      "in_reply_to": "20260110-can_usb-fix-memory-leak-v1-0-4a7c082a7081@pengutronix.de"
    }
  ]
}
```

**Notes:**
- Messages are sorted by date (oldest first).
- Use `in_reply_to` to reconstruct the tree structure: messages with `in_reply_to == ""` are thread roots, others are replies to the specified parent.
- `root` is the Message-ID of the thread root (may not exist in the database if it's in a different inbox or epoch).

---

### GET /api/search

Full-text search with lore.kernel.org-compatible prefix syntax. Uses SQLite FTS5 with BM25 ranking.

**Parameters:**
| Name | Required | Default | Description |
|------|----------|---------|-------------|
| q | yes | | Search query with optional prefix syntax (see below) |
| inbox | no | all | Limit search to this inbox name |
| page | no | 1 | Page number |
| per_page | no | 50 | Results per page (1-200) |

**Search prefix syntax** (compatible with lore.kernel.org):

| Prefix | Description | Example |
|--------|-------------|---------|
| `s:` | Match in Subject | `s:PATCH` `s:"memory leak"` |
| `f:` | Match From/sender | `f:torvalds` |
| `b:` | Match in message body | `b:kasan` `b:"use after free"` |
| `bs:` | Match in Subject + body | `bs:regression` |
| `d:` | Date range (ISO format) | `d:2026-01-01..2026-03-01` |
| `t:` | Match To header | `t:linux-mm@kvack.org` |
| `c:` | Match Cc header | `c:stable@vger.kernel.org` |
| `a:` | Match any address (From/To/Cc) | `a:torvalds` |
| `tc:` | Match To + Cc | `tc:netdev@vger.kernel.org` |
| `m:` | Match Message-ID (exact) | `m:20260110-can@pengutronix.de` |

**Message-ID auto-detection:** If the search query contains `@` and no spaces, it is automatically treated as a Message-ID lookup (no prefix needed). Angle brackets are stripped: `<foo@bar.com>` → `foo@bar.com`.

**Date range formats:**
- `d:2026-01-01..2026-03-01` — between two dates
- `d:2026-01-01..` — from a date onwards
- `d:..2026-03-01` — up to a date
- `d:2026-01-15` — a single day

**Operators:** AND (default), OR, NOT, `"exact phrase"`, `prefix*`

**Examples:**
```
memory leak                          plain text search
s:PATCH f:torvalds                   patches from Torvalds
s:"use after free" d:2026-01-01..    UAF patches since Jan 2026
f:torvalds d:2026-01-01..2026-03-01  Torvalds' emails in date range
b:kasan NOT s:Re:                    body contains "kasan", not a reply
s:PATCH b:mm_struct                  patches mentioning mm_struct in body
a:stable@vger.kernel.org             emails to/from/cc stable list
```

**Example API call:** `GET /api/search?q=s%3APATCH+f%3Atorvalds+d%3A2026-01-01..&inbox=lkml&per_page=10`

**Response:**
```json
{
  "query": "s:PATCH f:torvalds d:2026-01-01..",
  "total": 42,
  "page": 1,
  "per_page": 10,
  "pages": 5,
  "messages": [
    {
      "id": 30139,
      "message_id": "20260110-can_usb-fix-memory-leak-v1-0-4a7c082a7081@pengutronix.de",
      "subject": "[PATCH can 0/5] can: usb: fix URB memory leaks",
      "sender": "Marc Kleine-Budde <mkl@pengutronix.de>",
      "date": "2026-01-10T18:28:51+01:00",
      "in_reply_to": "",
      "inbox_name": "lkml",
      "snippet": "An URB <mark>memory</mark> <mark>leak</mark> was recently fixed..."
    }
  ]
}
```

**Notes:**
- Results are ranked by relevance (BM25) when using text/sender search (s:, f:, b:, bs:), or by date when using only filters (d:, t:, c:, a:, tc:).
- `snippet` contains a text excerpt with `<mark>` tags around matched terms. Empty for filter-only queries.
- When searching across all inboxes, `inbox_name` indicates which inbox each result comes from.
- For best performance on large datasets, always specify `inbox` parameter.

---

### GET /api/sync/status

Check the status of the background sync process (read-only).

**Response (idle):**
```json
{"running": false}
```

**Response (after sync):**
```json
{
  "running": false,
  "started_at": "2026-03-05 19:26:21",
  "finished_at": "2026-03-05 19:35:42",
  "current_inbox": null,
  "completed": ["lkml"],
  "total_inboxes": 1,
  "summaries": [
    {
      "inbox": "lkml",
      "epochs_fetched": 19,
      "new_commits": 156,
      "messages_imported": 113513,
      "errors": []
    }
  ]
}
```

---

## Common AI Workflows

**Step 0 (always do this first):** Call `GET /api/inboxes` to learn which mailing lists are available and what topics each one covers. Cache the result — the list rarely changes.

### Find discussions about a kernel topic

```
0. GET /api/inboxes → find that linux-mm covers "OOM killer, hugepages, mmap..."
1. GET /api/search?q=OOM+reaper&inbox=linux-mm
2. Pick a relevant result → GET /api/threads/{message_id}
3. Read the full thread to understand the discussion
```

### Find patches from a specific developer

```
0. GET /api/inboxes → confirm lkml is available
1. GET /api/search?q=s%3APATCH+f%3Atorvalds+d%3A2026-01-01..&inbox=lkml
   (s:PATCH f:torvalds d:2026-01-01..)
2. For each patch series, get the cover letter (0/N) thread
3. GET /api/messages/{message_id} to read patch details
```

### Find patches for a specific subsystem

```
0. GET /api/locate?q=btrfs → check if linux-btrfs is available
   (if not available, fall back to searching lkml)
1. GET /api/search?q=s%3APATCH+b%3Adefrag+d%3A2026-01-01..&inbox=linux-btrfs
   (s:PATCH b:defrag d:2026-01-01..)
```

### Search by email address (To/Cc/From)

```
GET /api/search?q=a%3Atorvalds%40linux-foundation.org&inbox=lkml
(a:torvalds@linux-foundation.org)
```

### Search for emails about a bug type in a date range

```
GET /api/search?q=b%3A%22use+after+free%22+d%3A2026-02-01..2026-03-01&inbox=lkml
(b:"use after free" d:2026-02-01..2026-03-01)
```

### Download a patch series with trailers

```
1. Find a patch: GET /api/search?q=s%3APATCH+f%3Aauthor&inbox=netdev
2. Get series metadata: GET /api/series?id={message_id}
   → JSON with version, patch count, collected review trailers
3. Download mbox: GET /api/series?id={message_id}&download=1
   → mboxrd with trailers injected, ready for git am
```

### Get raw email for processing

```
GET /api/raw?id={message_id}
→ Returns RFC 2822 raw email as .eml file with subject-based filename
GET /api/raw?id={message_id}&download=1
→ Returns as .patch file (attachment disposition)
```

### Discover which mailing list to search

```
1. GET /api/locate?q=nvme    → finds linux-nvme inbox
2. GET /api/search?q=timeout+error&inbox=linux-nvme
```

### Trace a review conversation

```
1. Search for the patch: GET /api/search?q=s%3A%22PATCH+v3%22+driver+name&inbox=lkml
2. Get the thread: GET /api/threads/{message_id}
3. Read each message in the thread chronologically to follow the review
```

---

## MCP Server

MCP (Model Context Protocol) 服务器提供结构化工具，让 AI 直接访问邮件列表数据，无需手写 HTTP 请求。

### 前置条件

- REST API 运行在 `:8000`（MCP server 通过 httpx 调用本地 API）
- Python 依赖：`pip3 install mcp httpx`

### Claude Code 配置

**在本项目中：** 自动生效。项目根目录的 `.mcp.json` 已配置好，Claude Code 打开本项目时自动连接。

**在其他项目中使用（如内核源码树）：**

全局配置（推荐） — 编辑 `~/.claude.json`，添加 `mcpServers`：

```json
{
  "mcpServers": {
    "lore-mirror": {
      "command": "python3",
      "args": ["/path/to/lore-mirror/server/mcp_server.py"]
    }
  }
}
```

或在目标项目根目录创建/编辑 `.mcp.json`，添加同样的配置。

> `args` 中必须使用 `mcp_server.py` 的绝对路径。

输入 `/mcp` 查看连接状态。

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LORE_API_URL` | `http://localhost:8000` | REST API 基础地址 |

### 工具列表

所有工具名以 `lore_` 为前缀，只读、幂等。

| 工具 | 对应 REST API | 说明 |
|------|---------------|------|
| `lore_list_inboxes` | `GET /api/inboxes` | 列出所有可用邮件列表（含消息计数和日期范围） |
| `lore_locate_inbox` | `GET /api/locate` | 按关键词模糊匹配邮件列表名称和描述 |
| `lore_search_emails` | `GET /api/search` | 搜索邮件，支持 lore 前缀语法（s: f: b: d: 等） |
| `lore_get_message` | `GET /api/messages/{id}` | 获取单封邮件（解析后内容，不含 raw_email） |
| `lore_get_thread` | `GET /api/threads/{id}` | 获取完整讨论线程（包含所有回复） |
| `lore_browse_inbox` | `GET /api/inboxes/{name}` | 浏览邮件列表，按时间倒序，支持 keyset 分页 |
| `lore_get_raw_email` | `GET /api/raw` | 获取原始 RFC 2822 邮件 |

### 故障排查

| 症状 | 原因 | 解决 |
|------|------|------|
| `/mcp` 显示 disconnected | REST API 未运行 | 启动 API：`./start.sh` |
| 工具返回连接错误 | API 地址不对 | 设置 `LORE_API_URL` 环境变量 |
| 搜索返回空结果 | inbox 未镜像 | 先调用 `lore_list_inboxes` 确认可用列表 |
