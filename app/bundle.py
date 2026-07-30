"""Bundle assembler -- the Constraint-6 enforcement point.

``build_bundle(conn, stock_id, date, ...)`` produces the frozen evidence bundle the
future reasoning agent (Phase 2) will consume. It admits ONLY:

  * Tier-1 / Tier-3 evidence tagged to THIS stock, first seen in the window
    [prev trading day 15:30 IST, today 23:59 IST]; AND
  * Tier-2 evidence whose ``factor_id`` is in this stock's *ratified-effective*
    exposure profile.

Nothing else. This filter is the structural guarantee that an unlinked macro event
(e.g. RED_SEA_FREIGHT) can never reach a stock (e.g. TCS) that has no such exposure
edge -- the guarantee is CODE, not a prompt instruction.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

from app.config import MARKET_TZ
from app.exposure.profiles import effective_profile, ExposureEdge
from app.tools.gate import GateResult

IST = ZoneInfo(MARKET_TZ)

# Window opens at the previous trading day's close-ish boundary.
WINDOW_OPEN_TIME = time(15, 30)
WINDOW_CLOSE_TIME = time(23, 59, 59)


@dataclass(frozen=True)
class Bundle:
    """Frozen, serialisable agent input (DESIGN.md section 1.2)."""

    stock_id: int
    ticker: str | None
    date: str
    prev_trading_day: str | None  # for temporal-ordering / same-day-window checks
    move: float | None            # r_today
    idio: float | None
    sigma_idio: float | None
    beta: float | None
    index_move: float | None
    vol_z: float | None
    gate_result: str
    exposure_profile: list[dict]
    evidence: list[dict]

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, ensure_ascii=False)

    @staticmethod
    def from_json(s: str) -> "Bundle":
        d = json.loads(s)
        return Bundle(**d)


def _window(date_iso: str, prev_trading_day: str | None) -> tuple[datetime, datetime]:
    """[prev trading day 15:30 IST, today 23:59:59 IST]."""
    today = datetime.fromisoformat(date_iso).date()
    if prev_trading_day:
        prev = datetime.fromisoformat(prev_trading_day).date()
    else:
        prev = today - timedelta(days=1)  # calendar fallback
    open_dt = datetime.combine(prev, WINDOW_OPEN_TIME, tzinfo=IST)
    close_dt = datetime.combine(today, WINDOW_CLOSE_TIME, tzinfo=IST)
    return open_dt, close_dt


def _in_window(first_seen_at: str | None, open_dt: datetime, close_dt: datetime) -> bool:
    if not first_seen_at:
        return False
    try:
        seen = datetime.fromisoformat(first_seen_at)
    except ValueError:
        return False
    if seen.tzinfo is None:
        seen = seen.replace(tzinfo=IST)
    seen = seen.astimezone(IST)
    return open_dt <= seen <= close_dt


def build_bundle(
    conn: sqlite3.Connection,
    stock_id: int,
    date_iso: str,
    *,
    gate: GateResult | None = None,
    prev_trading_day: str | None = None,
) -> Bundle:
    """Assemble the filtered, frozen bundle for (stock, date)."""
    profile: list[ExposureEdge] = effective_profile(conn, stock_id)
    allowed_factor_ids = {e.factor_id for e in profile}

    open_dt, close_dt = _window(date_iso, prev_trading_day)

    admitted: list[dict] = []

    # Tier-1 / Tier-3 tagged to this stock, within the time window.
    for r in conn.execute(
        """SELECT id, tier, source, url, headline, body_text, factor_id,
                  published_at, first_seen_at, exchange_dissemination_at, suspect_reactive
           FROM evidence
           WHERE stock_id = ? AND tier IN (1, 3)""",
        (stock_id,),
    ).fetchall():
        if _in_window(r["first_seen_at"], open_dt, close_dt):
            admitted.append(_evi_dict(r))

    # Tier-2 whose factor_id is in the ratified-effective profile, admitted on the
    # SAME time window as Tier-1/3. Overnight macro (US Fed after IST close, crude
    # moves late evening) lands on the prior calendar day and must not be dropped.
    if allowed_factor_ids:
        placeholders = ",".join("?" for _ in allowed_factor_ids)
        for r in conn.execute(
            f"""SELECT id, tier, source, url, headline, body_text, factor_id,
                       published_at, first_seen_at, exchange_dissemination_at, suspect_reactive
                FROM evidence
                WHERE tier = 2 AND factor_id IN ({placeholders})""",
            [*allowed_factor_ids],
        ).fetchall():
            if _in_window(r["first_seen_at"], open_dt, close_dt):
                admitted.append(_evi_dict(r))

    ticker = _ticker(conn, stock_id)

    return Bundle(
        stock_id=stock_id,
        ticker=ticker,
        date=date_iso,
        prev_trading_day=prev_trading_day,
        move=(gate.ret if gate else None),
        idio=(gate.idio_ret if gate else None),
        sigma_idio=(gate.sigma_idio if gate else None),
        beta=(gate.beta60 if gate else None),
        index_move=(gate.index_ret if gate else None),
        vol_z=(gate.vol_zscore if gate else None),
        gate_result=(gate.outcome if gate else "UNKNOWN"),
        exposure_profile=[e.to_json_dict() for e in profile],
        evidence=sorted(admitted, key=lambda e: (e["tier"], e["id"])),
    )


def _evi_dict(r: sqlite3.Row) -> dict:
    return {
        "id": r["id"], "tier": r["tier"], "source": r["source"], "url": r["url"],
        "headline": r["headline"], "body_text": r["body_text"],
        "factor_id": r["factor_id"], "published_at": r["published_at"],
        "first_seen_at": r["first_seen_at"],
        "exchange_dissemination_at": r["exchange_dissemination_at"],
        "suspect_reactive": bool(r["suspect_reactive"]),
    }


def _ticker(conn: sqlite3.Connection, stock_id: int) -> str | None:
    row = conn.execute("SELECT ticker_nse FROM stock WHERE id=?", (stock_id,)).fetchone()
    return row[0] if row else None
