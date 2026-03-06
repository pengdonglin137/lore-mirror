#!/usr/bin/env python3
"""
Sync script: git fetch + incremental import for all configured inboxes.

Usage:
    python3 scripts/sync.py                # sync all inboxes
    python3 scripts/sync.py --inbox lkml   # sync specific inbox
    python3 scripts/sync.py --status       # show sync status
"""

import argparse
import fcntl
import json
import logging
import os
import signal
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

# Per-inbox status directory for web UI to read progress
STATUS_DIR = PROJECT_ROOT / "sync_status"


def _status_file(inbox_name: str) -> Path:
    return STATUS_DIR / f"{inbox_name}.json"


def _lock_file(inbox_name: str) -> Path:
    return STATUS_DIR / f"{inbox_name}.lock"


# Hold open lock file descriptors so flock stays held for process lifetime
_lock_fds: dict[str, int] = {}


def write_status(inbox_name: str, status: dict):
    """Write per-inbox sync status."""
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    _status_file(inbox_name).write_text(json.dumps(status, default=str))


def read_status(inbox_name: str) -> dict:
    f = _status_file(inbox_name)
    if f.exists():
        try:
            return json.loads(f.read_text())
        except (json.JSONDecodeError, OSError):
            return {"running": False}
    return {"running": False}


def read_all_status() -> list[dict]:
    """Read status for all inboxes."""
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    for f in sorted(STATUS_DIR.glob("*.json")):
        try:
            results.append(json.loads(f.read_text()))
        except (json.JSONDecodeError, OSError):
            pass
    return results


def try_lock_inbox(inbox_name: str) -> bool:
    """
    Try to acquire an exclusive lock for an inbox (atomic, no race condition).
    Returns True if lock acquired, False if another process holds it.
    Uses fcntl.flock — lock is automatically released when process exits/crashes.
    """
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = _lock_file(inbox_name)
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Write PID for diagnostics (not used for locking)
        os.ftruncate(fd, 0)
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, str(os.getpid()).encode())
        _lock_fds[inbox_name] = fd
        return True
    except OSError:
        # LOCK_NB causes OSError if already locked
        os.close(fd)
        return False


def unlock_inbox(inbox_name: str):
    """Release the inbox lock."""
    fd = _lock_fds.pop(inbox_name, None)
    if fd is not None:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        except OSError:
            pass
    _lock_file(inbox_name).unlink(missing_ok=True)


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

    from import_mail import is_shutdown_requested

    total_new = 0
    epochs_with_updates = []
    for repo_path in epoch_dirs:
        if is_shutdown_requested():
            log.info(f"[{inbox_name}] Shutdown requested, stopping fetch")
            break
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

    for epoch in sorted(epochs_with_updates, reverse=True):
        if is_shutdown_requested():
            log.info(f"[{inbox_name}] Shutdown requested, stopping import")
            break
        do_import_epoch(conn, inbox_name, epoch, repos_dir)

    # Count imported messages
    count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    summary["messages_imported"] = count
    conn.close()

    log.info(f"[{inbox_name}] Import complete: {count} total messages in DB")
    return summary


