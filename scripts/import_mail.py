#!/usr/bin/env python3
"""
Import emails from public-inbox git repos into per-inbox SQLite databases.

Each inbox gets its own database file: db/{inbox_name}.db

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
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from database import init_db, get_connection
from config_utils import load_config, PROJECT_ROOT, DEFAULT_CONFIG

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# Batch size for commits between DB transactions
BATCH_SIZE = 500

# ── Graceful shutdown ────────────────────────────────
_shutdown_requested = False


def request_shutdown():
    """Request graceful shutdown. Safe to call from signal handlers."""
    global _shutdown_requested
    _shutdown_requested = True


def is_shutdown_requested() -> bool:
    return _shutdown_requested


def _signal_handler(signum, frame):
    signame = signal.Signals(signum).name
    log.info(f"Received {signame}, shutting down gracefully (finishing current batch)...")
    request_shutdown()


def get_db_path(config: dict, inbox_name: str) -> Path:
    """Get the database file path for an inbox."""
    db_dir = Path(config["database"]["dir"])
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / f"{inbox_name}.db"


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
            # Keep raw string; will be overridden by git commit date if available
            date_iso = None

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
    """Get all commit hashes in reverse chronological order (newest first)."""
    result = subprocess.run(
        ["git", "--git-dir", str(repo_path), "rev-list", "HEAD"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        log.error(f"Failed to list commits for {repo_path}: {result.stderr}")
        return []
    return [h.strip() for h in result.stdout.strip().split("\n") if h.strip()]


def fix_date(date_str: Optional[str]) -> Optional[str]:
    """Fix known date anomalies (Y2K bugs, epoch dates, etc.)."""
    if not date_str:
        return None
    year = date_str[:4]
    # Y2K: 0100=2000, 0101=2001, ..., 0104=2004
    if year.startswith('01') and len(year) == 4 and int(year) < 200:
        return str(int(year) + 1900) + date_str[4:]
    # Off by 100: 1903->2003, 1904->2004
    if year in ('1903', '1904'):
        return str(int(year) + 100) + date_str[4:]
    # Epoch/bogus dates before 1990
    if date_str < '1990':
        return None
    # Future dates beyond next year (spoofed or broken timestamp)
    from datetime import datetime
    max_year = str(datetime.now().year + 1)
    if date_str[:4] > max_year:
        return None
    return date_str


def get_commit_date(repo_path: Path, commit_hash: str) -> Optional[str]:
    """Get commit date in ISO format. Tries author date, then committer date."""
    for fmt in ["%aI", "%cI"]:
        result = subprocess.run(
            ["git", "--git-dir", str(repo_path), "log", "-1", f"--format={fmt}", commit_hash],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            date = fix_date(result.stdout.strip())
            if date:
                return date
    return None


def get_email_from_commit(repo_path: Path, commit_hash: str) -> Optional[bytes]:
    """
    Extract the raw email from a commit.
    Returns None if the commit is a deletion (contains 'd' instead of 'm').
    """
    result = subprocess.run(
        ["git", "--git-dir", str(repo_path), "show", f"{commit_hash}:m"],
        capture_output=True,
        timeout=30,
    )
    if result.returncode == 0:
        return result.stdout

    result_d = subprocess.run(
        ["git", "--git-dir", str(repo_path), "show", f"{commit_hash}:d"],
        capture_output=True,
        timeout=30,
    )
    if result_d.returncode == 0:
        return None  # deletion, skip

    log.warning(f"Commit {commit_hash} has neither 'm' nor 'd': {result.stderr.decode()[:200]}")
    return None


def get_import_progress(conn, epoch: int) -> tuple[Optional[str], int]:
    """Get the last imported commit and saved total count for an epoch."""
    row = conn.execute(
        "SELECT last_commit, commit_count FROM import_progress WHERE epoch=?",
        (epoch,),
    ).fetchone()
    if row:
        return row["last_commit"], row["commit_count"] or 0
    return None, 0


def import_epoch(conn, inbox_name: str, epoch: int, repos_dir: Path):
    """Import emails from a single epoch git repo (newest first)."""
    repo_path = repos_dir / inbox_name / "git" / f"{epoch}.git"

    if not repo_path.exists() or not (repo_path / "HEAD").exists():
        log.warning(f"Repo not found or incomplete: {repo_path}")
        return

    log.info(f"Processing {inbox_name} epoch {epoch}: {repo_path}")

    all_commits = get_commits_for_epoch(repo_path)  # newest first
    if not all_commits:
        log.info(f"  No commits found")
        return

    total_now = len(all_commits)
    last_commit, saved_total = get_import_progress(conn, epoch)

    if last_commit:
        try:
            last_idx = all_commits.index(last_commit)
        except ValueError:
            log.warning(f"  Last imported commit {last_commit} not found, starting from beginning")
            last_idx = -1

        if last_idx >= 0:
            # New commits from fetch: appear at the beginning of the list
            new_count = max(0, total_now - saved_total) if saved_total > 0 else 0
            new_part = all_commits[:new_count] if new_count > 0 else []

            # Old commits not yet processed (continuing toward older)
            old_part = all_commits[last_idx + 1:]

            remaining = new_part + old_part

            if new_count > 0 and old_part:
                log.info(f"  {new_count} new commits from fetch + {len(old_part)} remaining from initial import")
            elif new_count > 0:
                log.info(f"  {new_count} new commits from fetch")
        else:
            remaining = all_commits
    else:
        remaining = all_commits

    total = len(remaining)

    if total == 0:
        log.info(f"  Already up to date ({total_now} commits)")
        return

    log.info(f"  Importing {total} commits newest-first (of {total_now} total)")

    imported = 0
    skipped = 0
    errors = 0
    batch_start = time.time()

    interrupted = False

    for i, commit_hash in enumerate(remaining):
        # Check for graceful shutdown between commits
        if is_shutdown_requested():
            log.info(f"  Shutdown requested, saving progress at commit {i}/{total}...")
            interrupted = True
            break

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

            # Fix date: apply Y2K corrections, then fallback to git date
            msg_date = fix_date(parsed["date"])
            if not msg_date:
                msg_date = get_commit_date(repo_path, commit_hash)

            try:
                cursor = conn.execute(
                    """INSERT OR IGNORE INTO messages
                    (message_id, subject, sender, date,
                     in_reply_to, references_ids, body_text, body_html,
                     raw_email, headers, git_commit, epoch)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        parsed["message_id"],
                        parsed["subject"],
                        parsed["sender"],
                        msg_date,
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
                (epoch, last_commit, commit_count, updated_at)
                VALUES (?, ?, ?, datetime('now'))""",
                (epoch, commit_hash, total_now),
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

    # Save progress: use last processed commit (not remaining[-1] if interrupted)
    last_processed = remaining[i] if remaining else None
    if last_processed:
        conn.execute(
            """INSERT OR REPLACE INTO import_progress
            (epoch, last_commit, commit_count, updated_at)
            VALUES (?, ?, ?, datetime('now'))""",
            (epoch, last_processed, total_now),
        )
        conn.commit()

    if interrupted:
        log.info(
            f"  Interrupted: imported {imported}, skipped {skipped}, errors {errors} "
            f"({i}/{total} processed, will resume from here)"
        )
    else:
        log.info(
            f"  Done: imported {imported}, skipped {skipped}, errors {errors}"
        )

    return not interrupted


def show_stats(config: dict):
    """Display import statistics for all inboxes."""
    db_dir = Path(config["database"]["dir"])

    print(f"\n{'Inbox':<25} {'Messages':<12} {'Epochs':<10} {'Size':<10} {'Last Import'}")
    print("-" * 75)

    total_msgs = 0
    for inbox_cfg in config["inboxes"]:
        name = inbox_cfg["name"]
        db_path = db_dir / f"{name}.db"
        if not db_path.exists():
            print(f"{name:<25} {'—':<12} {'—':<10} {'—':<10} not imported")
            continue

        conn = get_connection(db_path)
        msg_count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        epoch_count = conn.execute("SELECT COUNT(DISTINCT epoch) FROM messages").fetchone()[0]
        last_update = conn.execute("SELECT MAX(updated_at) FROM import_progress").fetchone()[0] or "never"
        conn.close()

        size = db_path.stat().st_size
        size_str = f"{size / 1e9:.1f} GB" if size > 1e9 else f"{size / 1e6:.0f} MB"

        total_msgs += msg_count
        print(f"{name:<25} {msg_count:<12} {epoch_count:<10} {size_str:<10} {last_update}")

    print("-" * 75)
    print(f"{'Total':<25} {total_msgs:<12}")


def run_import(config: dict, inbox_filter: Optional[str] = None):
    """Main import logic."""
    # Import lock functions from sync module (shared per-inbox locks)
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    from sync import try_lock_inbox, unlock_inbox

    repos_dir = Path(config["mirror"]["repos_dir"])

    inboxes = config["inboxes"]
    if inbox_filter:
        inboxes = [ib for ib in inboxes if ib["name"] == inbox_filter]
        if not inboxes:
            log.error(f"Inbox '{inbox_filter}' not found in config")
            sys.exit(1)

    for inbox_cfg in inboxes:
        if is_shutdown_requested():
            break

        name = inbox_cfg["name"]

        # Acquire per-inbox lock (same lock as sync.py)
        if not try_lock_inbox(name):
            log.error(f"[{name}] Already locked by another sync/import process. Skipping.")
            continue

        try:
            inbox_repo_dir = repos_dir / name / "git"
            if not inbox_repo_dir.exists():
                log.warning(f"No repos found for '{name}' at {inbox_repo_dir}, skipping")
                continue

            db_path = get_db_path(config, name)
            conn = init_db(db_path)

            epochs = sorted(
                (int(p.name.replace(".git", ""))
                for p in inbox_repo_dir.iterdir()
                if p.name.endswith(".git") and (p / "HEAD").exists()),
                reverse=True,
            )

            log.info(f"Importing '{name}': {len(epochs)} epochs -> {db_path}")

            for epoch in epochs:
                if is_shutdown_requested():
                    break
                import_epoch(conn, name, epoch, repos_dir)

            conn.close()
        finally:
            unlock_inbox(name)

    if is_shutdown_requested():
        log.info("Import stopped gracefully (progress saved, will resume next run)")
    else:
        log.info("Import complete")


def main():
    parser = argparse.ArgumentParser(description="Import emails from git repos to SQLite")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--inbox", type=str, default=None, help="Import only this inbox")
    parser.add_argument("--stats", action="store_true", help="Show import statistics")
    args = parser.parse_args()

    config = load_config(args.config)

    if args.stats:
        show_stats(config)
    else:
        signal.signal(signal.SIGTERM, _signal_handler)
        signal.signal(signal.SIGINT, _signal_handler)
        run_import(config, inbox_filter=args.inbox)


if __name__ == "__main__":
    main()
