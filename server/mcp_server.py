#!/usr/bin/env python3
"""
MCP server for lore-mirror — exposes kernel mailing list search tools.

Wraps the local REST API (FastAPI on :8000) via httpx.
Spawned by Claude Code via .mcp.json using stdio transport.
"""

import json
import os
from typing import Optional

import httpx
from mcp.server.fastmcp import FastMCP

API_BASE = os.environ.get("LORE_API_URL", "http://localhost:8000")

mcp = FastMCP(
    "lore_mirror_mcp",
    instructions=(
        "Search and browse Linux kernel mailing list archives "
        "(lore.kernel.org mirror). Use search_emails with prefix syntax "
        "for targeted queries: s: (subject), f: (from), d: (date range), "
        "b: (body), t: (to), c: (cc)."
    ),
)


async def _api_get(path: str, params: Optional[dict] = None, timeout: float = 30.0) -> dict | str:
    """Shared helper for GET requests to the REST API."""
    async with httpx.AsyncClient(base_url=API_BASE, timeout=timeout) as client:
        r = await client.get(path, params=params)
        r.raise_for_status()
        content_type = r.headers.get("content-type", "")
        if "application/json" in content_type:
            return r.json()
        return r.text


def _handle_error(e: Exception) -> str:
    """Format errors into actionable messages."""
    if isinstance(e, httpx.HTTPStatusError):
        status = e.response.status_code
        if status == 404:
            return "Error: Not found. Check the message ID or inbox name."
        if status == 422:
            return f"Error: Invalid parameters. {e.response.text}"
        return f"Error: API returned status {status}."
    if isinstance(e, httpx.ConnectError):
        return f"Error: Cannot connect to lore-mirror API at {API_BASE}. Is the server running?"
    if isinstance(e, httpx.TimeoutException):
        return "Error: Request timed out. Try a narrower search."
    return f"Error: {type(e).__name__}: {e}"


# ── Tools ───────────────────────────────────────────


@mcp.tool(
    name="lore_list_inboxes",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def list_inboxes() -> str:
    """List all available kernel mailing list inboxes with message counts and date ranges.

    Returns JSON array of inboxes sorted by most recently active.
    Each entry has: name, description, message_count, earliest, latest.
    """
    try:
        data = await _api_get("/api/inboxes")
        return json.dumps(data, indent=2)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="lore_locate_inbox",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def locate_inbox(query: str) -> str:
    """Find mailing list inboxes by name or description keyword.

    Use this when you don't know the exact inbox name. For example:
    query="net" finds netdev, linux-netfilter, etc.
    query="memory" finds linux-mm, etc.

    Args:
        query: Keyword to match against inbox names and descriptions.

    Returns JSON with matching inbox names and descriptions.
    """
    try:
        data = await _api_get("/api/locate", params={"q": query})
        return json.dumps(data, indent=2)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="lore_search_emails",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def search_emails(
    query: str,
    inbox: str = "",
    page: int = 1,
    per_page: int = 20,
) -> str:
    """Search kernel mailing list emails with lore-compatible prefix syntax.

    Prefix syntax (combinable):
      s:keyword   - subject contains keyword
      f:name      - from/sender contains name
      b:keyword   - body contains keyword
      d:YYYY-MM-DD..YYYY-MM-DD - date range (either side optional)
      t:addr      - to field
      c:addr      - cc field
      a:addr      - any address field (from/to/cc)
      bs:keyword  - subject + body
      tc:addr     - to + cc
      m:msgid     - exact Message-ID lookup

    Examples:
      "s:PATCH f:torvalds" - patches from Torvalds
      "s:mm f:akpm d:2026-01-01..2026-03-01" - memory patches by akpm in date range
      "b:use-after-free" - body mentions use-after-free

    Args:
        query: Search query with optional prefix syntax.
        inbox: Limit search to a specific inbox (e.g. "linux-kernel"). Empty = all inboxes.
        page: Page number (1-based).
        per_page: Results per page (default 20, max 200).

    Returns JSON with total count, pagination info, and message list.
    Each message has: message_id, subject, sender, date, inbox_name, snippet.
    """
    try:
        params: dict = {"q": query, "page": page, "per_page": per_page}
        if inbox:
            params["inbox"] = inbox
        data = await _api_get("/api/search", params=params)
        return json.dumps(data, indent=2)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="lore_get_message",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def get_message(message_id: str) -> str:
    """Get a single email message by its Message-ID.

    Returns full message content including subject, sender, date, body,
    headers, references, and attachment metadata.
    Does NOT include raw_email — use lore_get_raw_email for that.

    Args:
        message_id: The email Message-ID (e.g. "20260101120000.12345-1-user@example.com").
    """
    try:
        data = await _api_get(f"/api/messages/{message_id}")
        return json.dumps(data, indent=2)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="lore_get_thread",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def get_thread(message_id: str) -> str:
    """Get the full discussion thread containing a message.

    Returns a tree of messages (root + all replies) for the thread that
    contains the given Message-ID.

    Args:
        message_id: Any Message-ID in the thread.
    """
    try:
        data = await _api_get(f"/api/threads/{message_id}")
        return json.dumps(data, indent=2)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="lore_browse_inbox",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def browse_inbox(
    name: str,
    page: int = 1,
    per_page: int = 20,
    after: str = "",
) -> str:
    """Browse messages in an inbox, newest first.

    Supports keyset pagination via `after` cursor for efficient deep pages.
    Use the `next_cursor` value from a previous response as the `after` param.

    Args:
        name: Inbox name (e.g. "linux-kernel", "netdev").
        page: Page number (1-based, used when `after` is empty).
        per_page: Results per page (default 20, max 200).
        after: Keyset cursor from previous page's next_cursor (overrides page).

    Returns JSON with inbox info, total count, pagination, and message list.
    """
    try:
        params: dict = {"page": page, "per_page": per_page}
        if after:
            params["after"] = after
        data = await _api_get(f"/api/inboxes/{name}", params=params)
        return json.dumps(data, indent=2)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="lore_get_raw_email",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def get_raw_email(message_id: str) -> str:
    """Get the raw RFC 2822 email text for a message.

    Use this when you need the original email headers, MIME structure,
    or exact formatting. For parsed content, use lore_get_message instead.

    Args:
        message_id: The email Message-ID.
    """
    try:
        data = await _api_get("/api/raw", params={"id": message_id})
        return data if isinstance(data, str) else json.dumps(data)
    except Exception as e:
        return _handle_error(e)


if __name__ == "__main__":
    mcp.run()
