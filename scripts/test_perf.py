#!/usr/bin/env python3
"""
Performance regression tests for lore-mirror.

Checks key API endpoints against time budgets and optional baselines.

Usage:
    python3 scripts/test_perf.py                          # test against localhost:8000
    python3 scripts/test_perf.py --url http://host:9000
    python3 scripts/test_perf.py --update-baselines       # save current timings as baselines
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error

BASELINE_FILE = "scripts/perf_baselines.json"

# Time budgets in seconds (generous to avoid flaky results)
BUDGETS = {
    "search_plain":           5.0,
    "search_subject":         5.0,
    "search_sender":          5.0,
    "search_date_range":      5.0,
    "search_combo_s_f_d":     5.0,
    "search_body":            5.0,
    "search_empty":           5.0,
    "inbox_list":             3.0,
    "inbox_first_page":       5.0,
    "inbox_last_page":        5.0,
    "stats":                  3.0,
}

PASS = 0
FAIL = 0
WARN = 0


def http_get(url, timeout=65):
    try:
        req = urllib.request.Request(url, headers={"X-Source": "perf-test"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def get_first_inbox(base_url):
    data = http_get(f"{base_url}/api/inboxes")
    if isinstance(data, list) and data:
        return data[0]["name"]
    return None


def check_perf(name, elapsed, budget, baseline=None):
    global PASS, FAIL, WARN
    tag = f"{elapsed:.3f}s"

    if elapsed > budget:
        print(f"  FAIL  {name:<25} {tag}  (exceeds {budget}s budget)")
        FAIL += 1
        return

    if baseline is not None and baseline > 0:
        ratio = elapsed / baseline
        if ratio > 5:
            print(f"  FAIL  {name:<25} {tag}  (5x regression vs baseline {baseline:.3f}s)")
            FAIL += 1
            return
        elif ratio > 2:
            print(f"  WARN  {name:<25} {tag}  (2x regression vs baseline {baseline:.3f}s)")
            WARN += 1
            return

    print(f"  OK    {name:<25} {tag}")
    PASS += 1


def measure(base_url, path, timeout=65):
    url = f"{base_url}{path}"
    start = time.time()
    http_get(url, timeout=timeout)
    return time.time() - start


def main():
    global PASS, FAIL, WARN

    parser = argparse.ArgumentParser(description="lore-mirror performance tests")
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--update-baselines", action="store_true",
                        help="Save current timings as baselines")
    args = parser.parse_args()

    base_url = args.url.rstrip("/")

    print("=" * 60)
    print("  lore-mirror performance tests")
    print("=" * 60)

    # Load baselines
    baselines = {}
    if os.path.exists(BASELINE_FILE) and not args.update_baselines:
        with open(BASELINE_FILE) as f:
            baselines = json.load(f)

    # Resolve inbox
    inbox = get_first_inbox(base_url)
    if not inbox:
        print("  No inboxes found. Aborting.")
        sys.exit(1)
    print(f"  Using inbox: {inbox}\n")

    results = {}

    # Define test cases: (name, path_template)
    tests = [
        ("search_plain",      f"/api/search?q=memory+leak&inbox={inbox}&per_page=10"),
        ("search_subject",    f"/api/search?q=s:PATCH&inbox={inbox}&per_page=10"),
        ("search_sender",     f"/api/search?q=f:torvalds&per_page=10"),
        ("search_date_range", f"/api/search?q=d:2000-01-01..2030-12-31&inbox={inbox}&per_page=10"),
        ("search_combo_s_f_d", f"/api/search?q=s:PATCH+f:torvalds+d:2000-01-01..2030-12-31&inbox={inbox}&per_page=10"),
        ("search_body",       f"/api/search?q=b:scheduler&inbox={inbox}&per_page=10"),
        ("search_empty",      f"/api/search?q=s:zzzznonexistent999xxx&inbox={inbox}&per_page=10"),
        ("inbox_list",        "/api/inboxes"),
        ("inbox_first_page",  f"/api/inboxes/{inbox}?per_page=20"),
        ("inbox_last_page",   f"/api/inboxes/{inbox}?last=1"),
        ("stats",             "/api/stats"),
    ]

    for name, path in tests:
        budget = BUDGETS.get(name, 5.0)
        baseline = baselines.get(name)
        elapsed = measure(base_url, path)
        results[name] = elapsed
        check_perf(name, elapsed, budget, baseline)

    # Save baselines if requested
    if args.update_baselines:
        with open(BASELINE_FILE, "w") as f:
            json.dump({k: round(v, 4) for k, v in results.items()}, f, indent=2)
        print(f"\n  Baselines saved to {BASELINE_FILE}")

    total = PASS + FAIL + WARN
    print(f"\n{'=' * 60}")
    print(f"  Results: {PASS} passed, {FAIL} failed, {WARN} warnings  ({total} total)")
    print(f"{'=' * 60}")

    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
