#!/usr/bin/env python3
"""
FastAPI backend for lore mirror.

Each inbox has its own SQLite database in the db/ directory.

Usage:
    uvicorn server.app:app --host 0.0.0.0 --port 8000 --reload
"""

import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Optional

import yaml
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, FileResponse
from fastapi.staticfiles import StaticFiles

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.yaml"
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"

with open(CONFIG_PATH) as f:
    _config = yaml.safe_load(f)

DB_DIR = Path(_config["database"]["dir"])
INBOXES_CONFIG = {ib["name"]: ib.get("description", "") for ib in _config["inboxes"]}

app = FastAPI(title="Lore Mirror API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db(inbox_name: str) -> sqlite3.Connection:
    """Open a connection to an inbox's database."""
    db_path = DB_DIR / f"{inbox_name}.db"
    if not db_path.exists():
        raise HTTPException(404, f"Inbox '{inbox_name}' not found")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
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
    """List all inboxes with message counts."""
    results = []
    for name in get_available_inboxes():
        try:
            conn = get_db(name)
            row = conn.execute("""
                SELECT COUNT(*) as message_count,
                       MIN(date) as earliest,
                       MAX(date) as latest
                FROM messages
            """).fetchone()
            conn.close()
            results.append({
                "name": name,
                "description": INBOXES_CONFIG.get(name, ""),
                "message_count": row["message_count"],
                "earliest": row["earliest"],
                "latest": row["latest"],
            })
        except Exception:
            results.append({
                "name": name,
                "description": INBOXES_CONFIG.get(name, ""),
                "message_count": 0,
                "earliest": None,
                "latest": None,
            })
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
):
    """Get messages for an inbox, newest first."""
    conn = get_db(name)
    offset = (page - 1) * per_page

    total = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]

    messages = conn.execute(
        """SELECT id, message_id, subject, sender, date, in_reply_to
        FROM messages
        ORDER BY date DESC
        LIMIT ? OFFSET ?""",
        (per_page, offset),
    ).fetchall()

    conn.close()
    return {
        "inbox": {"name": name, "description": INBOXES_CONFIG.get(name, "")},
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
        "messages": [row_to_dict(m) for m in messages],
    }


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
def get_message_raw(id: str = Query(..., alias="id")):
    """Get raw email content. Searches all inbox databases."""
    for name in get_available_inboxes():
        try:
            conn = get_db(name)
        except HTTPException:
            continue

        row = conn.execute(
            "SELECT raw_email FROM messages WHERE message_id=?", (id,)
        ).fetchone()
        conn.close()

        if row and row["raw_email"]:
            return Response(content=row["raw_email"], media_type="message/rfc822")

    raise HTTPException(404, "Message not found")


# ── Threads ──────────────────────────────────────────

