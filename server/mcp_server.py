#!/usr/bin/env python3
"""
MCP server for lore-mirror — exposes kernel mailing list search tools.

Wraps the local REST API via httpx. API URL configured via LORE_API_URL env var (default: http://localhost:8000).
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
        "(lore.kernel.org mirror).\n\n"
        "Workflow: (1) ALWAYS start with lore_list_inboxes or lore_locate_inbox "
        "to discover available mailing lists. (2) Use lore_search_emails with "
        "prefix syntax for targeted queries: s: (subject), f: (from), "
        "d: (date range), b: (body), t: (to), c: (cc), a: (any address). "
        "Always specify inbox= for better results. (3) If FTS returns 0 results, "
        "semantic fallback activates automatically. For explicit semantic search, "
        "use lore_semantic_search. (4) Use lore_get_thread to read full discussions, "
        "lore_get_series for patch series metadata."
    ),
)


async def _api_get(path: str, params: Optional[dict] = None, timeout: float = 60.0) -> dict | str:
    """Shared helper for GET requests to the REST API."""
    async with httpx.AsyncClient(base_url=API_BASE, timeout=timeout) as client:
        r = await client.get(path, params=params, headers={"X-Source": "mcp"})
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

    IMPORTANT: Always call this FIRST before searching to discover which
    mailing lists are available and what topics each covers. Not all ~200
    lore.kernel.org lists are mirrored.

    Each inbox has a description field listing topics and keywords.
    Use it to pick the right inbox for your query.

    Returns JSON array sorted by most recently active.
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

    IMPORTANT: Always specify the inbox parameter for better performance and
    precision. Use lore_list_inboxes or lore_locate_inbox first to find the
    right inbox. Omit inbox only for cross-inbox search.

    Prefix syntax (combinable — combine freely):
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

    Operators: AND (default), OR, NOT, "exact phrase", prefix*
    Paste a bare Message-ID (contains @) to auto-detect it.

    Fallback behavior: If keyword search returns 0 results and the query
    has no prefix syntax, the API automatically falls back to semantic
    search. The response will include "search_type": "semantic" and
    "fallback": true in that case.

    Common patterns:
      "s:PATCH f:torvalds"                      - patches from Torvalds
      "s:PATCH f:akpm d:2026-01-01..2026-03-01" - akpm patches in date range
      "b:use-after-free"                         - body mentions use-after-free
      "s:PATCH b:mm_struct"                      - patches touching mm_struct
      "a:stable@vger.kernel.org"                 - emails to/from stable
      "f:torvalds d:2026-01-01..2026-03-01"      - emails in date range
      "b:kasan NOT s:Re:"                        - body contains kasan, not a reply

    Args:
        query: Search query with optional prefix syntax. Use plain text for
               keyword search, or prefix syntax for targeted queries.
        inbox: Limit search to a specific inbox (e.g. "netdev", "linux-mm").
               Strongly recommended. Empty = all inboxes (slower).
        page: Page number (1-based).
        per_page: Results per page (default 20, max 200).

    Returns JSON with: total, page, per_page, pages, search_type ("fts"/"semantic"),
    and messages list. Each message has: id, message_id, subject, sender, date,
    inbox_name, snippet (highlighted excerpt).
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
async def get_thread(message_id: str, full: bool = False) -> str:
    """Get the full discussion thread containing a message.

    Returns all messages in the thread sorted by date (oldest first).
    Use in_reply_to to reconstruct the tree: messages with empty in_reply_to
    are thread roots. The root field shows the root Message-ID.

    Args:
        message_id: Any Message-ID in the thread (not just the root).
        full: Set to true to include body_text and headers for each message.
              Default false (metadata only: subject, sender, date, in_reply_to).

    Returns JSON with: root (Message-ID), total count, inbox name, and
    messages array sorted by date.
    """
    try:
        params = {"full": 1} if full else {}
        data = await _api_get(f"/api/threads/{message_id}", params=params)
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


@mcp.tool(
    name="lore_semantic_search",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def semantic_search_tool(
    query: str,
    inbox: str = "",
) -> str:
    """Search kernel mailing list emails by semantic similarity.

    Unlike search_emails which uses exact keyword/FTS matching, this tool
    finds emails whose meaning is similar to your query, even if the exact
    words differ. Best for conceptual/natural-language queries:
      "memory fragmentation issues in page allocator"
      "network performance regression after driver update"
      "filesystem corruption bugs during power failure"

    Does NOT support prefix syntax (s:, f:, b:, d:, etc.) — use
    search_emails for structured/keyword queries.

    NOTE: This requires vector_search.enabled=true in config and pre-built
    FAISS indexes (python3 scripts/embed.py). Returns 503 error if disabled.
    In that case, use search_emails with plain text query instead — it will
    automatically fall back to semantic when FTS returns 0 results.

    Args:
        query: Natural language description of what you're looking for.
               More descriptive = better results. e.g. "OOM killer behavior
               under memory pressure" is better than "OOM".
        inbox: Limit search to a specific inbox (e.g. "linux-mm").
               Empty = search all indexed inboxes.

    Returns JSON with messages ranked by similarity score (higher = more
    relevant). Each message has: id, message_id, subject, sender, date,
    inbox_name, score (cosine similarity, 0-1 range).
    """
    try:
        params: dict = {"q": query}
        if inbox:
            params["inbox"] = inbox
        data = await _api_get("/api/search/semantic", params=params)
        return json.dumps(data, indent=2)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="lore_get_series",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def get_series(
    message_id: str,
    download: bool = False,
) -> str:
    """Get patch series metadata or download as mbox.

    Returns b4-like metadata: version detection, patch list, cover letter,
    and collected review trailers (Reviewed-by, Acked-by, etc.).

    Args:
        message_id: Any Message-ID in the patch thread.
        download: If true, download as mboxrd file (for git am).
                  If false, return JSON metadata.

    Returns JSON with: version, total patches, cover_letter, patches list
    with trailers, or raw mboxrd text if download=true.
    """
    try:
        params: dict = {"id": message_id}
        if download:
            params["download"] = 1
        data = await _api_get("/api/series", params=params)
        if isinstance(data, str):
            return data
        return json.dumps(data, indent=2)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="lore_get_stats",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def get_stats() -> str:
    """Get overall statistics about the mirror.

    Returns total message count, inbox count, database size,
    and the latest message info.
    """
    try:
        data = await _api_get("/api/stats")
        return json.dumps(data, indent=2)
    except Exception as e:
        return _handle_error(e)


if __name__ == "__main__":
    mcp.run()
