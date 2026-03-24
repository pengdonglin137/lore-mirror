"""
Visit statistics collector with in-memory buffer and periodic SQLite flush.

Usage:
    from server.stats import stats_collector
    stats_collector.record(endpoint="/api/messages", inbox="netdev",
                           message_id="xxx@yyy", elapsed_ms=12.3)

The collector buffers counts in memory and flushes to db/stats.db every 60s.
"""

import atexit
import sqlite3
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

FLUSH_INTERVAL = 60  # seconds

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS endpoint_stats (
    hour TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    hits INTEGER DEFAULT 0,
    total_ms REAL DEFAULT 0,
    PRIMARY KEY (hour, endpoint)
);

CREATE TABLE IF NOT EXISTS inbox_stats (
    day TEXT NOT NULL,
    inbox TEXT NOT NULL,
    hits INTEGER DEFAULT 0,
    PRIMARY KEY (day, inbox)
);

CREATE TABLE IF NOT EXISTS message_stats (
    message_id TEXT PRIMARY KEY,
    inbox TEXT DEFAULT '',
    subject TEXT DEFAULT '',
    hits INTEGER DEFAULT 0,
    last_accessed TEXT
);

CREATE TABLE IF NOT EXISTS daily_summary (
    day TEXT PRIMARY KEY,
    total_hits INTEGER DEFAULT 0,
    unique_endpoints INTEGER DEFAULT 0
);
"""


class StatsCollector:
    """Thread-safe visit stats collector with buffered writes."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._lock = threading.Lock()
        # Buffers: keyed counters
        self._endpoint_hits: dict[tuple[str, str], int] = defaultdict(int)  # (hour, endpoint) -> hits
        self._endpoint_ms: dict[tuple[str, str], float] = defaultdict(float)
        self._inbox_hits: dict[tuple[str, str], int] = defaultdict(int)  # (day, inbox) -> hits
        self._message_hits: dict[str, int] = defaultdict(int)  # message_id -> hits
        self._message_meta: dict[str, tuple[str, str]] = {}  # message_id -> (inbox, subject)
        self._daily_hits: dict[str, int] = defaultdict(int)  # day -> hits
        self._daily_endpoints: dict[str, set] = defaultdict(set)  # day -> set of endpoints

        self._init_db()
        self._start_flush_timer()
        atexit.register(self.flush)

    def _init_db(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        conn.executescript(SCHEMA_SQL)
        conn.close()

    def _start_flush_timer(self):
        self._timer = threading.Timer(FLUSH_INTERVAL, self._flush_loop)
        self._timer.daemon = True
        self._timer.start()

    def _flush_loop(self):
        self.flush()
        self._start_flush_timer()

    def record(self, endpoint: str, elapsed_ms: float = 0,
               inbox: str = "", message_id: str = "", subject: str = ""):
        """Record a visit. Called from middleware, must be fast."""
        now = datetime.now(timezone.utc)
        hour = now.strftime("%Y-%m-%dT%H")
        day = now.strftime("%Y-%m-%d")

        with self._lock:
            self._endpoint_hits[(hour, endpoint)] += 1
            self._endpoint_ms[(hour, endpoint)] += elapsed_ms
            self._daily_hits[day] += 1
            self._daily_endpoints[day].add(endpoint)

            if inbox:
                self._inbox_hits[(day, inbox)] += 1
            if message_id:
                self._message_hits[message_id] += 1
                if message_id not in self._message_meta:
                    self._message_meta[message_id] = (inbox, subject)

    def flush(self):
        """Write buffered stats to SQLite."""
        with self._lock:
            ep_hits = dict(self._endpoint_hits)
            ep_ms = dict(self._endpoint_ms)
            ib_hits = dict(self._inbox_hits)
            msg_hits = dict(self._message_hits)
            msg_meta = dict(self._message_meta)
            daily_hits = dict(self._daily_hits)
            daily_endpoints = {k: len(v) for k, v in self._daily_endpoints.items()}

            self._endpoint_hits.clear()
            self._endpoint_ms.clear()
            self._inbox_hits.clear()
            self._message_hits.clear()
            self._message_meta.clear()
            self._daily_hits.clear()
            self._daily_endpoints.clear()

        if not (ep_hits or ib_hits or msg_hits or daily_hits):
            return

        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.execute("PRAGMA journal_mode=WAL")

            for (hour, endpoint), hits in ep_hits.items():
                total_ms = ep_ms.get((hour, endpoint), 0)
                conn.execute(
                    """INSERT INTO endpoint_stats (hour, endpoint, hits, total_ms)
                       VALUES (?, ?, ?, ?)
                       ON CONFLICT(hour, endpoint) DO UPDATE SET
                         hits = hits + excluded.hits,
                         total_ms = total_ms + excluded.total_ms""",
                    (hour, endpoint, hits, total_ms),
                )

            for (day, inbox), hits in ib_hits.items():
                conn.execute(
                    """INSERT INTO inbox_stats (day, inbox, hits)
                       VALUES (?, ?, ?)
                       ON CONFLICT(day, inbox) DO UPDATE SET
                         hits = hits + excluded.hits""",
                    (day, inbox, hits),
                )

            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
            for mid, hits in msg_hits.items():
                inbox, subject = msg_meta.get(mid, ("", ""))
                conn.execute(
                    """INSERT INTO message_stats (message_id, inbox, subject, hits, last_accessed)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(message_id) DO UPDATE SET
                         hits = hits + excluded.hits,
                         last_accessed = excluded.last_accessed,
                         inbox = CASE WHEN excluded.inbox != '' THEN excluded.inbox ELSE message_stats.inbox END,
                         subject = CASE WHEN excluded.subject != '' THEN excluded.subject ELSE message_stats.subject END""",
                    (mid, inbox, subject, hits, now_str),
                )

            for day, hits in daily_hits.items():
                unique = daily_endpoints.get(day, 0)
                conn.execute(
                    """INSERT INTO daily_summary (day, total_hits, unique_endpoints)
                       VALUES (?, ?, ?)
                       ON CONFLICT(day) DO UPDATE SET
                         total_hits = total_hits + excluded.total_hits,
                         unique_endpoints = MAX(daily_summary.unique_endpoints, excluded.unique_endpoints)""",
                    (day, hits, unique),
                )

            conn.commit()
            conn.close()
        except Exception:
            pass  # stats are best-effort, never crash the app

    def query_daily_trend(self, days: int = 30) -> list[dict]:
        """Get daily visit trend for the last N days."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT day, total_hits, unique_endpoints FROM daily_summary
               ORDER BY day DESC LIMIT ?""",
            (days,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in reversed(rows)]

    def query_hourly_trend(self, hours: int = 48) -> list[dict]:
        """Get hourly visit trend (aggregated across endpoints)."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT hour, SUM(hits) as hits, SUM(total_ms) as total_ms
               FROM endpoint_stats
               GROUP BY hour ORDER BY hour DESC LIMIT ?""",
            (hours,),
        ).fetchall()
        conn.close()
        result = []
        for r in reversed(rows):
            avg_ms = r["total_ms"] / r["hits"] if r["hits"] else 0
            result.append({"hour": r["hour"], "hits": r["hits"], "avg_ms": round(avg_ms, 1)})
        return result

    def query_top_endpoints(self, days: int = 7, limit: int = 20) -> list[dict]:
        """Get top endpoints by hit count in recent N days."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        cutoff = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        # Use hour prefix for filtering
        rows = conn.execute(
            """SELECT endpoint, SUM(hits) as hits,
                      SUM(total_ms) / SUM(hits) as avg_ms
               FROM endpoint_stats
               WHERE hour >= date(?, '-' || ? || ' days')
               GROUP BY endpoint ORDER BY hits DESC LIMIT ?""",
            (cutoff, days, limit),
        ).fetchall()
        conn.close()
        return [{"endpoint": r["endpoint"], "hits": r["hits"],
                 "avg_ms": round(r["avg_ms"], 1) if r["avg_ms"] else 0} for r in rows]

    def query_top_inboxes(self, days: int = 30, limit: int = 20) -> list[dict]:
        """Get most visited inboxes."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        cutoff = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        rows = conn.execute(
            """SELECT inbox, SUM(hits) as hits FROM inbox_stats
               WHERE day >= date(?, '-' || ? || ' days')
               GROUP BY inbox ORDER BY hits DESC LIMIT ?""",
            (cutoff, days, limit),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def query_top_messages(self, limit: int = 20) -> list[dict]:
        """Get most viewed messages."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT message_id, inbox, subject, hits, last_accessed
               FROM message_stats ORDER BY hits DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def query_total(self) -> dict:
        """Get overall totals."""
        conn = sqlite3.connect(str(self.db_path))
        total = conn.execute("SELECT COALESCE(SUM(total_hits), 0) FROM daily_summary").fetchone()[0]
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        today_hits = conn.execute(
            "SELECT COALESCE(total_hits, 0) FROM daily_summary WHERE day = ?", (today,)
        ).fetchone()
        conn.close()
        return {
            "total_hits": total,
            "today_hits": today_hits[0] if today_hits else 0,
        }


# Singleton — initialized lazily when app starts
_collector: StatsCollector | None = None


def init_stats(db_dir: Path) -> StatsCollector:
    """Initialize the global stats collector. Call once at app startup."""
    global _collector
    _collector = StatsCollector(db_dir / "stats.db")
    return _collector


def get_stats_collector() -> StatsCollector | None:
    return _collector
