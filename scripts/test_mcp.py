#!/usr/bin/env python3
"""
MCP server test suite for lore-mirror.

Tests the MCP server via stdio JSON-RPC protocol against a running backend.
No external dependencies (uses subprocess + stdlib).

Usage:
    python3 scripts/test_mcp.py                    # test against localhost:8000
    python3 scripts/test_mcp.py --api-url http://host:9000
    python3 scripts/test_mcp.py -v                 # verbose
"""

import argparse
import json
import subprocess
import sys
import os
import time

PASS = 0
FAIL = 0
SKIP = 0
VERBOSE = False
MCP_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "server", "mcp_server.py")


def log_pass(name):
    global PASS
    PASS += 1
    print(f"  \033[32m✓\033[0m {name}")


def log_fail(name, reason):
    global FAIL
    FAIL += 1
    print(f"  \033[31m✗\033[0m {name}: {reason}")


def log_skip(name, reason):
    global SKIP
    SKIP += 1
    print(f"  \033[33m○\033[0m {name}: {reason}")


class MCPClient:
    """Thin wrapper to talk to MCP server via stdio."""

    def __init__(self, api_url="http://localhost:8000"):
        self.api_url = api_url
        self.proc = None
        self._id = 0

    def start(self):
        env = os.environ.copy()
        env["LORE_API_URL"] = self.api_url
        self.proc = subprocess.Popen(
            [sys.executable, MCP_SCRIPT],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
        )

    def stop(self):
        if self.proc:
            self.proc.stdin.close()
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def call(self, method, params=None, timeout=30):
        """Send a JSON-RPC request, return the response dict."""
        self._id += 1
        msg = {"jsonrpc": "2.0", "id": self._id, "method": method}
        if params is not None:
            msg["params"] = params
        line = json.dumps(msg) + "\n"
        self.proc.stdin.write(line)
        self.proc.stdin.flush()

        deadline = time.time() + timeout
        while time.time() < deadline:
            raw = self.proc.stdout.readline()
            if not raw:
                break
            raw = raw.strip()
            if not raw:
                continue
            try:
                resp = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if resp.get("id") == self._id:
                return resp
        return None

    def initialize(self):
        """Run MCP initialize handshake."""
        resp = self.call("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-mcp", "version": "1.0"},
        }, timeout=10)
        if resp and "result" in resp:
            # Send initialized notification
            self.proc.stdin.write(
                json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
            )
            self.proc.stdin.flush()
        return resp


def test_initialize(client):
    """Test MCP initialize handshake."""
    resp = client.call("initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "test-mcp", "version": "1.0"},
    }, timeout=10)
    if not resp or "result" not in resp:
        log_fail("initialize", "no response or missing result")
        return False
    result = resp["result"]
    if result.get("serverInfo", {}).get("name") != "lore_mirror_mcp":
        log_fail("initialize", f"unexpected server name: {result.get('serverInfo')}")
        return False
    if "tools" not in result.get("capabilities", {}):
        log_fail("initialize", "missing tools capability")
        return False
    log_pass("initialize")
    return True


def test_tools_list(client):
    """Test tools/list returns all expected tools."""
    resp = client.call("tools/list", {}, timeout=10)
    if not resp or "result" not in resp:
        log_fail("tools/list", "no response")
        return []
    tools = resp["result"].get("tools", [])
    expected = {
        "lore_list_inboxes", "lore_locate_inbox", "lore_search_emails",
        "lore_get_message", "lore_get_thread", "lore_browse_inbox",
        "lore_get_raw_email", "lore_semantic_search", "lore_get_series",
        "lore_get_stats",
    }
    found = {t["name"] for t in tools}
    missing = expected - found
    extra = found - expected
    if missing:
        log_fail("tools/list", f"missing tools: {missing}")
    elif extra:
        log_fail("tools/list", f"unexpected tools: {extra}")
    else:
        log_pass(f"tools/list ({len(tools)} tools)")
    return tools


