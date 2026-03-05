#!/usr/bin/env python3
"""
FastAPI backend for lore mirror.

Usage:
    uvicorn server.app:app --host 0.0.0.0 --port 8000 --reload
"""

import json
import sqlite3
from pathlib import Path
from typing import Optional

import yaml
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, FileResponse
from fastapi.staticfiles import StaticFiles

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.yaml"
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"

with open(CONFIG_PATH) as f:
    _config = yaml.safe_load(f)

DB_PATH = _config["database"]["path"]

app = FastAPI(title="Lore Mirror API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


# ── Inboxes ──────────────────────────────────────────

@app.get("/api/inboxes")
def list_inboxes():
    """List all inboxes with message counts."""
    conn = get_db()
    rows = conn.execute("""
        SELECT i.id, i.name, i.description,
               COUNT(m.id) as message_count,
               MIN(m.date) as earliest,
               MAX(m.date) as latest
        FROM inboxes i
        LEFT JOIN messages m ON m.inbox_id = i.id
        GROUP BY i.id
        ORDER BY i.name
    """).fetchall()
    conn.close()
    return [row_to_dict(r) for r in rows]


@app.get("/api/inboxes/{name}")
def get_inbox(
    name: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
):
    """Get messages for an inbox, newest first."""
    conn = get_db()

    inbox = conn.execute(
        "SELECT id, name, description FROM inboxes WHERE name=?", (name,)
    ).fetchone()
    if not inbox:
        conn.close()
        raise HTTPException(404, f"Inbox '{name}' not found")

    offset = (page - 1) * per_page

    total = conn.execute(
        "SELECT COUNT(*) FROM messages WHERE inbox_id=?", (inbox["id"],)
    ).fetchone()[0]

    messages = conn.execute(
        """SELECT id, message_id, subject, sender, date, in_reply_to
        FROM messages
        WHERE inbox_id=?
        ORDER BY date DESC
        LIMIT ? OFFSET ?""",
        (inbox["id"], per_page, offset),
    ).fetchall()

    conn.close()
    return {
        "inbox": row_to_dict(inbox),
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
        "messages": [row_to_dict(m) for m in messages],
    }


# ── Messages ─────────────────────────────────────────

@app.get("/api/messages/{message_id:path}")
def get_message(message_id: str):
    """Get a single message by Message-ID."""
    conn = get_db()
    msg = conn.execute(
        """SELECT m.*, i.name as inbox_name
        FROM messages m
        JOIN inboxes i ON i.id = m.inbox_id
        WHERE m.message_id=?""",
        (message_id,),
    ).fetchone()

    if not msg:
        conn.close()
        raise HTTPException(404, f"Message not found")

    result = row_to_dict(msg)
    # Don't send raw_email in JSON response (too large)
    result.pop("raw_email", None)
    # Parse headers and references from JSON strings
    if result.get("headers"):
        result["headers"] = json.loads(result["headers"])
    if result.get("references_ids"):
        result["references_ids"] = json.loads(result["references_ids"])

    # Get attachments metadata (without content)
    attachments = conn.execute(
        """SELECT id, filename, content_type, LENGTH(content) as size
        FROM attachments WHERE message_id=?""",
        (msg["id"],),
    ).fetchall()
    result["attachments"] = [row_to_dict(a) for a in attachments]

    conn.close()
    return result


@app.get("/api/raw")
def get_message_raw(id: str = Query(..., alias="id")):
    """Get raw email content. Usage: /api/raw?id=<message_id>"""
    conn = get_db()
    row = conn.execute(
        "SELECT raw_email FROM messages WHERE message_id=?", (id,)
    ).fetchone()
    conn.close()

    if not row or not row["raw_email"]:
        raise HTTPException(404, "Message not found")

    return Response(content=row["raw_email"], media_type="message/rfc822")


# ── Threads ──────────────────────────────────────────

@app.get("/api/threads/{message_id:path}")
def get_thread(message_id: str):
    """
    Get the full thread for a message.
    Finds the thread root, then all descendants.
    """
    conn = get_db()

    # Find the starting message
    start = conn.execute(
        "SELECT id, message_id, in_reply_to, references_ids FROM messages WHERE message_id=?",
        (message_id,),
    ).fetchone()

    if not start:
        conn.close()
        raise HTTPException(404, "Message not found")

    # Walk up to find the root
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
            # Parent not in DB, current root is the best we have
            root_msg_id = current_reply_to
            break

    # Now get all messages in this thread (root + all descendants)
    # We do a breadth-first traversal via in_reply_to
    thread_ids = set()
    queue = [root_msg_id]

    while queue:
        current = queue.pop(0)
        if current in thread_ids:
            continue
        thread_ids.add(current)

        # Find all direct replies
        replies = conn.execute(
            "SELECT message_id FROM messages WHERE in_reply_to=?",
            (current,),
        ).fetchall()
        for r in replies:
            if r["message_id"] not in thread_ids:
                queue.append(r["message_id"])

    # Fetch full details for all thread messages
    if not thread_ids:
        conn.close()
        return {"root": root_msg_id, "messages": []}

    placeholders = ",".join("?" for _ in thread_ids)
    messages = conn.execute(
        f"""SELECT id, message_id, subject, sender, date, in_reply_to
        FROM messages
        WHERE message_id IN ({placeholders})
        ORDER BY date ASC""",
        list(thread_ids),
    ).fetchall()

    conn.close()
    return {
        "root": root_msg_id,
        "total": len(messages),
        "messages": [row_to_dict(m) for m in messages],
    }


# ── Search ───────────────────────────────────────────

@app.get("/api/search")
def search(
    q: str = Query(..., min_length=1),
    inbox: Optional[str] = None,
    sender: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
):
    """Full-text search across messages."""
    conn = get_db()
    offset = (page - 1) * per_page

    # Build query parts
    where_clauses = ["messages_fts MATCH ?"]
    params: list = [q]

    if inbox:
        where_clauses.append("i.name = ?")
        params.append(inbox)
    if sender:
        where_clauses.append("m.sender LIKE ?")
        params.append(f"%{sender}%")
    if date_from:
        where_clauses.append("m.date >= ?")
        params.append(date_from)
    if date_to:
        where_clauses.append("m.date <= ?")
        params.append(date_to)

    where = " AND ".join(where_clauses)

    # Count total
    count_sql = f"""
        SELECT COUNT(*)
        FROM messages_fts
        JOIN messages m ON m.id = messages_fts.rowid
        JOIN inboxes i ON i.id = m.inbox_id
        WHERE {where}
    """
    total = conn.execute(count_sql, params).fetchone()[0]

    # Fetch page
    search_sql = f"""
        SELECT m.id, m.message_id, m.subject, m.sender, m.date,
               m.in_reply_to, i.name as inbox_name,
               snippet(messages_fts, 2, '<mark>', '</mark>', '...', 40) as snippet
        FROM messages_fts
        JOIN messages m ON m.id = messages_fts.rowid
        JOIN inboxes i ON i.id = m.inbox_id
        WHERE {where}
        ORDER BY rank
        LIMIT ? OFFSET ?
    """
    params.extend([per_page, offset])
    messages = conn.execute(search_sql, params).fetchall()

    conn.close()
    return {
        "query": q,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
        "messages": [row_to_dict(m) for m in messages],
    }


# ── Stats ────────────────────────────────────────────

@app.get("/api/stats")
def get_stats():
    """Get overall statistics."""
    conn = get_db()

    total_messages = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    total_inboxes = conn.execute("SELECT COUNT(*) FROM inboxes").fetchone()[0]

    db_size = Path(DB_PATH).stat().st_size

    latest = conn.execute(
        "SELECT date, subject, sender FROM messages ORDER BY date DESC LIMIT 1"
    ).fetchone()

    conn.close()
    return {
        "total_messages": total_messages,
        "total_inboxes": total_inboxes,
        "database_size_bytes": db_size,
        "latest_message": row_to_dict(latest) if latest else None,
    }


# ── Static files (production mode) ──────────────────

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def serve_spa(path: str):
        """Serve Vue SPA — all non-API routes return index.html."""
        file = FRONTEND_DIST / path
        if file.exists() and file.is_file():
            return FileResponse(file)
        return FileResponse(FRONTEND_DIST / "index.html")
