#!/usr/bin/env python3
"""
Sync script: git fetch + incremental import for all configured inboxes.

Usage:
    python3 scripts/sync.py                # sync all inboxes
    python3 scripts/sync.py --inbox lkml   # sync specific inbox
    python3 scripts/sync.py --status       # show sync status
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from config_utils import load_config, PROJECT_ROOT, DEFAULT_CONFIG

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# Shared status file for web UI to read progress
STATUS_FILE = PROJECT_ROOT / "sync_status.json"


def write_status(status: dict):
    """Write sync status to JSON file for the web UI."""
    STATUS_FILE.write_text(json.dumps(status, default=str))


def read_status() -> dict:
    if STATUS_FILE.exists():
        return json.loads(STATUS_FILE.read_text())
    return {"running": False}


def git_fetch_epoch(repo_path: Path, timeout: int = 3600) -> tuple[bool, int]:
    """
    Fetch updates for an epoch repo.
    Returns (success, new_commit_count).
    """
    # Get commit count before fetch
    before = subprocess.run(
        ["git", "--git-dir", str(repo_path), "rev-list", "--count", "HEAD"],
        capture_output=True, text=True, timeout=30,
    )
    count_before = int(before.stdout.strip()) if before.returncode == 0 else 0

    # Fetch
    result = subprocess.run(
        ["git", "--git-dir", str(repo_path), "fetch", "--prune"],
        capture_output=True, text=True, timeout=timeout,
    )
    if result.returncode != 0:
        log.error(f"  Fetch failed for {repo_path}: {result.stderr.strip()}")
        return False, 0

    # Get commit count after fetch
    after = subprocess.run(
        ["git", "--git-dir", str(repo_path), "rev-list", "--count", "HEAD"],
        capture_output=True, text=True, timeout=30,
    )
    count_after = int(after.stdout.strip()) if after.returncode == 0 else 0

    new_commits = count_after - count_before
    return True, new_commits


def sync_inbox(config: dict, inbox_name: str) -> dict:
    """
    Sync a single inbox: git fetch all epochs, then import new emails.
    Returns a summary dict.
    """
    repos_dir = Path(config["mirror"]["repos_dir"])
    db_dir = Path(config["database"]["dir"])
    inbox_repo_dir = repos_dir / inbox_name / "git"

    summary = {
        "inbox": inbox_name,
        "epochs_fetched": 0,
        "new_commits": 0,
        "messages_imported": 0,
        "errors": [],
    }

    if not inbox_repo_dir.exists():
        summary["errors"].append(f"No repos found at {inbox_repo_dir}")
        return summary

    # Step 1: git fetch all epochs
    epoch_dirs = sorted(
        p for p in inbox_repo_dir.iterdir()
        if p.name.endswith(".git") and (p / "HEAD").exists()
    )

    log.info(f"[{inbox_name}] Fetching {len(epoch_dirs)} epochs...")

    total_new = 0
    epochs_with_updates = []
    for repo_path in epoch_dirs:
        epoch = repo_path.name.replace(".git", "")
        success, new_commits = git_fetch_epoch(repo_path)
        if success:
            summary["epochs_fetched"] += 1
            total_new += new_commits
            if new_commits > 0:
                epochs_with_updates.append(int(epoch))
                log.info(f"  Epoch {epoch}: {new_commits} new commits")
        else:
            summary["errors"].append(f"Fetch failed for epoch {epoch}")

    summary["new_commits"] = total_new
    log.info(f"[{inbox_name}] Fetch complete: {total_new} new commits across {summary['epochs_fetched']} epochs")

    if total_new == 0:
        log.info(f"[{inbox_name}] Already up to date, skipping import")
        return summary

    # Step 2: incremental import — only epochs that had new commits
    log.info(f"[{inbox_name}] Importing new emails from {len(epochs_with_updates)} updated epoch(s): {epochs_with_updates}")

    # Import using import_mail module
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    from database import init_db
    from import_mail import import_epoch as do_import_epoch

    db_path = db_dir / f"{inbox_name}.db"
    db_dir.mkdir(parents=True, exist_ok=True)
    conn = init_db(db_path)

    for epoch in sorted(epochs_with_updates):
        do_import_epoch(conn, inbox_name, epoch, repos_dir)

    # Count imported messages
    count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    summary["messages_imported"] = count
    conn.close()

    log.info(f"[{inbox_name}] Import complete: {count} total messages in DB")
    return summary


def run_sync(config: dict, inbox_filter: Optional[str] = None):
    """Run sync for all configured inboxes."""
    inboxes = config["inboxes"]
    if inbox_filter:
        inboxes = [ib for ib in inboxes if ib["name"] == inbox_filter]
        if not inboxes:
            log.error(f"Inbox '{inbox_filter}' not found in config")
            sys.exit(1)

    status = {
        "running": True,
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "current_inbox": None,
        "completed": [],
        "total_inboxes": len(inboxes),
    }
    write_status(status)

    summaries = []
    for inbox_cfg in inboxes:
        name = inbox_cfg["name"]
        status["current_inbox"] = name
        write_status(status)

        try:
            summary = sync_inbox(config, name)
            summaries.append(summary)
            status["completed"].append(name)
        except Exception as e:
            log.error(f"[{name}] Sync failed: {e}")
            summaries.append({"inbox": name, "errors": [str(e)]})
            status["completed"].append(name)

    status["running"] = False
    status["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    status["current_inbox"] = None
    status["summaries"] = summaries
    write_status(status)

    # Print summary
    log.info("=" * 60)
    log.info("Sync complete:")
    for s in summaries:
        errors = f", {len(s.get('errors', []))} errors" if s.get("errors") else ""
        log.info(
            f"  {s['inbox']}: {s.get('new_commits', 0)} new commits, "
            f"{s.get('messages_imported', 0)} total messages{errors}"
        )


def show_status():
    status = read_status()
    if status.get("running"):
        print(f"Sync in progress (started {status.get('started_at', '?')})")
        print(f"  Current: {status.get('current_inbox', '?')}")
        print(f"  Completed: {', '.join(status.get('completed', []))}")
    elif status.get("finished_at"):
        print(f"Last sync: {status['finished_at']}")
        for s in status.get("summaries", []):
            errors = f", errors: {s['errors']}" if s.get("errors") else ""
            print(f"  {s['inbox']}: {s.get('new_commits', 0)} new commits{errors}")
    else:
        print("No sync has been run yet.")


def main():
    parser = argparse.ArgumentParser(description="Sync lore mirror (fetch + import)")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--inbox", type=str, default=None)
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()

    if args.status:
        show_status()
        return

    config = load_config(args.config)

    # Prevent concurrent syncs — with stale lock detection
    status = read_status()
    if status.get("running"):
        # Check if the sync process is actually alive via a PID file
        pid_file = PROJECT_ROOT / "sync.pid"
        stale = True
        if pid_file.exists():
            try:
                old_pid = int(pid_file.read_text().strip())
                # Check if process still exists
                import os
                os.kill(old_pid, 0)
                stale = False  # Process is alive
            except (ValueError, ProcessLookupError, PermissionError):
                stale = True  # PID invalid or process gone

        if not stale:
            log.error("A sync is already running. Use --status to check progress.")
            sys.exit(1)
        else:
            log.warning("Stale sync lock detected (previous sync was interrupted). Resetting...")
            status["running"] = False
            write_status(status)

    # Write PID file for stale lock detection
    pid_file = PROJECT_ROOT / "sync.pid"
    pid_file.write_text(str(os.getpid()))

    try:
        run_sync(config, inbox_filter=args.inbox)
    except KeyboardInterrupt:
        log.info("Sync interrupted")
        s = read_status()
        s["running"] = False
        s["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        write_status(s)
    finally:
        pid_file.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