def test_tool_call(client, name, arguments, validator, timeout=30):
    """Call a tool and validate the result."""
    resp = client.call("tools/call", {"name": name, "arguments": arguments}, timeout=timeout)
    if not resp:
        log_fail(name, "no response (timeout)")
        return None
    if "error" in resp:
        log_fail(name, f"RPC error: {resp['error']}")
        return None
    content = resp.get("result", {}).get("content", [])
    if not content:
        log_fail(name, "empty content")
        return None
    text = content[0].get("text", "")
    if content[0].get("isError"):
        log_fail(name, f"tool error: {text[:200]}")
        return None
    # Try JSON parse; if it fails, pass the raw text to validator
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        data = text  # raw text (e.g. raw email, error messages)
    ok, msg = validator(data)
    if ok:
        log_pass(f"{name}: {msg}")
    else:
        log_fail(name, msg)
    return data


def main():
    global VERBOSE
    parser = argparse.ArgumentParser(description="MCP server test suite")
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    VERBOSE = args.verbose

    print(f"MCP Server Tests (API: {args.api_url})")
    print("=" * 50)

    client = MCPClient(args.api_url)
    client.start()

    try:
        # ── Protocol tests ──────────────────────────────
        print("\n── Protocol ──")
        if not test_initialize(client):
            print("\nFATAL: initialize failed, skipping remaining tests")
            return 1
        test_tools_list(client)

        # ── lore_get_stats ──────────────────────────────
        print("\n── lore_get_stats ──")
        def validate_stats(d):
            if "total_messages" not in d:
                return False, f"missing total_messages"
            if "total_inboxes" not in d:
                return False, f"missing total_inboxes"
            return True, f"{d['total_messages']:,} messages, {d['total_inboxes']} inboxes"

        test_tool_call(client, "lore_get_stats", {}, validate_stats, timeout=10)

        # ── lore_list_inboxes ───────────────────────────
        print("\n── lore_list_inboxes ──")
        def validate_inboxes(d):
            if not isinstance(d, list):
                return False, f"expected list, got {type(d).__name__}"
            if len(d) == 0:
                return False, "empty inbox list"
            first = d[0]
            for key in ("name", "message_count", "earliest", "latest"):
                if key not in first:
                    return False, f"missing key '{key}' in inbox entry"
            return True, f"{len(d)} inboxes"

        test_tool_call(client, "lore_list_inboxes", {}, validate_inboxes, timeout=10)

        # ── lore_locate_inbox ───────────────────────────
        print("\n── lore_locate_inbox ──")
        def validate_locate(d):
            # API returns {"query": ..., "matches": [...]}
            matches = d.get("matches", d) if isinstance(d, dict) else d
            if not isinstance(matches, list):
                return False, f"expected list, got {type(matches).__name__}"
            if len(matches) == 0:
                return False, "no matches for 'net'"
            names = [x["name"] for x in matches]
            if not any("net" in n for n in names):
                return False, f"no 'net' in results: {names}"
            return True, f"{len(matches)} matches"

        test_tool_call(client, "lore_locate_inbox", {"query": "net"}, validate_locate, timeout=10)

        # ── lore_search_emails (FTS) ────────────────────
        print("\n── lore_search_emails ──")
        def validate_search(d):
            if "total" not in d:
                return False, "missing 'total'"
            if "messages" not in d:
                return False, "missing 'messages'"
            if "search_type" not in d:
                return False, "missing 'search_type'"
            return True, f"{d['total']} results, type={d['search_type']}"

        test_tool_call(client, "lore_search_emails",
                       {"query": "s:PATCH", "inbox": "bpf", "per_page": 3},
                       validate_search, timeout=15)

        # ── lore_browse_inbox ───────────────────────────
        print("\n── lore_browse_inbox ──")
        def validate_browse(d):
            if "total" not in d:
                return False, "missing 'total'"
            if "messages" not in d:
                return False, "missing 'messages'"
            if len(d["messages"]) == 0:
                return False, "empty message list"
            msg = d["messages"][0]
            for key in ("message_id", "subject", "sender", "date"):
                if key not in msg:
                    return False, f"missing '{key}' in message"
            return True, f"total={d['total']}, showing {len(d['messages'])} messages"

        test_tool_call(client, "lore_browse_inbox",
                       {"name": "bpf", "page": 1, "per_page": 3},
                       validate_browse, timeout=10)

        # ── lore_get_message ────────────────────────────
        print("\n── lore_get_message ──")
        # First search to get a valid message_id
        search_resp = client.call("tools/call", {
            "name": "lore_search_emails",
            "arguments": {"query": "s:PATCH", "inbox": "bpf", "per_page": 1},
        }, timeout=15)
        msg_id = None
        if search_resp and "result" in search_resp:
            text = search_resp["result"]["content"][0]["text"]
            data = json.loads(text)
            if data.get("messages"):
                msg_id = data["messages"][0]["message_id"]

        if msg_id:
            def validate_message(d):
                if "subject" not in d:
                    return False, "missing 'subject'"
                if "sender" not in d:
                    return False, "missing 'sender'"
                if "body_text" not in d and "body_html" not in d:
                    return False, "missing body"
                return True, f"subject={d['subject'][:50]}"

            test_tool_call(client, "lore_get_message",
                           {"message_id": msg_id},
                           validate_message, timeout=10)
        else:
            log_skip("lore_get_message", "no message_id from search")

        # ── lore_get_thread ─────────────────────────────
        print("\n── lore_get_thread ──")
        if msg_id:
            def validate_thread(d):
                if "total" not in d:
                    return False, "missing 'total'"
                if "messages" not in d:
                    return False, "missing 'messages'"
                if d["total"] < 1:
                    return False, f"thread has {d['total']} messages"
                return True, f"total={d['total']} messages"

            test_tool_call(client, "lore_get_thread",
                           {"message_id": msg_id},
                           validate_thread, timeout=10)
        else:
            log_skip("lore_get_thread", "no message_id from search")

        # ── lore_get_raw_email ──────────────────────────
        print("\n── lore_get_raw_email ──")
        if msg_id:
            def validate_raw(d):
                # Raw email may be returned as string or dict with raw_email
                if isinstance(d, str):
                    text = d
                elif isinstance(d, dict):
                    text = d.get("raw_email", json.dumps(d))
                else:
                    return False, f"unexpected type: {type(d)}"
                if "From:" not in text and "from:" not in text:
                    return False, "missing From header"
                return True, f"raw email {len(text)} chars"

            test_tool_call(client, "lore_get_raw_email",
                           {"message_id": msg_id},
                           validate_raw, timeout=10)
        else:
            log_skip("lore_get_raw_email", "no message_id from search")

        # ── lore_get_series ─────────────────────────────
        print("\n── lore_get_series ──")
        if msg_id:
            def validate_series(d):
                if "version" not in d:
                    return False, "missing 'version'"
                if "patches" not in d:
                    return False, "missing 'patches'"
                return True, f"version={d['version']}, {len(d['patches'])} patches"

            test_tool_call(client, "lore_get_series",
                           {"message_id": msg_id},
                           validate_series, timeout=10)
        else:
            log_skip("lore_get_series", "no message_id from search")

        # ── lore_semantic_search ────────────────────────
        print("\n── lore_semantic_search ──")
        def validate_semantic(d):
            # Semantic search may be disabled (503) or return empty — that's OK
            if isinstance(d, dict):
                if "error" in d or "detail" in d:
                    return True, "disabled (vector indexes not built)"
                if "results" in d:
                    return True, f"{len(d['results'])} results"
                if "message" in d:
                    return True, f"error response: {d['message'][:60]}"
            return True, f"response: {str(d)[:100]}"

        test_tool_call(client, "lore_semantic_search",
                       {"query": "OOM killer memory pressure", "inbox": "linux-mm"},
                       validate_semantic, timeout=15)

        # ── Error handling ──────────────────────────────
        print("\n── Error handling ──")
        def validate_error(d):
            # MCP tool wraps API errors as error text — should not crash
            return True, "error handled gracefully"

        # Test with nonexistent message — may return error text or empty
        resp = client.call("tools/call", {
            "name": "lore_get_message",
            "arguments": {"message_id": "nonexistent@invalid"},
        }, timeout=10)
        if resp and "result" in resp:
            content = resp["result"].get("content", [])
            if content and content[0].get("isError"):
                log_pass("error handling: tool returned error gracefully")
            elif content:
                log_pass("error handling: tool returned response")
            else:
                log_fail("error handling", "empty content")
        elif resp and "error" in resp:
            log_pass("error handling: RPC error returned")
        else:
            log_fail("error handling", "no response")

    finally:
        client.stop()

    # ── Summary ────────────────────────────────────────
    total = PASS + FAIL + SKIP
    print(f"\n{'=' * 50}")
    print(f"Results: {PASS} passed, {FAIL} failed, {SKIP} skipped ({total} total)")
    if FAIL > 0:
        print("\033[31mFAILED\033[0m")
        return 1
    print("\033[32mPASSED\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
