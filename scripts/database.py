#!/usr/bin/env python3
"""
Database schema and access layer for lore mirror (SQLite3 + FTS5).

Each inbox gets its own database file: db/{inbox_name}.db
This allows parallel imports and better per-inbox performance.
"""

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 2


def get_connection(db_path: str | Path) -> sqlite3.Connection:
    """Open a connection with recommended settings."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
    return conn


def init_db(db_path: str | Path) -> sqlite3.Connection:
    """Create tables and FTS index if they don't exist."""
    conn = get_connection(db_path)

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id TEXT UNIQUE NOT NULL,
            subject TEXT,
            sender TEXT,
            date TEXT,
            in_reply_to TEXT,
            references_ids TEXT,       -- JSON array of Message-IDs
            body_text TEXT,
            body_html TEXT,
            raw_email BLOB,
            headers TEXT,              -- JSON object
            git_commit TEXT,
            epoch INTEGER,
            UNIQUE(git_commit, epoch)
        );

        CREATE INDEX IF NOT EXISTS idx_messages_date ON messages(date);
        CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender);
        CREATE INDEX IF NOT EXISTS idx_messages_in_reply_to ON messages(in_reply_to);
        CREATE INDEX IF NOT EXISTS idx_messages_message_id ON messages(message_id);

        CREATE TABLE IF NOT EXISTS attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER NOT NULL REFERENCES messages(id),
            filename TEXT,
            content_type TEXT,
            content BLOB
        );

        CREATE INDEX IF NOT EXISTS idx_attachments_message ON attachments(message_id);

        -- Track import progress per epoch
        CREATE TABLE IF NOT EXISTS import_progress (
            epoch INTEGER PRIMARY KEY,
            last_commit TEXT NOT NULL,
            commit_count INTEGER DEFAULT 0,
            updated_at TEXT DEFAULT (datetime('now'))
        );

        -- FTS5 full-text search index
        CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
            subject,
            sender,
            body_text,
            content='messages',
            content_rowid='id',
            tokenize='unicode61'
        );

        -- Triggers to keep FTS in sync
        CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
            INSERT INTO messages_fts(rowid, subject, sender, body_text)
            VALUES (new.id, new.subject, new.sender, new.body_text);
        END;

        CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
            INSERT INTO messages_fts(messages_fts, rowid, subject, sender, body_text)
            VALUES ('delete', old.id, old.subject, old.sender, old.body_text);
        END;

        CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
            INSERT INTO messages_fts(messages_fts, rowid, subject, sender, body_text)
            VALUES ('delete', old.id, old.subject, old.sender, old.body_text);
            INSERT INTO messages_fts(rowid, subject, sender, body_text)
            VALUES (new.id, new.subject, new.sender, new.body_text);
        END;

        -- Schema version tracking
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY
        );
    """)

    # Record schema version
    existing = conn.execute("SELECT version FROM schema_version").fetchone()
    if not existing:
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
    conn.commit()

    return conn