@app.get("/api/threads/{message_id:path}")
def get_thread(message_id: str):
    """Get the full thread for a message."""
    # Find which inbox has this message
    target_conn = None
    target_inbox = None

    for name in get_available_inboxes():
        try:
            conn = get_db(name)
        except HTTPException:
            continue

        row = conn.execute(
            "SELECT message_id FROM messages WHERE message_id=?",
            (message_id,),
        ).fetchone()

        if row:
            target_conn = conn
            target_inbox = name
            break
        conn.close()

    if not target_conn:
        raise HTTPException(404, "Message not found")

    conn = target_conn

    # Find the starting message
    start = conn.execute(
        "SELECT id, message_id, in_reply_to FROM messages WHERE message_id=?",
        (message_id,),
    ).fetchone()

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
            root_msg_id = current_reply_to
            break

    # BFS to find all thread messages
    thread_ids = set()
    queue = [root_msg_id]

    while queue:
        current = queue.pop(0)
        if current in thread_ids:
            continue
        thread_ids.add(current)

        replies = conn.execute(
            "SELECT message_id FROM messages WHERE in_reply_to=?",
            (current,),
        ).fetchall()
        for r in replies:
            if r["message_id"] not in thread_ids:
                queue.append(r["message_id"])

    if not thread_ids:
        conn.close()
        return {"root": root_msg_id, "total": 0, "inbox": target_inbox, "messages": []}

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
        "inbox": target_inbox,
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
    """Full-text search. If inbox is specified, search only that inbox.
    Otherwise search all inboxes."""
    offset = (page - 1) * per_page

    inboxes_to_search = [inbox] if inbox else get_available_inboxes()

    all_results = []
    total = 0

    for name in inboxes_to_search:
        try:
            conn = get_db(name)
        except HTTPException:
            continue

        where_clauses = ["messages_fts MATCH ?"]
        params: list = [q]

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

        count = conn.execute(
            f"""SELECT COUNT(*) FROM messages_fts
            JOIN messages m ON m.id = messages_fts.rowid
            WHERE {where}""",
            params,
        ).fetchone()[0]
        total += count

        rows = conn.execute(
            f"""SELECT m.id, m.message_id, m.subject, m.sender, m.date,
                   m.in_reply_to,
                   snippet(messages_fts, 2, '<mark>', '</mark>', '...', 40) as snippet,
                   rank
            FROM messages_fts
            JOIN messages m ON m.id = messages_fts.rowid
            WHERE {where}
            ORDER BY rank
            LIMIT ?""",
            params + [offset + per_page],  # fetch enough to merge
        ).fetchall()

        for r in rows:
            d = row_to_dict(r)
            d["inbox_name"] = name
            all_results.append(d)

        conn.close()

    # Sort merged results by rank (lower is better in FTS5)
    all_results.sort(key=lambda x: x.get("rank", 0))

    # Paginate
    page_results = all_results[offset:offset + per_page]
    # Remove rank from output
    for r in page_results:
        r.pop("rank", None)

    return {
        "query": q,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
        "messages": page_results,
    }


# ── Stats ────────────────────────────────────────────

@app.get("/api/stats")
def get_stats():
    """Get overall statistics."""
    total_messages = 0
    total_size = 0
    latest = None

    for name in get_available_inboxes():
        try:
            conn = get_db(name)
            count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            total_messages += count

            row = conn.execute(
                "SELECT date, subject, sender FROM messages ORDER BY date DESC LIMIT 1"
            ).fetchone()
            if row and (not latest or (row["date"] and row["date"] > latest["date"])):
                latest = {"date": row["date"], "subject": row["subject"],
                          "sender": row["sender"], "inbox": name}

            conn.close()
            total_size += (DB_DIR / f"{name}.db").stat().st_size
        except Exception:
            continue

    return {
        "total_messages": total_messages,
        "total_inboxes": len(get_available_inboxes()),
        "database_size_bytes": total_size,
        "latest_message": latest,
    }


# ── Sync ─────────────────────────────────────────────

SYNC_STATUS_FILE = PROJECT_ROOT / "sync_status.json"


def _run_sync_background(inbox: Optional[str] = None):
    """Run sync script as subprocess."""
    cmd = [sys.executable, str(PROJECT_ROOT / "scripts" / "sync.py")]
    if inbox:
        cmd.extend(["--inbox", inbox])
    subprocess.Popen(cmd, cwd=str(PROJECT_ROOT))


@app.post("/api/sync")
def trigger_sync(
    background_tasks: BackgroundTasks,
    inbox: Optional[str] = None,
):
    """Trigger a sync (git fetch + import). Runs in background."""
    # Check if already running
    if SYNC_STATUS_FILE.exists():
        status = json.loads(SYNC_STATUS_FILE.read_text())
        if status.get("running"):
            raise HTTPException(409, "Sync already in progress")

    background_tasks.add_task(_run_sync_background, inbox)
    return {"message": "Sync started", "inbox": inbox or "all"}


@app.get("/api/sync/status")
def get_sync_status():
    """Get current sync status."""
    if SYNC_STATUS_FILE.exists():
        return json.loads(SYNC_STATUS_FILE.read_text())
    return {"running": False}


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
