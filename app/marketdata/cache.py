"""TTL cache for third-party reference payloads, backed by ``reference_data``.

Why a database table and not an in-process dict: the API runs one connection per
request and the dev setup restarts constantly, so an in-memory cache would miss
almost every time and hammer endpoints that rate-limit aggressively.

The stale-fallback behaviour is the important part. On a refetch failure we serve the
**expired** payload with ``stale: True`` rather than nothing, because for this kind of
data yesterday's market cap is far more useful than an empty panel -- as long as the
UI can say it is yesterday's. What we never do is silently present stale data as fresh.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Callable


def _now() -> datetime:
    return datetime.now(timezone.utc)


def read_cache(conn: sqlite3.Connection, stock_id: int, kind: str) -> dict | None:
    """Return the cached entry, or None. Includes ``age_seconds`` and ``fetched_at``."""
    row = conn.execute(
        "SELECT payload_json, source, fetched_at FROM reference_data "
        "WHERE stock_id=? AND kind=?",
        (stock_id, kind),
    ).fetchone()
    if row is None:
        return None
    try:
        payload = json.loads(row["payload_json"])
        fetched = datetime.fromisoformat(row["fetched_at"])
    except (ValueError, TypeError, json.JSONDecodeError):
        return None
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    return {
        "payload": payload,
        "source": row["source"],
        "fetched_at": row["fetched_at"],
        "age_seconds": (_now() - fetched).total_seconds(),
    }


def write_cache(conn: sqlite3.Connection, stock_id: int, kind: str,
                payload: object, source: str) -> str:
    fetched_at = _now().isoformat()
    conn.execute(
        """INSERT INTO reference_data (stock_id, kind, payload_json, source, fetched_at)
           VALUES (?,?,?,?,?)
           ON CONFLICT(stock_id, kind) DO UPDATE SET
             payload_json=excluded.payload_json, source=excluded.source,
             fetched_at=excluded.fetched_at""",
        (stock_id, kind, json.dumps(payload), source, fetched_at),
    )
    conn.commit()
    return fetched_at


def invalidate(conn: sqlite3.Connection, stock_id: int, kind: str | None = None) -> None:
    if kind:
        conn.execute("DELETE FROM reference_data WHERE stock_id=? AND kind=?",
                     (stock_id, kind))
    else:
        conn.execute("DELETE FROM reference_data WHERE stock_id=?", (stock_id,))
    conn.commit()


def cached(conn: sqlite3.Connection, stock_id: int, kind: str, ttl_seconds: float,
           fetch: Callable[[], tuple[object, str] | None],
           *, force: bool = False) -> dict | None:
    """Serve ``kind`` from cache, refetching when stale.

    ``fetch`` returns ``(payload, source)`` on success, or ``None`` when the upstream
    had nothing usable. It may also raise -- both are treated as a failed refresh.

    Returns a dict with ``payload``, ``source``, ``fetched_at``, ``age_seconds`` and
    ``stale``, or ``None`` if there is neither a fresh fetch nor anything cached.
    """
    entry = None if force else read_cache(conn, stock_id, kind)
    if entry is not None and entry["age_seconds"] < ttl_seconds:
        return {**entry, "stale": False}

    try:
        fetched = fetch()
    except Exception:
        # Deliberately broad: every fetcher here talks to a third party that can fail
        # in ways we do not control, and a reference-data outage must never take down
        # the stock page. The stale-or-None fallback below is the whole point.
        fetched = None

    if fetched is not None:
        payload, source = fetched
        fetched_at = write_cache(conn, stock_id, kind, payload, source)
        return {"payload": payload, "source": source, "fetched_at": fetched_at,
                "age_seconds": 0.0, "stale": False}

    # Refresh failed. Expired data beats no data, provided we say it is expired.
    entry = entry or read_cache(conn, stock_id, kind)
    return {**entry, "stale": True} if entry else None
