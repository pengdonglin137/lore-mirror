#!/usr/bin/env python3
"""
Unit tests for lore-mirror (no server required).

Tests pure functions from import_mail, database, and server modules.

Usage:
    python3 scripts/test_unit.py
    python3 scripts/test_unit.py -v
"""

import json
import os
import re
import sys
import tempfile
import time

sys.path.insert(0, ".")
sys.path.insert(0, "scripts")

PASS = 0
FAIL = 0
SKIP = 0
VERBOSE = False


def test(name, fn):
    global PASS, FAIL
    try:
        err = fn()
        if err:
            print(f"  FAIL  {name}")
            print(f"        {err}")
            FAIL += 1
        else:
            if VERBOSE:
                print(f"  OK    {name}")
            PASS += 1
    except Exception as e:
        print(f"  FAIL  {name}")
        print(f"        Exception: {type(e).__name__}: {e}")
        FAIL += 1


def skip(name, reason=""):
    global SKIP
    print(f"  SKIP  {name}{f' ({reason})' if reason else ''}")
    SKIP += 1


def assert_eq(actual, expected, label=""):
    if actual != expected:
        return f"{label} got {actual!r}, expected {expected!r}"
    return None


def assert_true(cond, msg=""):
    if not cond:
        return msg or "assertion failed"
    return None


def assert_none(v, label=""):
    if v is not None:
        return f"{label} got {v!r}, expected None"
    return None


def assert_contains(text, substring):
    if substring not in text:
        return f"expected {substring!r} in {text[:100]!r}..."
    return None


def assert_no_surrogates(s):
    for c in s:
        if 0xD800 <= ord(c) <= 0xDFFF:
            return f"found surrogate {ord(c):#x} in string"
    return None


# ── Sample emails ────────────────────────────────────

PLAIN_EMAIL = b"""\
From: alice@example.com
To: bob@example.com
Subject: Hello world
Message-ID: <test-001@example.com>
Date: Mon, 05 Jan 2026 10:00:00 +0000
In-Reply-To: <parent@example.com>
References: <aaa@x.com> <bbb@x.com> <ccc@x.com>

This is the body.
"""

MULTIPART_EMAIL = b"""\
From: alice@example.com
To: bob@example.com
Subject: Multipart test
Message-ID: <multipart-001@example.com>
Date: Tue, 06 Jan 2026 11:00:00 +0000
MIME-Version: 1.0
Content-Type: multipart/alternative; boundary="XYZ"

--XYZ
Content-Type: text/plain; charset=utf-8

Plain text body here.
--XYZ
Content-Type: text/html; charset=utf-8

<html><body>HTML body here.</body></html>
--XYZ--
"""

ATTACHMENT_EMAIL = b"""\
From: alice@example.com
To: bob@example.com
Subject: With attachment
Message-ID: <attach-001@example.com>
Date: Wed, 07 Jan 2026 12:00:00 +0000
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="ABC"

--ABC
Content-Type: text/plain; charset=utf-8

Email body text.
--ABC
Content-Type: text/x-patch
Content-Disposition: attachment; filename="fix.patch"

diff --git a/file b/file
--- a/file
+++ b/file
--ABC--
"""

HTML_ONLY_EMAIL = b"""\
From: alice@example.com
To: bob@example.com
Subject: HTML only
Message-ID: <html-001@example.com>
Date: Thu, 08 Jan 2026 13:00:00 +0000
Content-Type: text/html; charset=utf-8

<html><body>Just HTML</body></html>
"""

GROUP_ADDRESS_EMAIL = b"""\
From: alice@example.com
To: unlisted-recipients:;
Cc: linux-kernel@vger.kernel.org
Subject: Group address test
Message-ID: <group-001@example.com>
Date: Fri, 09 Jan 2026 14:00:00 +0000

Body.
"""

ENCODED_SUBJECT_EMAIL = b"""\
From: alice@example.com
To: bob@example.com
Subject: =?UTF-8?B?VGVzdCBTdWJqZWN0?=
Message-ID: <encoded-001@example.com>
Date: Sat, 10 Jan 2026 15:00:00 +0000

Body.
"""

MISSING_HEADERS_EMAIL = b"""\
From: alice@example.com
Date: Sun, 11 Jan 2026 16:00:00 +0000

Body without subject or message-id.
"""

