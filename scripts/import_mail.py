#!/usr/bin/env python3
"""
Import emails from public-inbox git repos into SQLite database.

In public-inbox git repos, each commit contains a file 'm' (the raw email)
or 'd' (deletion marker). We iterate through commits, extract 'm', and
parse it with Python's email library.

Usage:
    python3 scripts/import_mail.py                # import all configured inboxes
    python3 scripts/import_mail.py --inbox lkml   # import specific inbox only
    python3 scripts/import_mail.py --stats        # show import statistics
"""

import argparse
import email
import email.policy
import email.utils
import json
import logging
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

from database import init_db, get_connection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "config.yaml"

# Batch size for commits between DB transactions
BATCH_SIZE = 500


def load_config(config_path: Path) -> dict:
    with open(config_path) as f:
        return yaml.safe_load(f)


def parse_email_bytes(raw: bytes) -> dict:
    """Parse raw email bytes into a structured dict."""
    msg = email.message_from_bytes(raw, policy=email.policy.default)

    # Extract basic headers
    message_id = msg.get("Message-ID", "").strip("<>").strip()
    subject = msg.get("Subject", "")
    sender = msg.get("From", "")
    date_str = msg.get("Date", "")
    in_reply_to = msg.get("In-Reply-To", "").strip("<>").strip()
    references_raw = msg.get("References", "")

    # Parse references into list of message IDs
    references = []
    if references_raw:
        references = [
            r.strip("<>").strip()
            for r in references_raw.split()
            if r.strip("<>").strip()
        ]

    # Parse date to ISO format
    date_iso = None
    if date_str:
        try:
            parsed = email.utils.parsedate_to_datetime(date_str)
            date_iso = parsed.isoformat()
        except (ValueError, TypeError):
            date_iso = date_str  # keep original if unparseable

    # Extract body
    body_text = ""
    body_html = ""
    attachments = []

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition", ""))

            if "attachment" in disposition:
                attachments.append({
                    "filename": part.get_filename() or "",
                    "content_type": content_type,
                    "content": part.get_payload(decode=True) or b"",
                })
            elif content_type == "text/plain" and not body_text:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    body_text = payload.decode(charset, errors="replace")
            elif content_type == "text/html" and not body_html:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    body_html = payload.decode(charset, errors="replace")
    else:
        content_type = msg.get_content_type()
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            decoded = payload.decode(charset, errors="replace")
            if content_type == "text/html":
                body_html = decoded
            else:
                body_text = decoded

    # Collect all headers as dict
    headers = {}
    for key in msg.keys():
        vals = msg.get_all(key)
        headers[key] = vals if len(vals) > 1 else vals[0]

    return {
        "message_id": message_id,
        "subject": subject,
        "sender": sender,
        "date": date_iso,
        "in_reply_to": in_reply_to,
        "references_ids": json.dumps(references),
        "body_text": body_text,
        "body_html": body_html,
        "headers": json.dumps(headers, ensure_ascii=False, default=str),
        "attachments": attachments,
        "raw_email": raw,
    }


