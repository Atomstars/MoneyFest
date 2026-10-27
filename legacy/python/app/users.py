"""User + preference persistence (Phase 3).

Single-tenant in practice, but every watchlist/alert row carries a ``user_id`` so
multi-user is a data change, not a schema change. ``user_id`` used across the app is the
string form of ``user.id`` (the Phase-1 watchlist default was the literal "default").
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from app.config import DEFAULT_PREFS, MIN_ALERT_LEVELS


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def register_user(conn: sqlite3.Connection, telegram_chat_id: str,
                  display_name: str | None = None) -> int:
    """Idempotently register a Telegram user; returns user.id."""
    cur = conn.execute(
        """INSERT INTO user (telegram_chat_id, display_name, created_at, prefs_json)
           VALUES (?,?,?,?)
           ON CONFLICT(telegram_chat_id) DO UPDATE SET
             display_name=COALESCE(excluded.display_name, user.display_name)
           RETURNING id""",
        (str(telegram_chat_id), display_name, _now(), json.dumps(DEFAULT_PREFS)),
    )
    uid = cur.fetchone()[0]
    conn.commit()
    return uid


def user_by_chat(conn: sqlite3.Connection, telegram_chat_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM user WHERE telegram_chat_id=?", (str(telegram_chat_id),)
    ).fetchone()


def get_prefs(conn: sqlite3.Connection, user_id: int | str) -> dict:
    """Return the user's prefs merged over defaults (defaults fill any missing key)."""
    row = conn.execute("SELECT prefs_json FROM user WHERE id=?", (int(user_id),)).fetchone()
    prefs = dict(DEFAULT_PREFS)
    if row and row[0]:
        prefs.update(json.loads(row[0]))
    return prefs


def set_prefs(conn: sqlite3.Connection, user_id: int | str, updates: dict) -> dict:
    """Validate and merge preference updates. Returns the effective prefs."""
    prefs = get_prefs(conn, user_id)
    for k, v in updates.items():
        if k == "min_alert_level":
            v = str(v).upper()
            if v not in MIN_ALERT_LEVELS:
                raise ValueError(f"min_alert_level must be one of {MIN_ALERT_LEVELS}")
            prefs[k] = v
        elif k in ("quiet_market_days", "daily_digest"):
            prefs[k] = _as_bool(v)
        # unknown keys are ignored (forward-compatible)
    conn.execute("UPDATE user SET prefs_json=? WHERE id=?",
                 (json.dumps(prefs), int(user_id)))
    conn.commit()
    return prefs


def _as_bool(v) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def all_users(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM user").fetchall()
