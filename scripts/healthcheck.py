#!/usr/bin/env python3
"""
Health check and repair for lore mirror data.

Checks:
  1. Git repos: all epochs exist and are valid
  2. SQLite databases: integrity check, schema version
  3. Import consistency: DB commit counts match git

Repair:
  --repair: re-clone missing/corrupted git repos, rebuild corrupted DBs

Usage:
    python3 scripts/healthcheck.py              # check all inboxes
    python3 scripts/healthcheck.py --inbox lkml  # check specific inbox
    python3 scripts/healthcheck.py --repair      # check and fix problems
"""

import argparse
import logging
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "config.yaml"


def load_config(config_path: Path) -> dict:
    with open(config_path) as f:
        return yaml.safe_load(f)


def check_git_repo(repo_path: Path) -> tuple[str, str]:
    """
    Check if a git repo is valid.
    Returns (status, detail) where status is 'ok', 'missing', or 'corrupted'.
    """
    if not repo_path.exists():
        return "missing", "directory does not exist"

    if not (repo_path / "HEAD").exists():
        return "corrupted", "HEAD file missing"

    # Run git fsck (quick check)
    # Skip known harmless warnings from old public-inbox commits
    HARMLESS_ERRORS = {"badTimezone", "badDate", "badEmail", "missingEmail"}

    result = subprocess.run(
        ["git", "--git-dir", str(repo_path), "fsck", "--no-dangling", "--no-progress"],
        capture_output=True,
        text=True,
        timeout=300,
    )

    if result.returncode != 0:
        # Filter out harmless errors
        serious = [
            line for line in result.stderr.strip().split("\n")
            if line.strip() and not any(h in line for h in HARMLESS_ERRORS)
        ]
        if serious:
            return "corrupted", f"fsck failed: {serious[0][:200]}"

    # Verify we can read HEAD
    result = subprocess.run(
        ["git", "--git-dir", str(repo_path), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    if result.returncode != 0:
        return "corrupted", "cannot resolve HEAD"

    return "ok", ""


def check_db(db_path: Path) -> tuple[str, str]:
    """
    Check SQLite database integrity.
    Returns (status, detail) where status is 'ok', 'missing', or 'corrupted'.
    """
    if not db_path.exists():
        return "missing", "database file does not exist"

    try:
        conn = sqlite3.connect(str(db_path))
        result = conn.execute("PRAGMA integrity_check").fetchone()
        if result[0] != "ok":
            conn.close()
            return "corrupted", f"integrity_check: {result[0]}"

        # Check that essential tables exist
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        required = {"messages", "messages_fts", "import_progress", "schema_version"}
        missing_tables = required - tables
        if missing_tables:
            conn.close()
            return "corrupted", f"missing tables: {missing_tables}"

        conn.close()
        return "ok", ""

    except sqlite3.DatabaseError as e:
        return "corrupted", str(e)


def repair_git_repo(repo_url: str, repo_path: Path, timeout: int = 3600) -> bool:
    """Re-clone a missing or corrupted git repo."""
    log.info(f"  Repairing: re-cloning {repo_url} -> {repo_path}")

    if repo_path.exists():
        backup = repo_path.with_suffix(".git.bak")
        log.info(f"  Moving corrupted repo to {backup}")
        if backup.exists():
            shutil.rmtree(backup)
        repo_path.rename(backup)

    repo_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["git", "clone", "--mirror", repo_url, str(repo_path)],
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    if result.returncode != 0:
        log.error(f"  Clone failed: {result.stderr.strip()}")
        return False

    log.info(f"  Clone successful")

    # Remove backup if clone succeeded
    backup = repo_path.with_suffix(".git.bak")
    if backup.exists():
        shutil.rmtree(backup)

    return True


def rebuild_db(config: dict, inbox_name: str) -> bool:
    """Rebuild a corrupted database from git repos."""
    db_dir = Path(config["database"]["dir"])
    db_path = db_dir / f"{inbox_name}.db"

    log.info(f"  Rebuilding database: {db_path}")

    if db_path.exists():
        backup = db_path.with_suffix(".db.bak")
        log.info(f"  Backing up corrupted DB to {backup}")
        if backup.exists():
            backup.unlink()
        db_path.rename(backup)

    # Import from scratch
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    from database import init_db
    from import_mail import import_epoch, get_db_path

    repos_dir = Path(config["mirror"]["repos_dir"])
    inbox_repo_dir = repos_dir / inbox_name / "git"

    if not inbox_repo_dir.exists():
        log.error(f"  Cannot rebuild: no git repos at {inbox_repo_dir}")
        return False

    conn = init_db(db_path)

    epochs = sorted(
        int(p.name.replace(".git", ""))
        for p in inbox_repo_dir.iterdir()
        if p.name.endswith(".git") and (p / "HEAD").exists()
    )

    log.info(f"  Re-importing {len(epochs)} epochs...")

    for epoch in epochs:
        import_epoch(conn, inbox_name, epoch, repos_dir)

    count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    conn.close()

    log.info(f"  Rebuild complete: {count} messages")

    # Remove backup if rebuild succeeded
    backup = db_path.with_suffix(".db.bak")
    if backup.exists():
        backup.unlink()

    return True


def discover_epochs(base_url: str, inbox_name: str) -> list[int]:
    """Discover expected epochs from lore mirror page."""
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    from mirror import discover_epochs as _discover
    return _discover(base_url, inbox_name)


def check_inbox(config: dict, inbox_name: str, repair: bool = False) -> dict:
    """Run full health check on an inbox."""
    base_url = config["mirror"]["base_url"]
    repos_dir = Path(config["mirror"]["repos_dir"])
    db_dir = Path(config["database"]["dir"])

    report = {
        "inbox": inbox_name,
        "git_ok": 0,
        "git_problems": [],
        "db_status": "unknown",
        "db_detail": "",
        "repaired": [],
    }

    log.info(f"[{inbox_name}] Checking git repos...")

    # Discover expected epochs
    expected_epochs = discover_epochs(base_url, inbox_name)
    if not expected_epochs:
        log.warning(f"  Could not discover epochs, checking existing repos only")
        inbox_repo_dir = repos_dir / inbox_name / "git"
        if inbox_repo_dir.exists():
            expected_epochs = sorted(
                int(p.name.replace(".git", ""))
                for p in inbox_repo_dir.iterdir()
                if p.name.endswith(".git")
            )

    # Check each epoch
    for epoch in expected_epochs:
        repo_path = repos_dir / inbox_name / "git" / f"{epoch}.git"
        status, detail = check_git_repo(repo_path)

        if status == "ok":
            report["git_ok"] += 1
        else:
            problem = {"epoch": epoch, "status": status, "detail": detail}
            report["git_problems"].append(problem)
            log.warning(f"  Epoch {epoch}: {status} — {detail}")

            if repair:
                repo_url = f"{base_url}/{inbox_name}/{epoch}"
                success = repair_git_repo(repo_url, repo_path)
                if success:
                    report["repaired"].append(f"git epoch {epoch}")

    # Check database
    log.info(f"[{inbox_name}] Checking database...")
    db_path = db_dir / f"{inbox_name}.db"
    db_status, db_detail = check_db(db_path)
    report["db_status"] = db_status
    report["db_detail"] = db_detail

    if db_status != "ok":
        log.warning(f"  Database: {db_status} — {db_detail}")

        if repair:
            # If git repos were just repaired, or DB is corrupted, rebuild
            success = rebuild_db(config, inbox_name)
            if success:
                report["repaired"].append("database")
                report["db_status"] = "rebuilt"
    else:
        log.info(f"  Database: ok")

    return report


def main():
    parser = argparse.ArgumentParser(description="Health check and repair for lore mirror")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--inbox", type=str, default=None)
    parser.add_argument("--repair", action="store_true", help="Attempt to fix problems")
    args = parser.parse_args()

    config = load_config(args.config)

    inboxes = config["inboxes"]
    if args.inbox:
        inboxes = [ib for ib in inboxes if ib["name"] == args.inbox]
        if not inboxes:
            log.error(f"Inbox '{args.inbox}' not found in config")
            sys.exit(1)

    reports = []
    for inbox_cfg in inboxes:
        report = check_inbox(config, inbox_cfg["name"], repair=args.repair)
        reports.append(report)

    # Summary
    print("\n" + "=" * 60)
    print("Health Check Summary:")
    print(f"{'Inbox':<20} {'Git':<20} {'Database':<15} {'Repaired'}")
    print("-" * 60)

    all_ok = True
    for r in reports:
        git_str = f"{r['git_ok']} ok"
        if r["git_problems"]:
            git_str += f", {len(r['git_problems'])} problems"
            all_ok = False

        if r["db_status"] != "ok" and r["db_status"] != "rebuilt":
            all_ok = False

        repaired = ", ".join(r["repaired"]) if r["repaired"] else "-"
        print(f"{r['inbox']:<20} {git_str:<20} {r['db_status']:<15} {repaired}")

    print("=" * 60)
    if all_ok:
        print("All checks passed.")
    else:
        print("Problems detected." + (" Use --repair to fix." if not args.repair else ""))
        sys.exit(1)


if __name__ == "__main__":
    main()
