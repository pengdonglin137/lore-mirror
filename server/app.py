#!/usr/bin/env python3
"""
FastAPI backend for lore mirror.

Each inbox has its own SQLite database in the db/ directory.

Usage:
    uvicorn server.app:app --host 0.0.0.0 --port 8000 --reload
"""

import json
import re
import sqlite3
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, FileResponse
from fastapi.staticfiles import StaticFiles

# ── In-memory cache ──────────────────────────────────
_cache: dict[str, tuple[float, any]] = {}
CACHE_TTL = 300  # 5 minutes


def cache_get(key: str):
    """Get from cache if not expired."""
    entry = _cache.get(key)
    if entry and time.monotonic() - entry[0] < CACHE_TTL:
        return entry[1]
    return None


def cache_set(key: str, value):
    """Store in cache."""
    _cache[key] = (time.monotonic(), value)

import sys
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from config_utils import load_config as _load_config

FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"

_config = _load_config()
DB_DIR = Path(_config["database"]["dir"])
INBOXES_CONFIG = {ib["name"]: ib.get("description", "") for ib in _config["inboxes"]}

app = FastAPI(title="Lore Mirror API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


QUERY_TIMEOUT_SECONDS = 30


def get_db(inbox_name: str) -> sqlite3.Connection:
    """Open a connection to an inbox's database."""
    db_path = DB_DIR / f"{inbox_name}.db"
    if not db_path.exists():
        raise HTTPException(404, f"Inbox '{inbox_name}' not found")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")

    # Set a progress handler to abort queries that run too long.
    # The callback is invoked every ~100k VM instructions (~50-100ms).
    deadline = time.monotonic() + QUERY_TIMEOUT_SECONDS

    def _progress():
        if time.monotonic() > deadline:
            return 1  # non-zero → abort
        return 0

    conn.set_progress_handler(_progress, 100_000)
    return conn


def get_available_inboxes() -> list[str]:
    """List inbox names that have a database file."""
    if not DB_DIR.exists():
        return []
    return sorted(
        p.stem for p in DB_DIR.glob("*.db")
        if p.stem != "schema"
    )


def row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


# ── Inboxes ──────────────────────────────────────────

@app.get("/api/inboxes")
def list_inboxes():
    """List all inboxes with message counts (cached 5 min)."""
    cached = cache_get("inboxes_list")
    if cached is not None:
        return cached

    results = []
    for name in get_available_inboxes():
        try:
            conn = get_db(name)
            # Use fast queries: COUNT via covering index, date range via index scan
            count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            earliest = conn.execute(
                "SELECT date FROM messages WHERE date >= '1990' ORDER BY date ASC LIMIT 1"
            ).fetchone()
            latest = conn.execute(
                "SELECT date FROM messages WHERE date <= '2027' ORDER BY date DESC LIMIT 1"
            ).fetchone()
            conn.close()
            results.append({
                "name": name,
                "description": INBOXES_CONFIG.get(name, ""),
                "message_count": count,
                "earliest": earliest["date"] if earliest else None,
                "latest": latest["date"] if latest else None,
            })
        except Exception:
            results.append({
                "name": name,
                "description": INBOXES_CONFIG.get(name, ""),
                "message_count": 0,
                "earliest": None,
                "latest": None,
            })

    # Sort by latest message date descending (most active first), then by name
    results.sort(key=lambda x: (x.get("latest") or "", x.get("name", "")), reverse=True)

    cache_set("inboxes_list", results)
    return results


@app.get("/api/locate")
def locate_inbox(q: str = Query(..., min_length=1)):
    """Fuzzy match inbox names (like lore's 'locate inbox')."""
    q_lower = q.lower()
    all_inboxes = []

    # Include configured inboxes (even if not yet imported)
    seen = set()
    for ib in _config["inboxes"]:
        name = ib["name"]
        seen.add(name)
        all_inboxes.append({"name": name, "description": ib.get("description", "")})

    # Also include any imported but unconfigured inboxes
    for name in get_available_inboxes():
        if name not in seen:
            all_inboxes.append({"name": name, "description": ""})

    # Match: name contains query, or description contains query
    matches = [
        ib for ib in all_inboxes
        if q_lower in ib["name"].lower() or q_lower in ib["description"].lower()
    ]

    return {"query": q, "matches": matches}


@app.get("/api/inboxes/{name}")
def get_inbox(
    name: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    after: Optional[str] = None,
    last: int = Query(0),
):
    """Get messages for an inbox, newest first.

    Supports keyset pagination via `after` cursor for efficient deep pagination.
    When `after` is provided, it takes precedence over `page` offset.
    The cursor format is "date|id" from the previous page's `next_cursor`.
    With `last=1`, efficiently returns the last page (oldest messages) without OFFSET.
    """
    conn = get_db(name)

    # Use cached total count (expensive COUNT on millions of rows)
    cache_key = f"inbox_total:{name}"
    total = cache_get(cache_key)
    if total is None:
        total = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        cache_set(cache_key, total)

    pages = (total + per_page - 1) // per_page

    if last:
        # Last page optimization: fetch oldest N messages ASC, then reverse.
        # Avoids catastrophic OFFSET on large inboxes (lkml: ~6M rows).
        page = pages
        last_page_size = total - (pages - 1) * per_page
        messages = conn.execute(
            """SELECT id, message_id, subject, sender, date, in_reply_to
            FROM messages
            WHERE date >= '1990'
            ORDER BY date ASC, id ASC
            LIMIT ?""",
            (last_page_size,),
        ).fetchall()
        messages = list(reversed(messages))
    elif after:
        # Keyset pagination: fetch rows after the cursor position
        parts = after.split("|", 1)
        if len(parts) == 2:
            cursor_date, cursor_id = parts[0], int(parts[1])
            messages = conn.execute(
                """SELECT id, message_id, subject, sender, date, in_reply_to
                FROM messages
                WHERE date <= '2027'
                  AND (date < ? OR (date = ? AND id < ?))
                ORDER BY date DESC, id DESC
                LIMIT ?""",
                (cursor_date, cursor_date, cursor_id, per_page),
            ).fetchall()
        else:
            messages = []
    else:
        # Traditional OFFSET pagination
        offset = (page - 1) * per_page
        messages = conn.execute(
            """SELECT id, message_id, subject, sender, date, in_reply_to
            FROM messages
            WHERE date <= '2027'
            ORDER BY date DESC, id DESC
            LIMIT ? OFFSET ?""",
            (per_page, offset),
        ).fetchall()

    conn.close()

    msg_list = [row_to_dict(m) for m in messages]

    # Build next_cursor from the last result
    next_cursor = None
    if msg_list and len(msg_list) == per_page:
        last_msg = msg_list[-1]
        next_cursor = f"{last_msg['date']}|{last_msg['id']}"

    result = {
        "inbox": {"name": name, "description": INBOXES_CONFIG.get(name, "")},
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
        "messages": msg_list,
    }
    if next_cursor:
        result["next_cursor"] = next_cursor
    return result


# ── Messages ─────────────────────────────────────────

@app.get("/api/messages/{message_id:path}")
def get_message(message_id: str):
    """Get a single message by Message-ID. Searches all inbox databases."""
    for name in get_available_inboxes():
        try:
            conn = get_db(name)
        except HTTPException:
            continue

        msg = conn.execute(
            "SELECT * FROM messages WHERE message_id=?",
            (message_id,),
        ).fetchone()

        if msg:
            result = row_to_dict(msg)
            result.pop("raw_email", None)
            result["inbox_name"] = name
            if result.get("headers"):
                result["headers"] = json.loads(result["headers"])
            if result.get("references_ids"):
                result["references_ids"] = json.loads(result["references_ids"])

            attachments = conn.execute(
                """SELECT id, filename, content_type, LENGTH(content) as size
                FROM attachments WHERE message_id=?""",
                (msg["id"],),
            ).fetchall()
            result["attachments"] = [row_to_dict(a) for a in attachments]
            conn.close()
            return result

        conn.close()

    raise HTTPException(404, "Message not found")


@app.get("/api/raw")
def get_message_raw(id: str = Query(..., alias="id"), download: int = Query(0)):
    """Get raw email content. With download=1, returns as .patch attachment."""
    for name in get_available_inboxes():
        try:
            conn = get_db(name)
        except HTTPException:
            continue

        row = conn.execute(
            "SELECT raw_email, subject FROM messages WHERE message_id=?", (id,)
        ).fetchone()
        conn.close()

        if row and row["raw_email"]:
            safe = _sanitize_filename(row["subject"] or "message")
            if download:
                ext, disposition = ".patch", "attachment"
            else:
                ext, disposition = ".eml", "attachment"
            headers = {
                "Content-Type": "message/rfc822",
                "Content-Disposition": f'{disposition}; filename="{safe}{ext}"',
            }
            return Response(content=row["raw_email"], headers=headers)

    raise HTTPException(404, "Message not found")


def _sanitize_filename(subject: str) -> str:
    """Turn an email subject into a safe filename."""
    # Remove [PATCH ...] prefix for cleaner filenames
    name = re.sub(r'^\[.*?\]\s*', '', subject)
    # Replace unsafe chars
    name = re.sub(r'[^\w\s\-.]', '', name).strip()
    name = re.sub(r'\s+', '-', name)
    return name[:80] or "patch"


def _find_thread_messages(message_id: str):
    """Find all message_ids in a thread. Returns (conn, inbox_name, thread_ids) or raises 404."""
    target_conn = None
    target_inbox = None

    for name in get_available_inboxes():
        try:
            conn = get_db(name)
        except HTTPException:
            continue
        row = conn.execute(
            "SELECT message_id FROM messages WHERE message_id=?", (message_id,),
        ).fetchone()
        if row:
            target_conn = conn
            target_inbox = name
            break
        conn.close()

    if not target_conn:
        raise HTTPException(404, "Message not found")

    conn = target_conn

    # Walk up to root
    start = conn.execute(
        "SELECT message_id, in_reply_to FROM messages WHERE message_id=?",
        (message_id,),
    ).fetchone()
    root_msg_id = start["message_id"]
    visited = {root_msg_id}
    current_reply_to = start["in_reply_to"]

    while current_reply_to and current_reply_to not in visited:
        visited.add(current_reply_to)
        parent = conn.execute(
            "SELECT message_id, in_reply_to FROM messages WHERE message_id=?",
            (current_reply_to,),
        ).fetchone()
        if parent:
            root_msg_id = parent["message_id"]
            current_reply_to = parent["in_reply_to"]
        else:
            root_msg_id = current_reply_to
            break

    # BFS to collect all thread message_ids
    thread_ids = set()
    queue = [root_msg_id]
    while queue:
        current = queue.pop(0)
        if current in thread_ids:
            continue
        thread_ids.add(current)
        replies = conn.execute(
            "SELECT message_id FROM messages WHERE in_reply_to=?", (current,),
        ).fetchall()
        for r in replies:
            if r["message_id"] not in thread_ids:
                queue.append(r["message_id"])

    return conn, target_inbox, thread_ids


_PATCH_NUM_RE = re.compile(r'\[PATCH(?:\s+\S+)*\s+(\d+)/(\d+)\]', re.IGNORECASE)

# Version-aware patch subject regex: [PATCH v2 3/5], [PATCH net-next v3 0/2], [PATCH 1/1]
# Version (vN) can appear anywhere between PATCH and N/M
_PATCH_VERSION_RE = re.compile(
    r'\[PATCH\b([^\]]*?)\s+(\d+)/(\d+)\]', re.IGNORECASE
)
_VERSION_NUM_RE = re.compile(r'\bv(\d+)\b', re.IGNORECASE)

_TRAILER_RE = re.compile(
    r'^(Reviewed-by|Acked-by|Tested-by|Reported-by|Suggested-by|Co-developed-by):\s+.+$',
    re.MULTILINE,
)

# Trailers that already exist in patch emails (for dedup and insertion point)
_EXISTING_TRAILER_RE = re.compile(
    r'^(Signed-off-by|Reviewed-by|Acked-by|Tested-by|Reported-by|Suggested-by|Co-developed-by|Cc|Link|Closes|Fixes):\s+.+$',
    re.MULTILINE,
)


def _parse_patch_subject(subject: str) -> tuple[int, int, int] | None:
    """Parse [PATCH vN M/T] from subject. Returns (version, number, total) or None."""
    if not subject:
        return None
    m = _PATCH_VERSION_RE.search(subject)
    if not m:
        return None
    tags = m.group(1)  # everything between PATCH and N/M
    number = int(m.group(2))
    total = int(m.group(3))
    # Extract version from tags (e.g. "net-next v3" → 3)
    vm = _VERSION_NUM_RE.search(tags) if tags else None
    version = int(vm.group(1)) if vm else 1
    return (version, number, total)


def _extract_trailers(body_text: str) -> list[str]:
    """Extract review trailers (Reviewed-by, Acked-by, etc.) from email body."""
    if not body_text:
        return []
    return [m.group(0) for m in _TRAILER_RE.finditer(body_text)]


def _find_patch_ancestor(message_id: str, msg_map: dict) -> str | None:
    """Walk in_reply_to chain to find which patch a reply is about."""
    visited = set()
    current = message_id
    while current and current not in visited:
        visited.add(current)
        msg = msg_map.get(current)
        if not msg:
            return None
        parent_id = msg.get("in_reply_to")
        if not parent_id:
            return None
        parent = msg_map.get(parent_id)
        if not parent:
            return None
        # If parent is a patch (not a reply), return it
        parent_subj = parent.get("subject") or ""
        if "[PATCH" in parent_subj.upper() and not re.match(r'^\s*Re:', parent_subj, re.IGNORECASE):
            return parent_id
        current = parent_id
    return None


def _inject_trailers(raw_email: str, trailers: list[str]) -> str:
    """Insert trailer lines before the --- separator in raw email.

    Finds the commit message's --- separator and inserts new trailers
    after any existing trailers (Signed-off-by, etc.) but before ---.
    """
    if not trailers:
        return raw_email

    # Find the \n---\n separator (diffstat marker)
    separator_idx = raw_email.find("\n---\n")
    if separator_idx == -1:
        return raw_email

    # Look backwards from --- to find the last existing trailer line
    before_sep = raw_email[:separator_idx]
    lines = before_sep.split("\n")

    # Find the last trailer line index
    last_trailer_idx = -1
    for i in range(len(lines) - 1, -1, -1):
        if _EXISTING_TRAILER_RE.match(lines[i]):
            last_trailer_idx = i
            break

    trailer_block = "\n".join(trailers)

    if last_trailer_idx >= 0:
        # Insert after the last existing trailer
        insert_point = "\n".join(lines[:last_trailer_idx + 1])
        rest = "\n".join(lines[last_trailer_idx + 1:])
        return insert_point + "\n" + trailer_block + "\n" + rest + raw_email[separator_idx:]
    else:
        # No existing trailers found, insert just before ---
        return before_sep + "\n" + trailer_block + raw_email[separator_idx:]


def _raw_to_str(raw) -> str:
    """Convert raw_email (bytes/memoryview/str) to str."""
    if isinstance(raw, memoryview):
        raw = bytes(raw)
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    return raw


def _build_mboxrd(patches: list[tuple[int, dict]], trailers_by_mid: dict[str, list[str]] | None = None) -> str:
    """Build mboxrd content from sorted patch list, optionally injecting trailers."""
    parts = []
    for _, row in patches:
        raw = _raw_to_str(row["raw_email"])
        # Inject trailers if available
        if trailers_by_mid:
            mid = row["message_id"]
            t = trailers_by_mid.get(mid, [])
            if t:
                raw = _inject_trailers(raw, t)
        # Escape From_ lines in body (mboxrd convention)
        escaped_lines = []
        for line in raw.split("\n"):
            if line.startswith("From "):
                escaped_lines.append(">" + line)
            else:
                escaped_lines.append(line)
        parts.append("From mboxrd@z Thu Jan  1 00:00:00 1970\n" + "\n".join(escaped_lines) + "\n")
    return "\n".join(parts)


@app.get("/api/series")
def get_series(id: str = Query(..., alias="id"), download: int = Query(0)):
    """Get patch series metadata (JSON) or download as mbox with trailers injected.

    Without download=1: returns JSON with version, patches, cover letter, trailers.
    With download=1: returns mboxrd file with review trailers injected into patches.
    """
    conn, inbox_name, thread_ids = _find_thread_messages(id)

    if not thread_ids:
        conn.close()
        raise HTTPException(404, "No thread messages found")

    # Fetch all thread messages with body and raw_email
    placeholders = ",".join("?" for _ in thread_ids)
    rows = conn.execute(
        f"""SELECT message_id, subject, sender, date, in_reply_to, body_text, raw_email
        FROM messages WHERE message_id IN ({placeholders})""",
        list(thread_ids),
    ).fetchall()
    conn.close()

    # Build message map for reply-chain walking
    msg_map = {}
    for row in rows:
        msg_map[row["message_id"]] = dict(row)

    # Classify messages
    patches = []       # (version, number, total, row_dict)
    covers = []        # cover letters (0/N)
    replies = []       # Re: messages (potential trailer sources)

    for row in rows:
        subj = row["subject"] or ""
        row_dict = dict(row)

        if re.match(r'^\s*Re:', subj, re.IGNORECASE):
            replies.append(row_dict)
            continue

        parsed = _parse_patch_subject(subj)
        if parsed:
            version, number, total = parsed
            if number == 0:
                covers.append(row_dict)
            else:
                patches.append((version, number, total, row_dict))
            continue

        # Check for [PATCH] without N/M (single patch)
        if "[PATCH" in subj.upper() and row["raw_email"]:
            # Try to extract version
            vm = re.search(r'\[PATCH\s+v(\d+)', subj, re.IGNORECASE)
            version = int(vm.group(1)) if vm else 1
            patches.append((version, 1, 1, row_dict))

    if not patches:
        raise HTTPException(404, "No patches found in thread")

    # Select latest version only
    max_version = max(p[0] for p in patches)
    patches = [(v, n, t, r) for v, n, t, r in patches if v == max_version]
    covers = [c for c in covers if _parse_patch_subject(c.get("subject", ""))
              and _parse_patch_subject(c["subject"])[0] == max_version]

    # Sort patches by number
    patches.sort(key=lambda x: x[1])

    # Collect trailers from replies
    trailers_by_mid: dict[str, list[str]] = {}
    for reply in replies:
        body = reply.get("body_text") or ""
        found = _extract_trailers(body)
        if not found:
            continue
        # Find which patch this reply is about
        target = _find_patch_ancestor(reply["message_id"], msg_map)
        if not target:
            continue
        if target not in trailers_by_mid:
            trailers_by_mid[target] = []
        for t in found:
            if t not in trailers_by_mid[target]:
                trailers_by_mid[target].append(t)

    if download:
        # Build mboxrd with trailers injected (exclude cover letters)
        mbox_patches = [(n, r) for _, n, _, r in patches if r.get("raw_email")]
        mbox_content = _build_mboxrd(mbox_patches, trailers_by_mid)

        series_subject = patches[0][3].get("subject") or "series"
        safe = _sanitize_filename(series_subject)
        return Response(
            content=mbox_content.encode("utf-8"),
            media_type="application/mbox",
            headers={"Content-Disposition": f'attachment; filename="{safe}.mbox"'},
        )

    # JSON metadata mode
    cover_info = None
    if covers:
        c = covers[0]
        cover_info = {
            "message_id": c["message_id"],
            "subject": c["subject"],
            "sender": c["sender"],
        }

    patches_info = []
    for _, number, _, row_dict in patches:
        mid = row_dict["message_id"]
        patches_info.append({
            "number": number,
            "message_id": mid,
            "subject": row_dict["subject"],
            "trailers": trailers_by_mid.get(mid, []),
        })

    total_trailers = sum(len(t) for t in trailers_by_mid.values())

    return {
        "version": max_version,
        "total": len(patches),
        "cover_letter": cover_info,
        "patches": patches_info,
        "total_trailers": total_trailers,
        "download_url": f"/api/series?id={id}&download=1",
    }


# ── Threads ──────────────────────────────────────────

@app.get("/api/threads/{message_id:path}")
def get_thread(message_id: str):
    """Get the full thread for a message."""
    conn, target_inbox, thread_ids = _find_thread_messages(message_id)

    if not thread_ids:
        conn.close()
        return {"root": message_id, "total": 0, "inbox": target_inbox, "messages": []}

    placeholders = ",".join("?" for _ in thread_ids)
    messages = conn.execute(
        f"""SELECT id, message_id, subject, sender, date, in_reply_to
        FROM messages
        WHERE message_id IN ({placeholders})
        ORDER BY date ASC""",
        list(thread_ids),
    ).fetchall()

    # Determine root (message with no in_reply_to in the set, or earliest)
    root_msg_id = message_id
    for m in messages:
        if not m["in_reply_to"] or m["in_reply_to"] not in thread_ids:
            root_msg_id = m["message_id"]
            break

    conn.close()
    return {
        "root": root_msg_id,
        "total": len(messages),
        "inbox": target_inbox,
        "messages": [row_to_dict(m) for m in messages],
    }


# ── Search ───────────────────────────────────────────


def parse_search_query(raw_query: str) -> tuple[str, list[str], list]:
    """
    Parse lore-style search prefixes into FTS5 query + SQL WHERE clauses.

    Supported prefixes (compatible with lore.kernel.org):
      s:    subject           f:    from/sender
      b:    body              t:    to header
      c:    cc header         a:    any address (from/to/cc)
      d:    date range        bs:   subject + body
      tc:   to + cc

    Date range format (d:):
      d:YYYY-MM-DD..YYYY-MM-DD   d:2026-01-01..
      d:..2026-01-31              d:2026-01-01

    Returns (fts_query, where_clauses, params).
    """
    fts_parts = []
    where_clauses = []
    params = []

    # FTS5 column mapping for lore prefixes
    FTS_PREFIX_MAP = {
        "s": "subject",
        "f": "sender",
        "b": "body_text",
        "bs": None,  # special: subject OR body
    }

    # SQL LIKE/exact search (for fields not in FTS5)
    SQL_PREFIX_MAP = {
        "m": "m.message_id",  # Message-ID exact match
        "t": "m.headers",     # search To in headers JSON
        "c": "m.headers",     # search Cc in headers JSON
        "a": None,             # special: sender + headers
        "tc": None,            # special: headers (To + Cc)
    }

    # Extract prefix:value tokens (handle quoted values)
    tokens = re.findall(r'(\w+):"([^"]+)"|(\w+):(\S+)|("(?:[^"\\]|\\.)*")|(\S+)', raw_query)

    for match in tokens:
        prefix_q, value_q, prefix_s, value_s, quoted, plain = match

        prefix = prefix_q or prefix_s
        value = value_q or value_s or quoted or plain

        if not value:
            continue

        if prefix == "d":
            # Date range: d:2026-01-01..2026-03-01 or d:2026-01-01.. or d:..2026-03-01
            if ".." in value:
                parts = value.split("..", 1)
                if parts[0]:
                    where_clauses.append("m.date >= ?")
                    params.append(parts[0])
                if parts[1]:
                    where_clauses.append("m.date <= ?")
                    params.append(parts[1] + "T23:59:59" if len(parts[1]) == 10 else parts[1])
            else:
                # Single date = that day
                where_clauses.append("m.date >= ?")
                params.append(value)
                if len(value) == 10:
                    where_clauses.append("m.date <= ?")
                    params.append(value + "T23:59:59")
        elif prefix in FTS_PREFIX_MAP:
            col = FTS_PREFIX_MAP[prefix]
            # Quote multi-token values for phrase matching
            clean = value.strip('"')
            quoted = f'"{clean}"' if not clean.isalnum() else clean
            if col:
                fts_parts.append(f"{col}:{quoted}")
            elif prefix == "bs":
                # subject OR body
                fts_parts.append(f"(subject:{quoted} OR body_text:{quoted})")
        elif prefix == "m":
            where_clauses.append("m.message_id = ?")
            params.append(value.strip("<>"))
        elif prefix == "t":
            where_clauses.append("m.headers LIKE ?")
            params.append(f"%\"To\"%{value}%")
        elif prefix == "c":
            where_clauses.append("m.headers LIKE ?")
            params.append(f"%\"Cc\"%{value}%")
        elif prefix == "a":
            where_clauses.append("(m.sender LIKE ? OR m.headers LIKE ?)")
            params.extend([f"%{value}%", f"%{value}%"])
        elif prefix == "tc":
            where_clauses.append("m.headers LIKE ?")
            params.append(f"%{value}%")
        else:
            # Unknown prefix or no prefix - treat as plain FTS query
            if prefix:
                fts_parts.append(f"{prefix}:{value}")
            else:
                fts_parts.append(value)

    fts_query = " ".join(fts_parts) if fts_parts else None
    return fts_query, where_clauses, params


@app.get("/api/search")
def search(
    q: str = Query(..., min_length=1),
    inbox: Optional[str] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
):
    """
    Full-text search with lore-compatible prefix syntax.

    Prefixes: s: (subject), f: (from), b: (body), d: (date range),
    t: (to), c: (cc), a: (any address), bs: (subject+body), tc: (to+cc)

    Date range: d:2026-01-01..2026-03-01  d:2026-01-01..  d:..2026-03-01
    """
    offset = (page - 1) * per_page

    # If query looks like a bare Message-ID (contains @, no space, no search prefix)
    q_stripped = q.strip().strip("<>")
    _KNOWN_PREFIXES = ("s:", "f:", "b:", "d:", "t:", "c:", "a:", "m:", "bs:", "tc:")
    if "@" in q_stripped and " " not in q_stripped and not q_stripped.lower().startswith(_KNOWN_PREFIXES):
        inboxes_check = [inbox] if inbox else get_available_inboxes()
        for name in inboxes_check:
            try:
                conn = get_db(name)
            except HTTPException:
                continue
            row = conn.execute(
                """SELECT id, message_id, subject, sender, date, in_reply_to
                FROM messages WHERE message_id=?""",
                (q_stripped,),
            ).fetchone()
            conn.close()
            if row:
                d = row_to_dict(row)
                d["inbox_name"] = name
                d["snippet"] = ""
                return {
                    "query": q,
                    "total": 1,
                    "page": 1,
                    "per_page": per_page,
                    "pages": 1,
                    "messages": [d],
                }

    fts_query, extra_where, extra_params = parse_search_query(q)

    inboxes_to_search = [inbox] if inbox else get_available_inboxes()

    all_results = []
    total = 0
    timed_out = False

    for name in inboxes_to_search:
        try:
            conn = get_db(name)
        except HTTPException:
            continue

        where_clauses = list(extra_where)
        params = list(extra_params)

        if fts_query:
            where_clauses.insert(0, "messages_fts MATCH ?")
            params.insert(0, fts_query)

        if not where_clauses:
            conn.close()
            continue

        where = " AND ".join(where_clauses)

        # Need FTS join only if we have a MATCH clause
        COUNT_CAP = 10001  # Cap COUNT for performance (avoids full scan)
        if fts_query:
            if extra_where:
                # FTS + SQL filters: need JOIN for WHERE clauses
                count_sql = f"""SELECT COUNT(*) FROM (
                    SELECT 1 FROM messages_fts
                    JOIN messages m ON m.id = messages_fts.rowid
                    WHERE {where} LIMIT {COUNT_CAP})"""
            else:
                # Pure FTS: skip JOIN for counting
                count_sql = f"""SELECT COUNT(*) FROM (
                    SELECT 1 FROM messages_fts
                    WHERE {where} LIMIT {COUNT_CAP})"""
            search_sql = f"""SELECT m.id, m.message_id, m.subject, m.sender, m.date,
                       m.in_reply_to,
                       snippet(messages_fts, 2, '<mark>', '</mark>', '...', 40) as snippet,
                       rank
                FROM messages_fts
                JOIN messages m ON m.id = messages_fts.rowid
                WHERE {where}
                ORDER BY rank
                LIMIT ?"""
        else:
            # Pure SQL search (e.g. d: only, no FTS)
            count_sql = f"""SELECT COUNT(*) FROM (
                SELECT 1 FROM messages m WHERE {where} LIMIT {COUNT_CAP})"""
            search_sql = f"""SELECT m.id, m.message_id, m.subject, m.sender, m.date,
                       m.in_reply_to, '' as snippet, 0 as rank
                FROM messages m
                WHERE {where}
                ORDER BY m.date DESC
                LIMIT ?"""

        try:
            # Skip SELECT if we already have enough results for this page
            need_rows = len(all_results) < offset + per_page

            count = conn.execute(count_sql, params).fetchone()[0]
            total += count

            if need_rows:
                rows = conn.execute(search_sql, params + [offset + per_page]).fetchall()
                for r in rows:
                    d = row_to_dict(r)
                    d["inbox_name"] = name
                    all_results.append(d)
        except sqlite3.OperationalError as e:
            if "interrupted" in str(e):
                timed_out = True
            # else: malformed query, skip gracefully
        except Exception:
            pass

        conn.close()

    # Sort merged results by rank (lower is better in FTS5)
    if fts_query:
        all_results.sort(key=lambda x: x.get("rank", 0))
    else:
        all_results.sort(key=lambda x: x.get("date", ""), reverse=True)

    # Paginate
    page_results = all_results[offset:offset + per_page]
    for r in page_results:
        r.pop("rank", None)

    result = {
        "query": q,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
        "messages": page_results,
    }

    if timed_out:
        result["warning"] = "Some results may be incomplete due to query timeout"

    return result


# ── Stats ────────────────────────────────────────────

@app.get("/api/stats")
def get_stats():
    """Get overall statistics (cached 5 min)."""
    cached = cache_get("stats")
    if cached is not None:
        return cached

    total_messages = 0
    total_size = 0
    latest = None

    for name in get_available_inboxes():
        try:
            conn = get_db(name)
            count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            total_messages += count

            row = conn.execute(
                """SELECT date, subject, sender FROM messages
                WHERE date <= '2027'
                ORDER BY date DESC LIMIT 1"""
            ).fetchone()
            if row and (not latest or (row["date"] and row["date"] > latest["date"])):
                latest = {"date": row["date"], "subject": row["subject"],
                          "sender": row["sender"], "inbox": name}

            conn.close()
            total_size += (DB_DIR / f"{name}.db").stat().st_size
        except Exception:
            continue

    result = {
        "total_messages": total_messages,
        "total_inboxes": len(get_available_inboxes()),
        "database_size_bytes": total_size,
        "latest_message": latest,
    }
    cache_set("stats", result)
    return result


# ── Sync ─────────────────────────────────────────────

SYNC_STATUS_DIR = PROJECT_ROOT / "sync_status"


@app.get("/api/sync/status")
def get_sync_status():
    """Get current sync status for all inboxes (read-only)."""
    if not SYNC_STATUS_DIR.exists():
        return {"running": False, "inboxes": []}

    inboxes = []
    any_running = False
    for f in sorted(SYNC_STATUS_DIR.glob("*.json")):
        try:
            status = json.loads(f.read_text())
            inboxes.append(status)
            if status.get("running"):
                any_running = True
        except (json.JSONDecodeError, OSError):
            pass

    return {"running": any_running, "inboxes": inboxes}


# ── Static files (production mode) ──────────────────

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def serve_spa(path: str):
        """Serve Vue SPA — all non-API routes return index.html."""
        if path.startswith("api/"):
            raise HTTPException(404, "Not found")
        file = FRONTEND_DIST / path
        if file.exists() and file.is_file():
            return FileResponse(file)
        return FileResponse(FRONTEND_DIST / "index.html")
