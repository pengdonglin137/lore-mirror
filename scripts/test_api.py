#!/usr/bin/env python3
"""
Automated API test suite for lore-mirror.

Tests all endpoints documented in docs/API.md against a running server.
No external dependencies required (uses urllib from stdlib).

Usage:
    python3 scripts/test_api.py                    # test against localhost:8000
    python3 scripts/test_api.py --url http://host:9000
    python3 scripts/test_api.py -v                 # verbose (show response snippets)
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error
import urllib.parse

# ── Test framework ───────────────────────────────────

PASS = 0
FAIL = 0
WARN = 0
SKIP = 0
SAVED = {}
VERBOSE = False


def request(base_url, method, path, timeout=35):
    """Make an HTTP request, return (status, headers, body_bytes)."""
    url = base_url.rstrip("/") + path
    req = urllib.request.Request(url, method=method)
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()
    except urllib.error.URLError as e:
        raise ConnectionError(f"Cannot connect to {base_url}: {e.reason}")
    except TimeoutError:
        raise TimeoutError(f"Request timed out after {timeout}s: {path}")


def test(base_url, name, method, path, *,
         expect_status=200, expect_keys=None, expect_type=None,
         expect_content_type=None, validate=None, save_as=None, timeout=35):
    """Run a single test case. Returns parsed data or None."""
    global PASS, FAIL, WARN

    try:
        start = time.time()
        status, headers, body = request(base_url, method, path, timeout=timeout)
        elapsed = time.time() - start

        # Status check
        if status != expect_status:
            print(f"  FAIL  {name}")
            print(f"        Expected HTTP {expect_status}, got {status}")
            if status < 500:
                print(f"        Body: {body.decode('utf-8', errors='replace')[:200]}")
            FAIL += 1
            return None

        # Content-Type check
        if expect_content_type:
            ct = headers.get("content-type", headers.get("Content-Type", ""))
            if expect_content_type not in ct:
                print(f"  FAIL  {name}")
                print(f"        Expected Content-Type '{expect_content_type}', got '{ct}'")
                FAIL += 1
                return None

        # Parse JSON if needed
        data = None
        if expect_type or expect_keys or validate or save_as:
            if expect_content_type and "rfc822" in (expect_content_type or ""):
                data = body  # raw email
            else:
                try:
                    data = json.loads(body)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    print(f"  FAIL  {name}")
                    print(f"        Response is not valid JSON")
                    FAIL += 1
                    return None

        # Type check
        if expect_type and not isinstance(data, expect_type):
            print(f"  FAIL  {name}")
            print(f"        Expected type {expect_type.__name__}, got {type(data).__name__}")
            FAIL += 1
            return None

        # Keys check
        if expect_keys and isinstance(data, dict):
            missing = [k for k in expect_keys if k not in data]
            if missing:
                print(f"  FAIL  {name}")
                print(f"        Missing keys: {missing}")
                FAIL += 1
                return None

        # Custom validation
        if validate:
            err = validate(data, body, headers)
            if err:
                if err.startswith("WARN:"):
                    print(f"  WARN  {name}")
                    print(f"        {err}")
                    WARN += 1
                else:
                    print(f"  FAIL  {name}")
                    print(f"        {err}")
                    FAIL += 1
                    return None

        if save_as and data is not None:
            SAVED[save_as] = data

        tag = f"({elapsed:.1f}s)" if elapsed > 1 else ""
        print(f"  OK    {name} {tag}")
        if VERBOSE and isinstance(data, dict):
            preview = {k: v for k, v in list(data.items())[:4]}
            print(f"        {json.dumps(preview, ensure_ascii=False, default=str)[:120]}")
        PASS += 1
        return data

    except (ConnectionError, TimeoutError) as e:
        print(f"  FAIL  {name}")
        print(f"        {e}")
        FAIL += 1
        return None
    except Exception as e:
        print(f"  FAIL  {name}")
        print(f"        Exception: {type(e).__name__}: {e}")
        FAIL += 1
        return None


def skip(name, reason=""):
    global SKIP
    print(f"  SKIP  {name}{f' ({reason})' if reason else ''}")
    SKIP += 1


# ── Validators ───────────────────────────────────────

def v_search(d, body, headers, expect_results=True):
    """Validate search response structure."""
    for k in ["query", "total", "page", "per_page", "pages", "messages"]:
        if k not in d:
            return f"Missing key '{k}'"
    if expect_results and d["total"] == 0:
        return "Expected results but total=0"
    for m in d.get("messages", []):
        for k in ["id", "message_id", "subject", "sender", "date", "inbox_name"]:
            if k not in m:
                return f"Search result missing key '{k}'"
    if d.get("warning"):
        return f"WARN: {d['warning']}"
    return None


# ── Test suite ───────────────────────────────────────

def run_tests(base_url):
    print("=" * 65)
    print(f"  lore-mirror API Test Suite")
    print(f"  Target: {base_url}")
    print("=" * 65)

    # ── 1. GET /api/stats ──
    print("\n── 1. GET /api/stats ──")

    test(base_url, "Basic stats", "GET", "/api/stats",
         expect_keys=["total_messages", "total_inboxes", "database_size_bytes", "latest_message"],
         validate=lambda d, b, h: (
             "total_messages should be > 0" if d["total_messages"] <= 0
             else "total_inboxes should be > 0" if d["total_inboxes"] <= 0
             else f"latest_message date anomalous: {d['latest_message']['date']}"
                 if d.get("latest_message") and d["latest_message"]["date"][:4] > "2027"
             else None
         ))

    # ── 2. GET /api/inboxes ──
    print("\n── 2. GET /api/inboxes ──")

    test(base_url, "List inboxes", "GET", "/api/inboxes",
         expect_type=list,
         validate=lambda d, b, h: (
             "Should return non-empty list" if len(d) == 0
             else next(
                 (f"Inbox missing key '{k}'" for ib in d
                  for k in ["name", "description", "message_count", "earliest", "latest"]
                  if k not in ib),
                 None
             )
         ),
         save_as="inboxes")

    # Determine first available inbox for subsequent tests
    inboxes = SAVED.get("inboxes", [])
    inbox_name = inboxes[0]["name"] if inboxes else None
    if not inbox_name:
        print("  FATAL: No inboxes available, cannot continue tests")
        return

    # ── 3. GET /api/locate ──
    print("\n── 3. GET /api/locate ──")

    test(base_url, "Locate inbox: linux", "GET", "/api/locate?q=linux",
         expect_keys=["query", "matches"],
         validate=lambda d, b, h: (
             None if d["matches"] else "No matches for 'linux'"
         ))

    test(base_url, "Locate: empty query (422)", "GET", "/api/locate?q=",
         expect_status=422)

    test(base_url, "Locate: no match", "GET", "/api/locate?q=zzzznonexistent999",
         expect_keys=["query", "matches"],
         validate=lambda d, b, h: None if len(d["matches"]) == 0 else "Should return empty")

    # ── 4. GET /api/inboxes/{name} ──
    print(f"\n── 4. GET /api/inboxes/{{name}} (using '{inbox_name}') ──")

    test(base_url, f"Inbox detail: {inbox_name}", "GET",
         f"/api/inboxes/{inbox_name}?page=1&per_page=3",
         validate=lambda d, b, h: (
             next((f"Missing key '{k}'" for k in ["inbox", "total", "page", "per_page", "pages", "messages"] if k not in d), None)
             or (f"Expected 3 messages, got {len(d['messages'])}" if len(d["messages"]) != 3 else None)
             or next((f"Message missing '{k}'" for m in d["messages"]
                      for k in ["id", "message_id", "subject", "sender", "date", "in_reply_to"] if k not in m), None)
         ),
         save_as="inbox_detail")

    test(base_url, "Inbox: nonexistent (404)", "GET", "/api/inboxes/nonexistent_xyz",
         expect_status=404)

    test(base_url, "Inbox: page=0 (422)", "GET", f"/api/inboxes/{inbox_name}?page=0",
         expect_status=422)

    test(base_url, "Inbox: per_page=300 (422)", "GET", f"/api/inboxes/{inbox_name}?per_page=300",
         expect_status=422)

    test(base_url, "Inbox: huge page (empty)", "GET", f"/api/inboxes/{inbox_name}?page=999999",
         validate=lambda d, b, h: None if len(d["messages"]) == 0 else "Should be empty")

    test(base_url, "Inbox: default pagination", "GET", f"/api/inboxes/{inbox_name}",
         validate=lambda d, b, h: None if d["per_page"] == 50 and d["page"] == 1
         else f"Expected per_page=50 page=1")

    # ── 5. GET /api/messages/{message_id} ──
    print("\n── 5. GET /api/messages/{message_id} ──")

    msgs = SAVED.get("inbox_detail", {}).get("messages", [])
    msg_id = msgs[0]["message_id"] if msgs else None

    if msg_id:
        test(base_url, f"Get message: {msg_id[:45]}...", "GET",
             f"/api/messages/{urllib.parse.quote(msg_id, safe='')}",
             validate=lambda d, b, h: (
                 next((f"Missing key '{k}'" for k in
                       ["id", "message_id", "inbox_name", "subject", "sender", "date",
                        "in_reply_to", "body_text", "headers", "attachments"]
                       if k not in d), None)
                 or ("raw_email should be excluded" if "raw_email" in d else None)
                 or (f"headers should be dict" if not isinstance(d["headers"], dict) else None)
                 or (f"attachments should be list" if not isinstance(d["attachments"], list) else None)
             ))
    else:
        skip("Get message", "no message_id available")

    test(base_url, "Message: nonexistent (404)", "GET",
         "/api/messages/nonexistent%40nope.invalid", expect_status=404)

    # ── 6. GET /api/raw ──
    print("\n── 6. GET /api/raw?id={message_id} ──")

    if msg_id:
        test(base_url, "Get raw email", "GET",
             f"/api/raw?id={urllib.parse.quote(msg_id, safe='')}",
             expect_content_type="message/rfc822",
             validate=lambda d, b, h: None if len(b) > 100 else "Raw email too short")
    else:
        skip("Get raw email", "no message_id")

    test(base_url, "Raw: nonexistent (404)", "GET",
         "/api/raw?id=nonexistent%40nope.invalid", expect_status=404)

    # ── 7. GET /api/threads/{message_id} ──
    print("\n── 7. GET /api/threads/{message_id} ──")

    # Pick a message with in_reply_to for better thread coverage
    thread_msg_id = None
    for m in msgs:
        if m.get("in_reply_to"):
            thread_msg_id = m["message_id"]
            break
    if not thread_msg_id:
        thread_msg_id = msg_id

    if thread_msg_id:
        test(base_url, f"Get thread: {thread_msg_id[:45]}...", "GET",
             f"/api/threads/{urllib.parse.quote(thread_msg_id, safe='')}",
             validate=lambda d, b, h: (
                 next((f"Missing key '{k}'" for k in ["root", "total", "inbox", "messages"] if k not in d), None)
                 or ("Thread should have >= 1 message" if d["total"] <= 0 else None)
                 or next((f"Thread message missing '{k}'" for m in d["messages"]
                          for k in ["id", "message_id", "subject", "sender", "date", "in_reply_to"]
                          if k not in m), None)
                 or ("Messages not sorted by date ASC"
                     if [m["date"] for m in d["messages"] if m["date"]]
                        != sorted(m["date"] for m in d["messages"] if m["date"])
                     else None)
             ))
    else:
        skip("Get thread", "no message_id")

    test(base_url, "Thread: nonexistent (404)", "GET",
         "/api/threads/nonexistent%40nope.invalid", expect_status=404)

    # ── 8. GET /api/search ──
    print("\n── 8. GET /api/search ──")

    # Basic FTS
    test(base_url, "Search: basic FTS", "GET",
         f"/api/search?q=memory+leak&inbox={inbox_name}&per_page=3",
         validate=lambda d, b, h: v_search(d, b, h))

    # s: prefix
    test(base_url, "Search: s: (subject)", "GET",
         f"/api/search?q=s:PATCH&inbox={inbox_name}&per_page=2",
         validate=lambda d, b, h: v_search(d, b, h))

    # f: prefix
    test(base_url, "Search: f: (from)", "GET",
         f"/api/search?q=f:torvalds&inbox={inbox_name}&per_page=2",
         validate=lambda d, b, h: v_search(d, b, h))

    # b: prefix
    test(base_url, "Search: b: (body)", "GET",
         f"/api/search?q=b:scheduler&inbox={inbox_name}&per_page=2",
         validate=lambda d, b, h: v_search(d, b, h))

    # bs: prefix
    test(base_url, "Search: bs: (subject+body)", "GET",
         f"/api/search?q=bs:regression&inbox={inbox_name}&per_page=2",
         validate=lambda d, b, h: v_search(d, b, h))

    # d: date range — use the inbox's known date range
    latest_date = None
    for ib in inboxes:
        if ib["name"] == inbox_name and ib.get("latest"):
            latest_date = ib["latest"][:10]
            break
    if latest_date:
        test(base_url, "Search: d: date range", "GET",
             f"/api/search?q=d:2000-01-01..{latest_date}&inbox={inbox_name}&per_page=2",
             validate=lambda d, b, h: v_search(d, b, h))

        test(base_url, "Search: d: single date", "GET",
             f"/api/search?q=d:{latest_date}&inbox={inbox_name}&per_page=2",
             validate=lambda d, b, h: v_search(d, b, h))

        test(base_url, "Search: d: open-ended", "GET",
             f"/api/search?q=d:2000-01-01..&inbox={inbox_name}&per_page=2",
             validate=lambda d, b, h: v_search(d, b, h))
    else:
        skip("Search: d: date tests", "no latest date available")

    # m: prefix (Message-ID) — may match in multiple inboxes
    if msg_id:
        test(base_url, "Search: m: (Message-ID)", "GET",
             f"/api/search?q=m:{urllib.parse.quote(msg_id, safe='')}&inbox={inbox_name}",
             validate=lambda d, b, h: v_search(d, b, h) or (
                 None if d["total"] >= 1 else f"Expected >= 1 result, got {d['total']}"))
    else:
        skip("Search: m: prefix", "no message_id")

    # Message-ID auto-detection
    if msg_id:
        test(base_url, "Search: Message-ID auto-detect", "GET",
             f"/api/search?q={urllib.parse.quote(msg_id, safe='')}",
             validate=lambda d, b, h: v_search(d, b, h) or (
                 None if d["total"] == 1 else f"Expected 1, got {d['total']}"))
    else:
        skip("Search: Message-ID auto-detect", "no message_id")

    # Combo: f: + d:
    if latest_date:
        test(base_url, "Search: combo f:+d:", "GET",
             f"/api/search?q=f:torvalds+d:2000-01-01..{latest_date}&inbox={inbox_name}&per_page=2",
             validate=lambda d, b, h: v_search(d, b, h))
    else:
        skip("Search: combo f:+d:", "no date info")

    # FTS snippet
    test(base_url, "Search: snippet <mark> tags", "GET",
         f"/api/search?q=memory+leak&inbox={inbox_name}&per_page=1",
         validate=lambda d, b, h: v_search(d, b, h) or (
             None if d["messages"] and "<mark>" in d["messages"][0].get("snippet", "")
             else "Expected <mark> in snippet"))

    # t: prefix
    test(base_url, "Search: t: (To header)", "GET",
         f"/api/search?q=t:linux&inbox={inbox_name}&per_page=2",
         validate=lambda d, b, h: v_search(d, b, h))

    # Quoted phrase
    test(base_url, "Search: quoted phrase", "GET",
         f'/api/search?q=s:"use+after+free"&inbox={inbox_name}&per_page=2',
         validate=lambda d, b, h: v_search(d, b, h))

    # Empty query (422)
    test(base_url, "Search: empty query (422)", "GET",
         "/api/search?q=", expect_status=422)

    # Pagination
    test(base_url, "Search: pagination", "GET",
         f"/api/search?q=PATCH&inbox={inbox_name}&page=2&per_page=5",
         validate=lambda d, b, h: v_search(d, b, h) or (
             None if d["page"] == 2 and d["per_page"] == 5
             else f"Expected page=2 per_page=5"))

    # Inbox filter
    test(base_url, "Search: inbox filter", "GET",
         f"/api/search?q=memory&inbox={inbox_name}&per_page=2",
         validate=lambda d, b, h: v_search(d, b, h) or (
             None if all(m["inbox_name"] == inbox_name for m in d["messages"])
             else "Results from wrong inbox"))

    # f: with email address (should use FTS, not hang on LIKE scan)
    test(base_url, "Search: f: email address (FTS)", "GET",
         f"/api/search?q=f:torvalds@linux-foundation.org&per_page=2",
         timeout=10,
         validate=lambda d, b, h: v_search(d, b, h))

    # f: with @ should NOT trigger Message-ID auto-detect
    test(base_url, "Search: f:user@domain not treated as Message-ID", "GET",
         f"/api/search?q=f:someone@kernel.org&inbox={inbox_name}&per_page=2",
         timeout=10,
         validate=lambda d, b, h: (
             v_search(d, b, h, expect_results=False)))

    # Verify f: results match the sender
    test(base_url, "Search: f: results have correct sender", "GET",
         f"/api/search?q=f:torvalds&per_page=5",
         timeout=10,
         validate=lambda d, b, h: v_search(d, b, h) or (
             None if all("torvalds" in m["sender"].lower() for m in d["messages"])
             else f"Result sender doesn't match: {d['messages'][0]['sender']}"))

    # ── 9. GET /api/sync/status ──
    print("\n── 9. GET /api/sync/status ──")

    test(base_url, "Sync status", "GET", "/api/sync/status",
         expect_keys=["running"],
         validate=lambda d, b, h: None)

    # ── Summary ──
    print("\n" + "=" * 65)
    total = PASS + FAIL + WARN + SKIP
    print(f"  Results: {PASS} passed, {FAIL} failed, {WARN} warnings, {SKIP} skipped  ({total} total)")
    print("=" * 65)


def main():
    global VERBOSE

    parser = argparse.ArgumentParser(description="lore-mirror API test suite")
    parser.add_argument("--url", default="http://localhost:8000",
                        help="Base URL of the server (default: http://localhost:8000)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Show response snippets for passing tests")
    args = parser.parse_args()

    VERBOSE = args.verbose

    # Connectivity check
    try:
        status, _, _ = request(args.url, "GET", "/api/stats", timeout=10)
        if status != 200:
            print(f"Server at {args.url} returned HTTP {status} for /api/stats")
            sys.exit(1)
    except Exception as e:
        print(f"Cannot connect to server at {args.url}: {e}")
        sys.exit(1)

    run_tests(args.url)
    sys.exit(1 if FAIL > 0 else 0)


if __name__ == "__main__":
    main()
