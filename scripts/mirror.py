#!/usr/bin/env python3
"""
lore.kernel.org git mirror downloader.

Downloads and maintains local mirrors of kernel mailing list archives
stored as public-inbox git repositories.

Usage:
    python3 scripts/mirror.py                # clone/fetch all configured inboxes
    python3 scripts/mirror.py --inbox lkml   # clone/fetch specific inbox only
    python3 scripts/mirror.py --status       # show status of all repos
"""

import argparse
import logging
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# Project root: one level up from scripts/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "config.yaml"


@dataclass
class InboxConfig:
    name: str
    description: str = ""


@dataclass
class MirrorConfig:
    base_url: str
    repos_dir: Path
    max_concurrent_downloads: int = 2
    max_retries: int = 3
    git_timeout: int = 3600
    inboxes: list[InboxConfig] = field(default_factory=list)


def load_config(config_path: Path) -> MirrorConfig:
    """Load and parse config.yaml."""
    with open(config_path) as f:
        raw = yaml.safe_load(f)

    mirror = raw["mirror"]
    inboxes = [
        InboxConfig(name=ib["name"], description=ib.get("description", ""))
        for ib in raw["inboxes"]
    ]

    return MirrorConfig(
        base_url=mirror["base_url"].rstrip("/"),
        repos_dir=Path(mirror["repos_dir"]),
        max_concurrent_downloads=mirror.get("max_concurrent_downloads", 2),
        max_retries=mirror.get("max_retries", 3),
        git_timeout=mirror.get("git_timeout", 3600),
        inboxes=inboxes,
    )


def discover_epochs(base_url: str, inbox_name: str) -> list[int]:
    """
    Discover available epochs for an inbox by fetching its mirror page.

    Falls back to probing if the mirror page is inaccessible.
    """
    mirror_url = f"{base_url}/{inbox_name}/_/text/mirror/"
    log.info(f"Discovering epochs for '{inbox_name}' from {mirror_url}")

    try:
        req = Request(mirror_url, headers={"User-Agent": "lore-mirror/1.0"})
        with urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        # Extract epoch numbers from: git clone --mirror https://.../{inbox}/{N}
        pattern = rf"{re.escape(base_url)}/{re.escape(inbox_name)}/(\d+)"
        epochs = sorted(set(int(m) for m in re.findall(pattern, html)))

        if epochs:
            log.info(f"  Found {len(epochs)} epochs: {epochs[0]}..{epochs[-1]}")
            return epochs
    except (URLError, HTTPError) as e:
        log.warning(f"  Could not fetch mirror page: {e}")

    # Fallback: probe epochs starting from 0
    log.info(f"  Falling back to epoch probing for '{inbox_name}'")
    return probe_epochs(base_url, inbox_name)


def probe_epochs(base_url: str, inbox_name: str) -> list[int]:
    """
    Probe for epochs by trying git ls-remote on sequential epoch numbers.
    Stops after the first failure.
    """
    epochs = []
    for i in range(100):  # no inbox has 100+ epochs
        repo_url = f"{base_url}/{inbox_name}/{i}"
        try:
            result = subprocess.run(
                ["git", "ls-remote", repo_url],
                capture_output=True,
                timeout=30,
            )
            if result.returncode == 0:
                epochs.append(i)
                log.info(f"  Epoch {i}: exists")
            else:
                log.info(f"  Epoch {i}: not found, stopping probe")
                break
        except subprocess.TimeoutExpired:
            log.warning(f"  Epoch {i}: timeout, stopping probe")
            break

    log.info(f"  Probed {len(epochs)} epochs for '{inbox_name}'")
    return epochs


def git_clone_mirror(repo_url: str, local_path: Path, timeout: int) -> bool:
    """Run git clone --mirror."""
    log.info(f"  Cloning {repo_url} -> {local_path}")
    local_path.parent.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        ["git", "clone", "--mirror", repo_url, str(local_path)],
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    if result.returncode != 0:
        log.error(f"  Clone failed: {result.stderr.strip()}")
        return False

    log.info(f"  Clone complete: {local_path}")
    return True