LATIN1_EMAIL = b"""\
From: alice@example.com
To: bob@example.com
Subject: Latin-1 test
Message-ID: <latin1-001@example.com>
Date: Mon, 12 Jan 2026 17:00:00 +0000
Content-Type: text/plain; charset=iso-8859-1

Caf\xe9 r\xe9sum\xe9
"""

UNKNOWN_CHARSET_EMAIL = b"""\
From: alice@example.com
To: bob@example.com
Subject: Bad charset
Message-ID: <badcharset-001@example.com>
Date: Tue, 13 Jan 2026 18:00:00 +0000
Content-Type: text/plain; charset=foobar-xyz

Body with unknown charset.
"""

MULTI_ATTACH_EMAIL = b"""\
From: alice@example.com
To: bob@example.com
Subject: Multi attachment
Message-ID: <multiatt-001@example.com>
Date: Wed, 14 Jan 2026 19:00:00 +0000
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="DEF"

--DEF
Content-Type: text/plain

Body.
--DEF
Content-Type: text/x-patch
Content-Disposition: attachment; filename="a.patch"

patch a
--DEF
Content-Type: text/x-patch
Content-Disposition: attachment; filename="b.patch"

patch b
--DEF
Content-Type: application/pdf
Content-Disposition: attachment; filename="doc.pdf"

pdf content
--DEF--
"""


# ── Section 2A: parse_email_bytes ───────────────────

def run_parse_email_tests():
    from import_mail import parse_email_bytes

    def test_plain():
        d = parse_email_bytes(PLAIN_EMAIL)
        err = assert_eq(d["message_id"], "test-001@example.com", "message_id")
        if err: return err
        err = assert_eq(d["subject"], "Hello world", "subject")
        if err: return err
        err = assert_eq(d["sender"], "alice@example.com", "sender")
        if err: return err
        assert d["date"] and "2026" in d["date"], f"date should contain 2026, got {d['date']}"
        err = assert_true("This is the body" in d["body_text"], "body_text should contain body")
        if err: return err
        err = assert_eq(d["body_html"], "", "body_html")
        if err: return err
        err = assert_eq(d["attachments"], [], "attachments")
        if err: return err
        h = json.loads(d["headers"])
        err = assert_true("Subject" in h, "headers should have Subject")
        return err

    def test_multipart():
        d = parse_email_bytes(MULTIPART_EMAIL)
        err = assert_true("Plain text body" in d["body_text"], "body_text")
        if err: return err
        err = assert_true("HTML body" in d["body_html"], "body_html")
        if err: return err
        err = assert_eq(d["attachments"], [], "attachments")
        return err

    def test_attachment():
        d = parse_email_bytes(ATTACHMENT_EMAIL)
        err = assert_true("Email body text" in d["body_text"], "body_text")
        if err: return err
        err = assert_eq(len(d["attachments"]), 1, "attachments count")
        if err: return err
        att = d["attachments"][0]
        err = assert_eq(att["filename"], "fix.patch", "filename")
        if err: return err
        err = assert_eq(att["content_type"], "text/x-patch", "content_type")
        if err: return err
        err = assert_true(len(att["content"]) > 0, "attachment content non-empty")
        return err

    def test_html_only():
        d = parse_email_bytes(HTML_ONLY_EMAIL)
        err = assert_eq(d["body_text"], "", "body_text")
        if err: return err
        err = assert_true("Just HTML" in d["body_html"], "body_html")
        return err

    def test_missing_subject():
        d = parse_email_bytes(MISSING_HEADERS_EMAIL)
        err = assert_eq(d["subject"], "", "subject should be empty")
        if err: return err
        err = assert_eq(d["message_id"], "", "message_id should be empty")
        return err

    def test_group_address():
        # This should not raise AttributeError with compat32 policy
        d = parse_email_bytes(GROUP_ADDRESS_EMAIL)
        err = assert_true("unlisted-recipients" in d["headers"], "headers should contain group address")
        return err

    def test_encoded_subject():
        d = parse_email_bytes(ENCODED_SUBJECT_EMAIL)
        # compat32 policy returns raw encoded subject; the encoded string
        # should be present and the email should parse without error
        err = assert_true(len(d["subject"]) > 0, "subject not empty")
        if err: return err
        return assert_no_surrogates(d["subject"])

    def test_references():
        d = parse_email_bytes(PLAIN_EMAIL)
        refs = json.loads(d["references_ids"])
        err = assert_eq(refs, ["aaa@x.com", "bbb@x.com", "ccc@x.com"], "references")
        return err

    def test_in_reply_to():
        d = parse_email_bytes(PLAIN_EMAIL)
        err = assert_eq(d["in_reply_to"], "parent@example.com", "in_reply_to")
        return err

    def test_multi_attachments():
        d = parse_email_bytes(MULTI_ATTACH_EMAIL)
        err = assert_eq(len(d["attachments"]), 3, "attachments count")
        return err

    def test_latin1_charset():
        d = parse_email_bytes(LATIN1_EMAIL)
        err = assert_true("caf" in d["body_text"].lower(), "latin-1 body decoded")
        return err

    def test_unknown_charset():
        d = parse_email_bytes(UNKNOWN_CHARSET_EMAIL)
        # Should not crash, body should be decoded with fallback
        err = assert_true(len(d["body_text"]) > 0, "body decoded with fallback")
        return err

    def test_no_surrogates_in_output():
        d = parse_email_bytes(PLAIN_EMAIL)
        for key in ["subject", "sender", "body_text", "body_html", "message_id"]:
            err = assert_no_surrogates(d[key])
            if err:
                return f"{key}: {err}"
        return None

    print("\n── 1. import_mail.parse_email_bytes ──")
    test("Plain text email", test_plain)
    test("Multipart with text+HTML", test_multipart)
    test("Multipart with attachment", test_attachment)
    test("HTML-only email", test_html_only)
    test("Missing Subject/Message-ID", test_missing_subject)
    test("RFC 5322 Group address in To", test_group_address)
    test("Encoded subject (RFC 2047)", test_encoded_subject)
    test("References header parsing", test_references)
    test("In-Reply-To angle brackets", test_in_reply_to)
    test("Multiple attachments", test_multi_attachments)
    test("Latin-1 charset", test_latin1_charset)
    test("Unknown charset fallback", test_unknown_charset)
    test("No surrogate characters in output", test_no_surrogates_in_output)


