#!/usr/bin/env python3
"""
Test cases for the search query parser.

Usage:
    python3 scripts/test_search.py
"""

import sys
sys.path.insert(0, ".")

from server.app import parse_search_query


def test(name, query, expect_fts=None, expect_where_count=None, expect_params_contains=None):
    fts, where, params = parse_search_query(query)
    errors = []

    if expect_fts is not None and fts != expect_fts:
        errors.append(f"FTS: expected {expect_fts!r}, got {fts!r}")
    if expect_where_count is not None and len(where) != expect_where_count:
        errors.append(f"WHERE count: expected {expect_where_count}, got {len(where)}")
    if expect_params_contains is not None:
        for p in expect_params_contains:
            if p not in params:
                errors.append(f"PARAMS missing: {p!r} not in {params}")

    if errors:
        print(f"FAIL: {name}")
        for e in errors:
            print(f"  {e}")
        return False
    else:
        print(f"OK:   {name}")
        return True


passed = 0
failed = 0

tests = [
    # Plain text search
    ("plain text", "memory leak",
     {"expect_fts": "memory leak", "expect_where_count": 0}),

    # Subject prefix
    ("s: subject", 's:PATCH',
     {"expect_fts": "subject:PATCH", "expect_where_count": 0}),

    # Subject with quoted phrase
    ("s: quoted phrase", 's:"memory leak"',
     {"expect_fts": "subject:memory leak", "expect_where_count": 0}),

    # From prefix
    ("f: from/sender", "f:torvalds",
     {"expect_fts": None, "expect_where_count": 1, "expect_params_contains": ["%torvalds%"]}),

    # Body prefix
    ("b: body", "b:kasan",
     {"expect_fts": "body_text:kasan", "expect_where_count": 0}),

    # Subject + body
    ("bs: subject+body", "bs:regression",
     {"expect_fts": "(subject:regression OR body_text:regression)", "expect_where_count": 0}),

    # Date range (open-ended start)
    ("d: date from", "d:2026-01-01..",
     {"expect_fts": None, "expect_where_count": 1, "expect_params_contains": ["2026-01-01"]}),

    # Date range (open-ended end)
    ("d: date to", "d:..2026-03-01",
     {"expect_fts": None, "expect_where_count": 1, "expect_params_contains": ["2026-03-01T23:59:59"]}),

    # Date range (both sides)
    ("d: full range", "d:2026-01-01..2026-03-01",
     {"expect_fts": None, "expect_where_count": 2,
      "expect_params_contains": ["2026-01-01", "2026-03-01T23:59:59"]}),

    # Single date
    ("d: single date", "d:2026-02-15",
     {"expect_fts": None, "expect_where_count": 2,
      "expect_params_contains": ["2026-02-15", "2026-02-15T23:59:59"]}),

    # To header
    ("t: to header", "t:linux-mm@kvack.org",
     {"expect_fts": None, "expect_where_count": 1}),

    # Cc header
    ("c: cc header", "c:stable@vger.kernel.org",
     {"expect_fts": None, "expect_where_count": 1}),

    # Any address
    ("a: any address", "a:torvalds",
     {"expect_fts": None, "expect_where_count": 1, "expect_params_contains": ["%torvalds%"]}),

    # Combined: subject + from + date
    ("combined s: f: d:", "s:PATCH f:torvalds d:2026-01-01..",
     {"expect_fts": "subject:PATCH", "expect_where_count": 2,
      "expect_params_contains": ["%torvalds%", "2026-01-01"]}),

    # Combined: plain text + from
    ("combined plain + f:", "memory leak f:kasan",
     {"expect_fts": "memory leak", "expect_where_count": 1,
      "expect_params_contains": ["%kasan%"]}),

    # Message-ID prefix
    ("m: message-id", "m:20260110-can_usb@pengutronix.de",
     {"expect_fts": None, "expect_where_count": 1,
      "expect_params_contains": ["20260110-can_usb@pengutronix.de"]}),

    # Message-ID with angle brackets
    ("m: message-id brackets", "m:<foo@bar.com>",
     {"expect_fts": None, "expect_where_count": 1,
      "expect_params_contains": ["foo@bar.com"]}),
]

for name, query, kwargs in tests:
    if test(name, query, **kwargs):
        passed += 1
    else:
        failed += 1

print(f"\n{'='*40}")
print(f"Results: {passed} passed, {failed} failed")
if failed > 0:
    sys.exit(1)