def git_fetch(local_path: Path, timeout: int) -> bool:
    """Run git fetch in an existing mirror repo to update it."""
    log.info(f"  Fetching updates for {local_path}")

    result = subprocess.run(
        ["git", "--git-dir", str(local_path), "fetch", "--prune"],
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    if result.returncode != 0:
        log.error(f"  Fetch failed: {result.stderr.strip()}")
        return False

    log.info(f"  Fetch complete: {local_path}")
    return True


def sync_epoch(
    base_url: str,
    inbox_name: str,
    epoch: int,
    repos_dir: Path,
    timeout: int,
    max_retries: int,
) -> tuple[str, int, bool]:
    """
    Sync a single epoch: clone if new, fetch if exists.
    Returns (inbox_name, epoch, success).
    """
    local_path = repos_dir / inbox_name / "git" / f"{epoch}.git"
    repo_url = f"{base_url}/{inbox_name}/{epoch}"

    for attempt in range(1, max_retries + 1):
        try:
            if local_path.exists() and (local_path / "HEAD").exists():
                success = git_fetch(local_path, timeout)
            else:
                # Remove partial clone if exists
                if local_path.exists():
                    import shutil
                    shutil.rmtree(local_path)
                success = git_clone_mirror(repo_url, local_path, timeout)

            if success:
                return (inbox_name, epoch, True)

            log.warning(
                f"  Attempt {attempt}/{max_retries} failed for {inbox_name}/{epoch}"
            )

        except subprocess.TimeoutExpired:
            log.warning(
                f"  Timeout on attempt {attempt}/{max_retries} for {inbox_name}/{epoch}"
            )

        if attempt < max_retries:
            wait = 10 * attempt
            log.info(f"  Retrying in {wait}s...")
            time.sleep(wait)

    return (inbox_name, epoch, False)


def get_repo_status(repos_dir: Path, inbox_name: str) -> list[dict]:
    """Get status info for all epoch repos of an inbox."""
    inbox_dir = repos_dir / inbox_name / "git"
    if not inbox_dir.exists():
        return []

    statuses = []
    for repo_path in sorted(inbox_dir.iterdir()):
        if not repo_path.name.endswith(".git"):
            continue

        epoch = repo_path.name.replace(".git", "")
        head = repo_path / "HEAD"

        info = {"epoch": epoch, "path": str(repo_path)}

        if head.exists():
            # Count commits (approximate size indicator)
            try:
                result = subprocess.run(
                    ["git", "--git-dir", str(repo_path), "rev-list", "--count", "--all"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode == 0:
                    info["commits"] = int(result.stdout.strip())
            except (subprocess.TimeoutExpired, ValueError):
                info["commits"] = -1

            # Get disk size
            try:
                result = subprocess.run(
                    ["du", "-sh", str(repo_path)],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    info["size"] = result.stdout.split()[0]
            except subprocess.TimeoutExpired:
                info["size"] = "?"

            info["status"] = "ok"
        else:
            info["status"] = "incomplete"

        statuses.append(info)

    return statuses


def show_status(config: MirrorConfig):
    """Display status of all configured inboxes."""
    print(f"\n{'Inbox':<25} {'Epochs':<10} {'Commits':<12} {'Size':<10} {'Status'}")
    print("-" * 75)

    for inbox in config.inboxes:
        statuses = get_repo_status(config.repos_dir, inbox.name)
        if not statuses:
            print(f"{inbox.name:<25} {'—':<10} {'—':<12} {'—':<10} not downloaded")
            continue

        total_commits = 0
        all_ok = True
        for s in statuses:
            total_commits += s.get("commits", 0)
            if s["status"] != "ok":
                all_ok = False

        # Size of the whole inbox dir
        try:
            result = subprocess.run(
                ["du", "-sh", str(config.repos_dir / inbox.name)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            total_size = result.stdout.split()[0] if result.returncode == 0 else "?"
        except subprocess.TimeoutExpired:
            total_size = "?"

        status_str = "ok" if all_ok else "incomplete"
        print(
            f"{inbox.name:<25} {len(statuses):<10} {total_commits:<12} {total_size:<10} {status_str}"
        )


def run_sync(config: MirrorConfig, inbox_filter: Optional[str] = None):
    """Main sync logic: discover epochs and download/update repos."""
    inboxes = config.inboxes
    if inbox_filter:
        inboxes = [ib for ib in inboxes if ib.name == inbox_filter]
        if not inboxes:
            log.error(f"Inbox '{inbox_filter}' not found in config")
            sys.exit(1)

    # Phase 1: discover epochs for all inboxes
    inbox_epochs: dict[str, list[int]] = {}
    for inbox in inboxes:
        epochs = discover_epochs(config.base_url, inbox.name)
        if not epochs:
            log.warning(f"No epochs found for '{inbox.name}', skipping")
            continue
        inbox_epochs[inbox.name] = epochs

    # Phase 2: build task list
    tasks = []
    for inbox_name, epochs in inbox_epochs.items():
        for epoch in epochs:
            tasks.append((inbox_name, epoch))

    total = len(tasks)
    log.info(f"Total sync tasks: {total}")

    if total == 0:
        log.info("Nothing to sync")
        return

    # Phase 3: execute with thread pool
    succeeded = 0
    failed = 0

    with ThreadPoolExecutor(max_workers=config.max_concurrent_downloads) as pool:
        futures = {
            pool.submit(
                sync_epoch,
                config.base_url,
                inbox_name,
                epoch,
                config.repos_dir,
                config.git_timeout,
                config.max_retries,
            ): (inbox_name, epoch)
            for inbox_name, epoch in tasks
        }

        for future in as_completed(futures):
            inbox_name, epoch, success = future.result()
            if success:
                succeeded += 1
            else:
                failed += 1
            log.info(
                f"Progress: {succeeded + failed}/{total} "
                f"(ok: {succeeded}, fail: {failed}) "
                f"— {inbox_name}/{epoch}: {'OK' if success else 'FAILED'}"
            )

    log.info(f"\nSync complete: {succeeded} succeeded, {failed} failed out of {total}")

    if failed > 0:
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="lore.kernel.org git mirror tool")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Path to config.yaml",
    )
    parser.add_argument(
        "--inbox",
        type=str,
        default=None,
        help="Sync only this inbox (must be in config)",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show status of all repos",
    )

    args = parser.parse_args()
    config = load_config(args.config)

    if args.status:
        show_status(config)
    else:
        run_sync(config, inbox_filter=args.inbox)


if __name__ == "__main__":
    main()