# ── Section 2B: fix_date ────────────────────────────

def run_fix_date_tests():
    from import_mail import fix_date
    from datetime import datetime

    def test_y2k_0100():
        return assert_eq(fix_date("0100-03-15T10:00:00+00:00"), "2000-03-15T10:00:00+00:00")

    def test_y2k_0104():
        return assert_eq(fix_date("0104-06-20T12:00:00+00:00"), "2004-06-20T12:00:00+00:00")

    def test_off_by_100_1903():
        return assert_eq(fix_date("1903-01-01T00:00:00+00:00"), "2003-01-01T00:00:00+00:00")

    def test_off_by_100_1904():
        return assert_eq(fix_date("1904-12-31T23:59:59+00:00"), "2004-12-31T23:59:59+00:00")

    def test_epoch():
        return assert_none(fix_date("1970-01-01T00:00:00+00:00"))

    def test_before_1990():
        return assert_none(fix_date("1985-06-15T10:00:00+00:00"))

    def test_valid_modern():
        return assert_eq(fix_date("2026-01-05T10:00:00+00:00"), "2026-01-05T10:00:00+00:00")

    def test_future():
        return assert_none(fix_date("2099-01-01T00:00:00+00:00"))

    def test_none():
        return assert_none(fix_date(None))

    def test_empty():
        return assert_none(fix_date(""))

    def test_next_year_valid():
        next_year = str(datetime.now().year + 1)
        d = f"{next_year}-06-15T10:00:00+00:00"
        return assert_eq(fix_date(d), d)

    def test_1905_not_corrected():
        # 1905 is NOT in the off-by-100 fix list
        return assert_none(fix_date("1905-01-01T00:00:00+00:00"))

    print("\n── 2. import_mail.fix_date ──")
    test("Y2K 0100→2000", test_y2k_0100)
    test("Y2K 0104→2004", test_y2k_0104)
    test("Off-by-100 1903→2003", test_off_by_100_1903)
    test("Off-by-100 1904→2004", test_off_by_100_1904)
    test("Epoch date 1970→None", test_epoch)
    test("Before 1990→None", test_before_1990)
    test("Valid modern date unchanged", test_valid_modern)
    test("Future date→None", test_future)
    test("None input→None", test_none)
    test("Empty string→None", test_empty)
    test("Next year is valid", test_next_year_valid)
    test("1905 not corrected (pre-1990→None)", test_1905_not_corrected)