def _sync_one_inbox(config: dict, inbox_name: str) -> dict:
    """Sync one inbox with per-inbox locking and status."""
    if not try_lock_inbox(inbox_name):
        log.error(f"[{inbox_name}] Sync already running (locked by another process). Skipping.")
        return {"inbox": inbox_name, "errors": ["already running"]}

    status = {
        "running": True,
        "inbox": inbox_name,
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    write_status(inbox_name, status)

    try:
        summary = sync_inbox(config, inbox_name)
        status["running"] = False
        status["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        status["summary"] = summary
        write_status(inbox_name, status)
        return summary
    except Exception as e:
        log.error(f"[{inbox_name}] Sync failed: {e}")
        summary = {"inbox": inbox_name, "errors": [str(e)]}
        status["running"] = False
        status["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        status["summary"] = summary
        write_status(inbox_name, status)
        return summary
    finally:
        unlock_inbox(inbox_name)


def run_sync(config: dict, inbox_filter: Optional[str] = None):
    """Run sync for configured inboxes (sequentially)."""
    inboxes = config["inboxes"]
    if inbox_filter:
        inboxes = [ib for ib in inboxes if ib["name"] == inbox_filter]
        if not inboxes:
            log.error(f"Inbox '{inbox_filter}' not found in config")
            sys.exit(1)

    from import_mail import is_shutdown_requested

    summaries = []
    for inbox_cfg in inboxes:
        if is_shutdown_requested():
            log.info("Shutdown requested, stopping sync")
            break

        summary = _sync_one_inbox(config, inbox_cfg["name"])
        summaries.append(summary)

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
    statuses = read_all_status()
    if not statuses:
        print("No sync has been run yet.")
        return

    running = [s for s in statuses if s.get("running")]
    finished = [s for s in statuses if not s.get("running") and s.get("finished_at")]

    if running:
        print("Syncing:")
        for s in running:
            print(f"  {s.get('inbox', '?')}: started {s.get('started_at', '?')}")

    if finished:
        print("Last sync results:")
        for s in finished:
            sm = s.get("summary", {})
            errors = f", errors: {sm['errors']}" if sm.get("errors") else ""
            print(
                f"  {sm.get('inbox', s.get('inbox', '?'))}: "
                f"{sm.get('new_commits', 0)} new commits, "
                f"finished {s.get('finished_at', '?')}{errors}"
            )


def stop_sync(inbox_filter: Optional[str] = None):
    """Stop running sync processes by sending SIGTERM."""
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    lock_files = sorted(STATUS_DIR.glob("*.lock"))

    if not lock_files:
        print("No sync processes are running.")
        return

    stopped = 0
    for lf in lock_files:
        inbox_name = lf.stem
        if inbox_filter and inbox_name != inbox_filter:
            continue

        try:
            pid = int(lf.read_text().strip())
        except (ValueError, OSError):
            continue

        # Check if process is alive
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            print(f"  {inbox_name}: stale lock (PID {pid} not found), cleaning up")
            lf.unlink(missing_ok=True)
            # Clean up status
            status = read_status(inbox_name)
            if status.get("running"):
                status["running"] = False
                status["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                write_status(inbox_name, status)
            continue
        except PermissionError:
            print(f"  {inbox_name}: PID {pid} — no permission to signal")
            continue

        print(f"  {inbox_name}: sending SIGTERM to PID {pid}...")
        os.kill(pid, signal.SIGTERM)
        stopped += 1

    if inbox_filter and stopped == 0:
        print(f"No sync running for '{inbox_filter}'.")
        return

    if stopped == 0:
        print("No sync processes are running.")
        return

    # Wait for processes to exit gracefully
    print(f"Waiting for {stopped} process(es) to finish...")
    deadline = time.time() + 30
    while time.time() < deadline:
        still_running = 0
        for lf in lock_files:
            inbox_name = lf.stem
            if inbox_filter and inbox_name != inbox_filter:
                continue
            if not lf.exists():
                continue
            try:
                pid = int(lf.read_text().strip())
                os.kill(pid, 0)
                still_running += 1
            except (ProcessLookupError, ValueError, OSError):
                pass
        if still_running == 0:
            break
        time.sleep(0.5)

    print("Done.")


def main():
    parser = argparse.ArgumentParser(description="Sync lore mirror (fetch + import)")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--inbox", type=str, default=None)
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--stop", action="store_true",
                        help="Stop running sync (all or --inbox specific)")
    args = parser.parse_args()

    if args.status:
        show_status()
        return

    if args.stop:
        stop_sync(inbox_filter=args.inbox)
        return

    config = load_config(args.config)

    # Register signal handlers for graceful shutdown
    from import_mail import _signal_handler as import_signal_handler
    signal.signal(signal.SIGTERM, import_signal_handler)
    signal.signal(signal.SIGINT, import_signal_handler)

    # Per-inbox locking is handled inside _sync_one_inbox()
    run_sync(config, inbox_filter=args.inbox)


if __name__ == "__main__":
    main()