def get_commits_for_epoch(repo_path: Path) -> list[str]:
    """Get all commit hashes in chronological order (oldest first)."""
    result = subprocess.run(
        ["git", "--git-dir", str(repo_path), "rev-list", "--reverse", "HEAD"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        log.error(f"Failed to list commits for {repo_path}: {result.stderr}")
        return []
    return [h.strip() for h in result.stdout.strip().split("\n") if h.strip()]


def get_email_from_commit(repo_path: Path, commit_hash: str) -> Optional[bytes]:
    """
    Extract the raw email from a commit.
    Returns None if the commit is a deletion (contains 'd' instead of 'm').
    """
    # Check if 'm' file exists in this commit
    result = subprocess.run(
        ["git", "--git-dir", str(repo_path), "show", f"{commit_hash}:m"],
        capture_output=True,
        timeout=30,
    )
    if result.returncode == 0:
        return result.stdout

    # Check for 'd' (deletion marker) — this is expected, not an error
    result_d = subprocess.run(
        ["git", "--git-dir", str(repo_path), "show", f"{commit_hash}:d"],
        capture_output=True,
        timeout=30,
    )
    if result_d.returncode == 0:
        return None  # deletion, skip

    log.warning(f"Commit {commit_hash} has neither 'm' nor 'd': {result.stderr.decode()[:200]}")
    return None


def get_last_imported_commit(conn, inbox_id: int, epoch: int) -> Optional[str]:
    """Get the last imported commit hash for an inbox/epoch."""
    row = conn.execute(
        "SELECT last_commit FROM import_progress WHERE inbox_id=? AND epoch=?",
        (inbox_id, epoch),
    ).fetchone()
    return row["last_commit"] if row else None


def import_epoch(conn, inbox_id: int, inbox_name: str, epoch: int, repos_dir: Path):
    """Import emails from a single epoch git repo."""
    repo_path = repos_dir / inbox_name / "git" / f"{epoch}.git"

    if not repo_path.exists() or not (repo_path / "HEAD").exists():
        log.warning(f"Repo not found or incomplete: {repo_path}")
        return

    log.info(f"Processing {inbox_name} epoch {epoch}: {repo_path}")

    # Get all commits
    all_commits = get_commits_for_epoch(repo_path)
    if not all_commits:
        log.info(f"  No commits found")
        return

    # Find where we left off
    last_commit = get_last_imported_commit(conn, inbox_id, epoch)
    if last_commit:
        try:
            start_idx = all_commits.index(last_commit) + 1
        except ValueError:
            log.warning(f"  Last imported commit {last_commit} not found, starting from beginning")
            start_idx = 0
    else:
        start_idx = 0

    remaining = all_commits[start_idx:]
    total = len(remaining)

    if total == 0:
        log.info(f"  Already up to date ({len(all_commits)} commits)")
        return

    log.info(f"  Importing {total} new commits (of {len(all_commits)} total, starting from #{start_idx})")

    imported = 0
    skipped = 0
    errors = 0
    batch_start = time.time()

    for i, commit_hash in enumerate(remaining):
        try:
            raw = get_email_from_commit(repo_path, commit_hash)
            if raw is None:
                skipped += 1
                continue

            parsed = parse_email_bytes(raw)

            if not parsed["message_id"]:
                log.warning(f"  Commit {commit_hash}: no Message-ID, skipping")
                skipped += 1
                continue

            # Insert message (ignore duplicates by message_id)
            try:
                cursor = conn.execute(
                    """INSERT OR IGNORE INTO messages
                    (inbox_id, message_id, subject, sender, date,
                     in_reply_to, references_ids, body_text, body_html,
                     raw_email, headers, git_commit, epoch)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        inbox_id,
                        parsed["message_id"],
                        parsed["subject"],
                        parsed["sender"],
                        parsed["date"],
                        parsed["in_reply_to"],
                        parsed["references_ids"],
                        parsed["body_text"],
                        parsed["body_html"],
                        parsed["raw_email"],
                        parsed["headers"],
                        commit_hash,
                        epoch,
                    ),
                )

                # Insert attachments if the message was actually inserted
                if cursor.lastrowid and parsed["attachments"]:
                    msg_id = cursor.lastrowid
                    for att in parsed["attachments"]:
                        conn.execute(
                            """INSERT INTO attachments
                            (message_id, filename, content_type, content)
                            VALUES (?, ?, ?, ?)""",
                            (msg_id, att["filename"], att["content_type"], att["content"]),
                        )

                imported += 1

            except Exception as e:
                log.warning(f"  Commit {commit_hash}: insert error: {e}")
                errors += 1

        except Exception as e:
            log.warning(f"  Commit {commit_hash}: parse error: {e}")
            errors += 1

        # Commit in batches
        if (i + 1) % BATCH_SIZE == 0:
            conn.execute(
                """INSERT OR REPLACE INTO import_progress
                (inbox_id, epoch, last_commit, commit_count, updated_at)
                VALUES (?, ?, ?, ?, datetime('now'))""",
                (inbox_id, epoch, commit_hash, start_idx + i + 1),
            )
            conn.commit()

            elapsed = time.time() - batch_start
            rate = BATCH_SIZE / elapsed if elapsed > 0 else 0
            log.info(
                f"  Progress: {i+1}/{total} "
                f"(imported: {imported}, skipped: {skipped}, errors: {errors}) "
                f"[{rate:.0f} commits/s]"
            )
            batch_start = time.time()

    # Final commit
    if remaining:
        conn.execute(
            """INSERT OR REPLACE INTO import_progress
            (inbox_id, epoch, last_commit, commit_count, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'))""",
            (inbox_id, epoch, remaining[-1], start_idx + len(remaining)),
        )
        conn.commit()

    log.info(
        f"  Done: imported {imported}, skipped {skipped}, errors {errors}"
    )


def get_or_create_inbox(conn, name: str, description: str = "") -> int:
    """Get inbox ID, creating it if needed."""
    row = conn.execute("SELECT id FROM inboxes WHERE name=?", (name,)).fetchone()
    if row:
        return row["id"]
    cursor = conn.execute(
        "INSERT INTO inboxes (name, description) VALUES (?, ?)",
        (name, description),
    )
    conn.commit()
    return cursor.lastrowid


def show_stats(conn):
    """Display import statistics."""
    print(f"\n{'Inbox':<25} {'Messages':<12} {'Epochs':<10} {'Last Import'}")
    print("-" * 70)

    rows = conn.execute("""
        SELECT i.name, COUNT(m.id) as msg_count,
               COUNT(DISTINCT m.epoch) as epoch_count,
               MAX(p.updated_at) as last_update
        FROM inboxes i
        LEFT JOIN messages m ON m.inbox_id = i.id
        LEFT JOIN import_progress p ON p.inbox_id = i.id
        GROUP BY i.id
        ORDER BY i.name
    """).fetchall()

    total = 0
    for row in rows:
        total += row["msg_count"]
        last = row["last_update"] or "never"
        print(f"{row['name']:<25} {row['msg_count']:<12} {row['epoch_count']:<10} {last}")

    print("-" * 70)
    print(f"{'Total':<25} {total:<12}")

    # DB file size
    db_path = conn.execute("PRAGMA database_list").fetchone()[2]
    if db_path:
        size = Path(db_path).stat().st_size
        if size > 1_000_000_000:
            print(f"\nDatabase size: {size / 1_000_000_000:.1f} GB")
        else:
            print(f"\nDatabase size: {size / 1_000_000:.1f} MB")


def run_import(config: dict, inbox_filter: Optional[str] = None):
    """Main import logic."""
    db_path = config["database"]["path"]
    repos_dir = Path(config["mirror"]["repos_dir"])

    conn = init_db(db_path)

    inboxes = config["inboxes"]
    if inbox_filter:
        inboxes = [ib for ib in inboxes if ib["name"] == inbox_filter]
        if not inboxes:
            log.error(f"Inbox '{inbox_filter}' not found in config")
            sys.exit(1)

    for inbox_cfg in inboxes:
        name = inbox_cfg["name"]
        desc = inbox_cfg.get("description", "")
        inbox_id = get_or_create_inbox(conn, name, desc)

        inbox_repo_dir = repos_dir / name / "git"
        if not inbox_repo_dir.exists():
            log.warning(f"No repos found for '{name}' at {inbox_repo_dir}, skipping")
            continue

        # Find all epoch repos
        epochs = sorted(
            int(p.name.replace(".git", ""))
            for p in inbox_repo_dir.iterdir()
            if p.name.endswith(".git") and (p / "HEAD").exists()
        )

        log.info(f"Importing '{name}': {len(epochs)} epochs")

        for epoch in epochs:
            import_epoch(conn, inbox_id, name, epoch, repos_dir)

    conn.close()
    log.info("Import complete")


def main():
    parser = argparse.ArgumentParser(description="Import emails from git repos to SQLite")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--inbox", type=str, default=None, help="Import only this inbox")
    parser.add_argument("--stats", action="store_true", help="Show import statistics")
    args = parser.parse_args()

    config = load_config(args.config)

    if args.stats:
        db_path = config["database"]["path"]
        if not Path(db_path).exists():
            print("Database not found. Run import first.")
            sys.exit(1)
        conn = get_connection(db_path)
        show_stats(conn)
        conn.close()
    else:
        run_import(config, inbox_filter=args.inbox)


if __name__ == "__main__":
    main()