# ── Section 2C: _strip_surrogates ───────────────────

def run_strip_surrogates_tests():
    from import_mail import _strip_surrogates

    def test_lone_surrogate():
        return assert_eq(_strip_surrogates("hello\ud800world"), "helloworld")

    def test_high_surrogate():
        return assert_eq(_strip_surrogates("test\udbffend"), "testend")

    def test_low_surrogate():
        return assert_eq(_strip_surrogates("test\udc00end"), "testend")

    def test_clean():
        return assert_eq(_strip_surrogates("no surrogates here"), "no surrogates here")

    def test_empty():
        return assert_eq(_strip_surrogates(""), "")

    def test_multiple():
        return assert_eq(_strip_surrogates("\ud800\udc00\ud801"), "")

    def test_mixed_unicode():
        r = _strip_surrogates("hello \u2603 \ud800 world")
        return assert_eq(r, "hello \u2603  world")

    print("\n── 3. import_mail._strip_surrogates ──")
    test("Remove lone surrogate", test_lone_surrogate)
    test("Remove high surrogate", test_high_surrogate)
    test("Remove low surrogate", test_low_surrogate)
    test("Clean string unchanged", test_clean)
    test("Empty string", test_empty)
    test("Multiple surrogates", test_multiple)
    test("Mixed valid unicode + surrogates", test_mixed_unicode)


# ── Section 2D: _parse_patch_subject ────────────────

def run_parse_patch_tests():
    from server.app import _parse_patch_subject

    def test_simple():
        return assert_eq(_parse_patch_subject("[PATCH 1/3] Fix leak"), (1, 1, 3))

    def test_v2():
        return assert_eq(_parse_patch_subject("[PATCH v2 3/5] Add handling"), (2, 3, 5))

    def test_tagged():
        return assert_eq(_parse_patch_subject("[PATCH v3 net-next 2/10] Refactor"), (3, 2, 10))

    def test_cover():
        return assert_eq(_parse_patch_subject("[PATCH 0/5] This series"), (1, 0, 5))

    def test_non_patch():
        return assert_none(_parse_patch_subject("Re: Fix memory leak"))

    def test_empty():
        return assert_none(_parse_patch_subject(""))

    def test_none():
        return assert_none(_parse_patch_subject(None))

    def test_high_version():
        return assert_eq(_parse_patch_subject("[PATCH v10 15/20] Big series"), (10, 15, 20))

    def test_single():
        return assert_eq(_parse_patch_subject("[PATCH 1/1] Single fix"), (1, 1, 1))

    print("\n── 4. server._parse_patch_subject ──")
    test("[PATCH 1/3]", test_simple)
    test("[PATCH v2 3/5]", test_v2)
    test("[PATCH v3 net-next 2/10]", test_tagged)
    test("[PATCH 0/5] cover letter", test_cover)
    test("Non-patch subject", test_non_patch)
    test("Empty subject", test_empty)
    test("None subject", test_none)
    test("[PATCH v10 15/20]", test_high_version)
    test("[PATCH 1/1] single", test_single)


# ── Section 2E: _extract_trailers ───────────────────

def run_extract_trailers_tests():
    from server.app import _extract_trailers

    def test_single():
        body = "Some text\nReviewed-by: Foo Bar <foo@x.com>\n"
        t = _extract_trailers(body)
        return assert_eq(len(t), 1) or assert_true("Reviewed-by" in t[0])

    def test_multiple():
        body = "Some text\nReviewed-by: A <a@x.com>\nAcked-by: B <b@x.com>\nTested-by: C <c@x.com>\n"
        return assert_eq(len(_extract_trailers(body)), 3)

    def test_none_found():
        return assert_eq(_extract_trailers("Just text, no trailers"), [])

    def test_empty():
        return assert_eq(_extract_trailers(""), [])

    def test_reported_suggested():
        body = "Reported-by: R <r@x.com>\nSuggested-by: S <s@x.com>\n"
        return assert_eq(len(_extract_trailers(body)), 2)

    def test_co_developed():
        body = "Co-developed-by: Dev <dev@x.com>\n"
        return assert_eq(len(_extract_trailers(body)), 1)

    def test_sob_not_extracted():
        body = "Signed-off-by: Author <author@x.com>\n"
        return assert_eq(len(_extract_trailers(body)), 0)

    print("\n── 5. server._extract_trailers ──")
    test("Single Reviewed-by", test_single)
    test("Multiple trailer types", test_multiple)
    test("No trailers", test_none_found)
    test("Empty body", test_empty)
    test("Reported-by + Suggested-by", test_reported_suggested)
    test("Co-developed-by", test_co_developed)
    test("Signed-off-by NOT extracted", test_sob_not_extracted)


