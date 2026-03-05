# lore-mirror API Reference

Base URL: `http://localhost:8000` (production) or `http://localhost:3000` (dev, proxied)

All responses are JSON. Dates are ISO 8601 format.

---

## Overview

This is a local mirror of lore.kernel.org. It stores Linux kernel mailing list emails in per-inbox SQLite databases with full-text search. Use these APIs to browse inboxes, read emails, trace discussion threads, and search across all archived messages.

### Quick Start for AI Agents

1. Call `GET /api/inboxes` to see available mailing lists
2. Call `GET /api/search?q=your+query` to find relevant emails
3. Call `GET /api/messages/{message_id}` to read a specific email
4. Call `GET /api/threads/{message_id}` to see the full discussion thread

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
| Name | Required | Description |
|------|----------|-------------|
| id | yes (query) | Message-ID |

**Response:** Raw email bytes with `Content-Type: message/rfc822`

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

Full-text search across all inboxes (or a specific one). Uses SQLite FTS5 with BM25 ranking.

**Parameters:**
| Name | Required | Default | Description |
|------|----------|---------|-------------|
| q | yes | | Search query (FTS5 syntax: words, phrases `"exact phrase"`, AND/OR/NOT) |
| inbox | no | all | Limit search to this inbox |
| sender | no | | Filter by sender (substring match) |
| date_from | no | | Start date (ISO 8601, e.g. `2026-01-01`) |
| date_to | no | | End date |
| page | no | 1 | Page number |
| per_page | no | 50 | Results per page (1-200) |

**Example:** `GET /api/search?q=memory+leak&inbox=lkml&per_page=10`

**FTS5 query syntax examples:**
- `memory leak` — matches emails containing both words
- `"memory leak"` — exact phrase match
- `memory OR leak` — either word
- `memory NOT leak` — contains "memory" but not "leak"
- `memory*` — prefix match (memory, memoryleak, etc.)

**Response:**
```json
{
  "query": "memory leak",
  "total": 1324,
  "page": 1,
  "per_page": 10,
  "pages": 133,
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
- Results are ranked by relevance (BM25).
- `snippet` contains a text excerpt with `<mark>` tags around matched terms.
- When searching across all inboxes, `inbox_name` indicates which inbox each result comes from.

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

### Find discussions about a kernel topic

```
1. GET /api/search?q=io_uring+splice+zero+copy
2. Pick a relevant result → GET /api/threads/{message_id}
3. Read the full thread to understand the discussion
```

### Find patches for a specific subsystem

```
1. GET /api/search?q=subject:PATCH+btrfs+defrag&date_from=2026-01-01
2. For each patch series, get the cover letter (0/N) thread
3. GET /api/messages/{message_id} to read patch details
```

### Get raw email for processing

```
GET /api/raw?id={message_id}
→ Returns RFC 2822 raw email, suitable for email parsers or LLM context
```

### Discover which mailing list to search

```
1. GET /api/locate?q=nvme    → finds linux-nvme inbox
2. GET /api/search?q=timeout+error&inbox=linux-nvme
```

### Trace a review conversation

```
1. Search for the patch: GET /api/search?q="PATCH v3"+driver+name
2. Get the thread: GET /api/threads/{message_id}
3. Read each message in the thread chronologically to follow the review
```
