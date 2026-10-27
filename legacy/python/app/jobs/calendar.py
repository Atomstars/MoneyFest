"""Trading-calendar and run-log helpers (Phase 3 scheduler hardening).

The EOD job skips weekends and NSE holidays (data/nse_holidays.yaml), and records one
run_log row per attempt so a run is safely re-runnable and operationally visible.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timezone
from functools import lru_cache

import yaml

from app.config import NSE_HOLIDAYS_YAML


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@lru_cache(maxsize=1)
def _holidays() -> set[str]:
    try:
        doc = yaml.safe_load(open(NSE_HOLIDAYS_YAML, "r", encoding="utf-8"))
    except FileNotFoundError:  # pragma: no cover
        return set()
    out: set[str] = set()
    for _year, days in (doc.get("holidays") or {}).items():
        out.update(str(d) for d in days)
    return out


def is_trading_day(d: date | str) -> bool:
    """True on weekdays that are not listed NSE holidays."""
    if isinstance(d, str):
        d = date.fromisoformat(d)
    if d.weekday() >= 5:  # Sat/Sun
        return False
    return d.isoformat() not in _holidays()


def skip_reason(d: date | str) -> str | None:
    """Human-readable reason to skip, or None if it's a trading day."""
    if isinstance(d, str):
        d = date.fromisoformat(d)
    if d.weekday() >= 5:
        return "weekend"
    if d.isoformat() in _holidays():
        return "NSE holiday"
    return None


# --- run_log ---------------------------------------------------------------

def start_run(conn: sqlite3.Connection, run_date: str) -> int:
    cur = conn.execute(
        "INSERT INTO run_log (date, started_at) VALUES (?, ?) RETURNING id",
        (run_date, _now()),
    )
    rid = cur.fetchone()[0]
    conn.commit()
    return rid


def finish_run(conn: sqlite3.Connection, run_id: int, summary: dict) -> None:
    conn.execute(
        "UPDATE run_log SET finished_at=?, summary_json=? WHERE id=?",
        (_now(), json.dumps(summary, default=str), run_id),
    )
    conn.commit()