# ── Section 2F: _inject_trailers ────────────────────

def run_inject_trailers_tests():
    from server.app import _inject_trailers

    def test_before_separator():
        raw = "Subject: Patch\n\nBody text\n---\ndiff --git a/file b/file\n"
        result = _inject_trailers(raw, ["Reviewed-by: Foo <foo@x.com>"])
        idx = result.find("Reviewed-by")
        sep = result.find("\n---\n")
        if idx < 0 or sep < 0 or idx > sep:
            return f"trailer not before ---: trailer at {idx}, --- at {sep}"
        return None

    def test_after_existing():
        raw = "Subject: Patch\n\nBody\nSigned-off-by: A <a@x.com>\n---\ndiff\n"
        result = _inject_trailers(raw, ["Reviewed-by: B <b@x.com>"])
        sob = result.find("Signed-off-by")
        rvb = result.find("Reviewed-by")
        sep = result.find("\n---\n")
        if not (sob < rvb < sep):
            return f"order wrong: SOB={sob} RVB={rvb} ---={sep}"
        return None

    def test_no_separator():
        raw = "Subject: Patch\n\nBody text\n"
        result = _inject_trailers(raw, ["Reviewed-by: X <x@x.com>"])
        return assert_eq(result, raw)

    def test_empty_trailers():
        raw = "Subject: Patch\n\nBody\n---\ndiff\n"
        result = _inject_trailers(raw, [])
        return assert_eq(result, raw)

    def test_multiple_inject():
        raw = "Subject: Patch\n\nBody\n---\ndiff\n"
        result = _inject_trailers(raw, ["Reviewed-by: A <a@x.com>", "Acked-by: B <b@x.com>"])
        err = assert_true("Reviewed-by" in result, "has Reviewed-by")
        if err: return err
        err = assert_true("Acked-by" in result, "has Acked-by")
        return err

    print("\n── 6. server._inject_trailers ──")
    test("Inject before --- separator", test_before_separator)
    test("Inject after existing trailers", test_after_existing)
    test("No --- separator unchanged", test_no_separator)
    test("Empty trailers unchanged", test_empty_trailers)
    test("Multiple trailers injected", test_multiple_inject)


# ── Section 2G: _sanitize_filename ──────────────────

def run_sanitize_filename_tests():
    from server.app import _sanitize_filename

    def test_normal():
        return assert_eq(_sanitize_filename("Fix memory leak in parser"), "Fix-memory-leak-in-parser")

    def test_patch_prefix():
        return assert_eq(_sanitize_filename("[PATCH v2 3/5] Add feature"), "Add-feature")

    def test_special_chars():
        r = _sanitize_filename("Fix: crash in <widget> (issue #42)")
        return assert_true("<" not in r and ">" not in r and "#" not in r, "special chars removed")

    def test_long():
        long = "A" * 120
        r = _sanitize_filename(long)
        return assert_true(len(r) <= 80, f"should be <=80 chars, got {len(r)}")

    def test_empty_after_sanitize():
        return assert_eq(_sanitize_filename("///:::"), "patch")

    def test_unicode():
        r = _sanitize_filename("Fix unicode handling \u00e9")
        return assert_true(len(r) > 0, "should not be empty")

    print("\n── 7. server._sanitize_filename ──")
    test("Normal subject", test_normal)
    test("Remove [PATCH] prefix", test_patch_prefix)
    test("Special characters removed", test_special_chars)
    test("Truncated to 80 chars", test_long)
    test("Empty after sanitize→'patch'", test_empty_after_sanitize)
    test("Unicode subject", test_unicode)


# ── Section 2H: cache_get/cache_set ─────────────────

