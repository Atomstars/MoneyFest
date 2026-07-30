"""Trigger & alert selection (Phase 3).

``select_alerts(conn, run_date)`` reads the day's attribution rows for watchlisted
stocks and returns the alerts to deliver -- deterministic and side-effect-free (the
delivery layer records/sends). Dedupe is by the ``alert`` table's UNIQUE(user_id,
attribution_id): already-recorded rows are excluded, so an EOD rerun never re-selects.

Outcome x preference matrix (see README):

              ALL            EXPLAINED_ONLY      HIGH_ONLY
ATTRIBUTED    send           send                send only if top driver HIGH
EVENT_NO_MOVE send           send                suppress
NO_DRIVER     send           suppress            suppress
MARKET        send*          suppress            suppress          (*unless quiet_market_days)
NOISE         never (digest-only)
DATA_ISSUE    admin log, never a user alert
PENDING/other never
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

ALWAYS_WORTHY = {"ATTRIBUTED", "EVENT_NO_MOVE", "NO_DRIVER"}
EXPLAINED = {"ATTRIBUTED", "EVENT_NO_MOVE"}
NEVER_USER = {"NOISE", "DATA_ISSUE", "PENDING_ATTRIBUTION", "WARMING_UP"}


@dataclass
class Alert:
    user_id: str
    chat_id: str | None
    stock_id: int
    ticker: str | None
    name: str
    date: str
    attribution_id: int
    outcome: str
    rendered_text: str
    move: float | None = None
    top_confidence: str | None = None

    def metadata_line(self) -> str:
        pct = "n/a" if self.move is None else f"{self.move * 100:+.2f}%"
        return f"{self.ticker or self.name} · {self.date} · moved {pct}"


def is_alert_worthy(outcome: str, prefs: dict, top_confidence: str | None) -> bool:
    """Apply the outcome x preference matrix. Pure."""
    if outcome in NEVER_USER:
        return False
    level = prefs.get("min_alert_level", "ALL")

    if level == "HIGH_ONLY":
        return outcome == "ATTRIBUTED" and top_confidence == "HIGH"
    if level == "EXPLAINED_ONLY":
        return outcome in EXPLAINED
    # ALL
    if outcome == "MARKET":
        return not prefs.get("quiet_market_days", False)
    return outcome in ALWAYS_WORTHY or outcome == "MARKET"


def _top_confidence(conn: sqlite3.Connection, attribution_id: int) -> str | None:
    row = conn.execute(
        "SELECT confidence FROM driver WHERE attribution_id=? ORDER BY rank ASC LIMIT 1",
        (attribution_id,),
    ).fetchone()
    return row[0] if row else None


def _move(conn: sqlite3.Connection, stock_id: int, date: str) -> float | None:
    row = conn.execute(
        "SELECT ret FROM daily_metric WHERE stock_id=? AND date=?", (stock_id, date)
    ).fetchone()
    return row[0] if row else None


def select_alerts(conn: sqlite3.Connection, run_date: str) -> list[Alert]:
    """Return the alerts to deliver for ``run_date`` (excludes already-recorded)."""
    from app.users import get_prefs

    alerts: list[Alert] = []
    for u in conn.execute("SELECT id, telegram_chat_id FROM user").fetchall():
        user_id = str(u["id"])
        prefs = get_prefs(conn, u["id"])
        for r in conn.execute(
            """SELECT a.id AS attribution_id, a.outcome, a.rendered_text,
                      s.id AS stock_id, s.ticker_nse, s.name
               FROM attribution a
               JOIN stock s ON s.id = a.stock_id
               JOIN watchlist_item w ON w.stock_id = s.id AND w.user_id = ?
               WHERE a.date = ?
                 AND NOT EXISTS (SELECT 1 FROM alert al
                                 WHERE al.user_id = ? AND al.attribution_id = a.id)""",
            (user_id, run_date, user_id),
        ).fetchall():
            top = _top_confidence(conn, r["attribution_id"])
            if not is_alert_worthy(r["outcome"], prefs, top):
                continue
            alerts.append(Alert(
                user_id=user_id, chat_id=u["telegram_chat_id"],
                stock_id=r["stock_id"], ticker=r["ticker_nse"], name=r["name"],
                date=run_date, attribution_id=r["attribution_id"],
                outcome=r["outcome"], rendered_text=r["rendered_text"] or "",
                move=_move(conn, r["stock_id"], run_date), top_confidence=top,
            ))
    return alerts