def run_cache_tests():
    from server.app import cache_get, cache_set, _cache

    def test_basic():
        _cache.clear()
        cache_set("k1", "v1")
        return assert_eq(cache_get("k1"), "v1")

    def test_miss():
        _cache.clear()
        return assert_none(cache_get("nonexistent"))

    def test_expired():
        _cache.clear()
        _cache["k2"] = (time.monotonic() - 400, "v2")
        return assert_none(cache_get("k2"))

    def test_overwrite():
        _cache.clear()
        cache_set("k3", "v1")
        cache_set("k3", "v2")
        return assert_eq(cache_get("k3"), "v2")

    def test_non_string():
        _cache.clear()
        cache_set("k4", {"dict": True})
        return assert_eq(cache_get("k4"), {"dict": True})

    print("\n── 8. server.cache_get/cache_set ──")
    test("Basic set and get", test_basic)
    test("Miss returns None", test_miss)
    test("Expired entry returns None", test_expired)
    test("Overwrite existing key", test_overwrite)
    test("Non-string values", test_non_string)


# ── Section 2I: database.init_db/get_connection ─────

def run_database_tests():
    from database import init_db, get_connection

    def test_init_creates_tables():
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        try:
            conn = init_db(path)
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            conn.close()
            for t in ["messages", "attachments", "import_progress", "messages_fts", "schema_version"]:
                if t not in tables:
                    return f"missing table {t}"
            return None
        finally:
            os.unlink(path)

    def test_schema_version():
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        try:
            conn = init_db(path)
            v = conn.execute("SELECT version FROM schema_version").fetchone()[0]
            conn.close()
            return assert_eq(v, 2, "schema version")
        finally:
            os.unlink(path)

    def test_pragmas():
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        try:
            conn = get_connection(path)
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
            conn.close()
            err = assert_eq(mode, "wal", "journal_mode")
            if err: return err
            return assert_eq(fk, 1, "foreign_keys")
        finally:
            os.unlink(path)

    def test_row_factory():
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        try:
            conn = get_connection(path)
            row = conn.execute("SELECT 42 as x").fetchone()
            conn.close()
            return assert_eq(row["x"], 42, "row access by name")
        finally:
            os.unlink(path)

    def test_idempotent():
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        try:
            conn1 = init_db(path)
            conn1.close()
            conn2 = init_db(path)
            tables = [r[0] for r in conn2.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            conn2.close()
            return assert_true("messages" in tables)
        finally:
            os.unlink(path)

    def test_fts_works():
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        try:
            conn = init_db(path)
            conn.execute("""INSERT INTO messages (message_id, subject, sender, date, epoch)
                           VALUES ('<test@x.com>', 'Test subject', 'me@x.com', '2026-01-01T00:00:00+00:00', 0)""")
            conn.commit()
            r = conn.execute(
                "SELECT COUNT(*) FROM messages_fts WHERE messages_fts MATCH 'Test'").fetchone()
            conn.close()
            return assert_eq(r[0], 1, "FTS match count")
        finally:
            os.unlink(path)

    print("\n── 9. database.init_db/get_connection ──")
    test("init_db creates all tables", test_init_creates_tables)
    test("Schema version recorded", test_schema_version)
    test("get_connection sets pragmas", test_pragmas)
    test("Row factory allows name access", test_row_factory)
    test("init_db is idempotent", test_idempotent)
    test("FTS5 virtual table works", test_fts_works)


# ── Main ────────────────────────────────────────────

def main():
    global VERBOSE

    parser = argparse.ArgumentParser(description="lore-mirror unit tests")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    VERBOSE = args.verbose

    print("=" * 60)
    print("  lore-mirror unit tests")
    print("=" * 60)

    run_parse_email_tests()
    run_fix_date_tests()
    run_strip_surrogates_tests()
    run_parse_patch_tests()
    run_extract_trailers_tests()
    run_inject_trailers_tests()
    run_sanitize_filename_tests()
    run_cache_tests()
    run_database_tests()

    total = PASS + FAIL + SKIP
    print(f"\n{'=' * 60}")
    print(f"  Results: {PASS} passed, {FAIL} failed, {SKIP} skipped  ({total} total)")
    print(f"{'=' * 60}")

    sys.exit(1 if FAIL else 0)


import argparse

if __name__ == "__main__":
    main()
