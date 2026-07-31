"""Portfolio layer -- holdings, valuation, P&L and allocation.

Deliberately arithmetic-only. Every number here is derived from two stored facts:
the position you entered (``holding.qty``, ``holding.avg_cost``) and the adjusted
close the gate already recorded (``daily_metric.close``). Nothing is modelled,
forecast, or inferred.

What this module will NOT do, consistent with DESIGN.md section 0:
  * no projections, targets, or expected returns
  * no "should you buy/sell/hold" scoring of any kind
  * no risk score that collapses into implied advice

The one genuinely useful thing it adds over a broker app is the join to the
explanation engine: each position carries that day's gate outcome, so "why is my
portfolio down" resolves into per-position, cited reasons instead of a number.

Valuation caveat: ``daily_metric.close`` is an EOD adjusted close, so a position's
market value is as-of the last completed trading day -- not a live quote. Callers
should surface the ``as_of`` date rather than implying real-time pricing.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- Position management ---------------------------------------------------

def upsert_holding(conn: sqlite3.Connection, stock_id: int, qty: float,
                   avg_cost: float, user_id: str = "default") -> int:
    """Create or replace a position. Returns the holding id.

    A qty of 0 is allowed (a closed position); negative qty is rejected -- this
    system has no short-position semantics and silently accepting one would make
    every downstream weight and P&L figure meaningless.
    """
    if qty < 0:
        raise ValueError("qty cannot be negative (no short positions in v1)")
    if avg_cost < 0:
        raise ValueError("avg_cost cannot be negative")
    cur = conn.execute(
        """INSERT INTO holding (user_id, stock_id, qty, avg_cost, updated_at)
           VALUES (?,?,?,?,?)
           ON CONFLICT(user_id, stock_id) DO UPDATE SET
             qty=excluded.qty, avg_cost=excluded.avg_cost,
             updated_at=excluded.updated_at
           RETURNING id""",
        (user_id, stock_id, qty, avg_cost, _now()),
    )
    hid = cur.fetchone()[0]
    conn.commit()
    return hid


def remove_holding(conn: sqlite3.Connection, stock_id: int,
                   user_id: str = "default") -> None:
    conn.execute("DELETE FROM holding WHERE user_id=? AND stock_id=?",
                 (user_id, stock_id))
    conn.commit()


# --- Valuation -------------------------------------------------------------

def _latest_priced_date(conn: sqlite3.Connection, on_or_before: str | None = None) -> str | None:
    """Most recent date for which we hold any close price."""
    if on_or_before:
        row = conn.execute(
            "SELECT MAX(date) FROM daily_metric WHERE close IS NOT NULL AND date<=?",
            (on_or_before,),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT MAX(date) FROM daily_metric WHERE close IS NOT NULL"
        ).fetchone()
    return row[0] if row and row[0] else None


def _price_before(conn: sqlite3.Connection, stock_id: int, date_iso: str) -> float | None:
    """Latest close strictly before ``date_iso`` -- the previous-close baseline."""
    row = conn.execute(
        """SELECT close FROM daily_metric
           WHERE stock_id=? AND date<? AND close IS NOT NULL
           ORDER BY date DESC LIMIT 1""",
        (stock_id, date_iso),
    ).fetchone()
    return row["close"] if row else None


def positions(conn: sqlite3.Connection, user_id: str = "default",
              as_of: str | None = None) -> list[dict]:
    """Per-position valuation as of the latest priced trading day.

    Returns one dict per holding. ``price`` is None when we have no close for that
    stock (a newly added name, or a data gap) -- such rows are returned with null
    valuation fields rather than being silently dropped or defaulted to zero, so a
    missing price can never masquerade as a real loss.
    """
    date_iso = _latest_priced_date(conn, as_of)
    rows = conn.execute(
        """SELECT h.stock_id, h.qty, h.avg_cost,
                  s.ticker_nse, s.ticker_bse, s.name, sec.name AS sector
           FROM holding h
           JOIN stock s ON s.id = h.stock_id
           LEFT JOIN sector sec ON sec.id = s.sector_id
           WHERE h.user_id = ?
           ORDER BY s.ticker_nse""",
        (user_id,),
    ).fetchall()

    out: list[dict] = []
    for r in rows:
        price = prev_close = None
        gate = outcome = None
        priced_on = date_iso
        if date_iso:
            m = conn.execute(
                """SELECT close, gate_result FROM daily_metric
                   WHERE stock_id=? AND date=?""",
                (r["stock_id"], date_iso),
            ).fetchone()
            if m:
                price = m["close"]
                gate = m["gate_result"]
            if price is None:
                # Fall back to this stock's own most recent close (it may not have
                # traded on the portfolio's as-of date).
                fb = conn.execute(
                    """SELECT date, close, gate_result FROM daily_metric
                       WHERE stock_id=? AND close IS NOT NULL AND date<=?
                       ORDER BY date DESC LIMIT 1""",
                    (r["stock_id"], date_iso),
                ).fetchone()
                if fb:
                    price, gate = fb["close"], fb["gate_result"]
                    priced_on = fb["date"]
            # The baseline must be the close before the day this position was ACTUALLY
            # priced at, not before the portfolio's global as-of date. Those differ
            # whenever one stock's history runs further than another's -- which is now
            # routine, since a stock backfilled on demand is current while the
            # watchlist may be days behind. Using the global date there returns the
            # very same close as `price`, so every day change silently reads 0.00%.
            prev_close = _price_before(conn, r["stock_id"], priced_on)
            a = conn.execute(
                """SELECT outcome FROM attribution
                   WHERE stock_id=? AND date=? ORDER BY id DESC LIMIT 1""",
                (r["stock_id"], date_iso),
            ).fetchone()
            outcome = a["outcome"] if a else None

        qty, avg_cost = r["qty"], r["avg_cost"]
        invested = qty * avg_cost
        market_value = qty * price if price is not None else None
        pnl = (market_value - invested) if market_value is not None else None
        pnl_pct = (pnl / invested) if (pnl is not None and invested) else None
        day_change = (qty * (price - prev_close)
                      if price is not None and prev_close is not None else None)
        day_change_pct = ((price - prev_close) / prev_close
                          if price is not None and prev_close else None)

        out.append({
            "stock_id": r["stock_id"],
            "ticker": r["ticker_nse"],
            "name": r["name"],
            "sector": r["sector"],
            "qty": qty,
            "avg_cost": avg_cost,
            "price": price,
            "prev_close": prev_close,
            # The date this position was actually priced at. Usually the portfolio's
            # as_of, but older when this stock's history lags -- the UI needs to be
            # able to say so rather than implying every row is same-day.
            "priced_on": priced_on if price is not None else None,
            "invested": invested,
            "market_value": market_value,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "day_change": day_change,
            "day_change_pct": day_change_pct,
            "gate_result": gate,
            "outcome": outcome,
        })
    return out


def summary(conn: sqlite3.Connection, user_id: str = "default",
            as_of: str | None = None) -> dict:
    """Portfolio totals plus per-position weights.

    ``priced`` / ``unpriced`` counts are reported explicitly: totals cover only the
    positions we could value, and hiding that would misstate the portfolio.
    """
    pos = positions(conn, user_id=user_id, as_of=as_of)
    date_iso = _latest_priced_date(conn, as_of)

    valued = [p for p in pos if p["market_value"] is not None]
    total_value = sum(p["market_value"] for p in valued)
    total_invested = sum(p["invested"] for p in valued)
    total_pnl = total_value - total_invested
    total_day = sum(p["day_change"] for p in valued if p["day_change"] is not None)

    prev_total = total_value - total_day
    for p in pos:
        mv = p["market_value"]
        p["weight"] = (mv / total_value) if (mv is not None and total_value) else None

    return {
        "as_of": date_iso,
        "positions": pos,
        "total_value": total_value,
        "total_invested": total_invested,
        "total_pnl": total_pnl,
        "total_pnl_pct": (total_pnl / total_invested) if total_invested else None,
        "day_change": total_day,
        "day_change_pct": (total_day / prev_total) if prev_total else None,
        "priced_positions": len(valued),
        "unpriced_positions": len(pos) - len(valued),
    }


def allocation(conn: sqlite3.Connection, user_id: str = "default",
               as_of: str | None = None) -> list[dict]:
    """Sector allocation by market value. Unmapped stocks group under 'Unclassified'."""
    pos = positions(conn, user_id=user_id, as_of=as_of)
    valued = [p for p in pos if p["market_value"] is not None]
    total = sum(p["market_value"] for p in valued)
    buckets: dict[str, float] = {}
    for p in valued:
        buckets[p["sector"] or "Unclassified"] = (
            buckets.get(p["sector"] or "Unclassified", 0.0) + p["market_value"]
        )
    return sorted(
        ({"sector": k, "value": v, "weight": (v / total) if total else None}
         for k, v in buckets.items()),
        key=lambda d: d["value"], reverse=True,
    )


def history(conn: sqlite3.Connection, user_id: str = "default",
            days: int = 90) -> list[dict]:
    """Portfolio market value over time, using each day's stored closes.

    Uses current quantities across all history -- this is a *valuation* of today's
    position set at past prices, NOT a record of what the portfolio was actually
    worth then (there is no transaction ledger in v1). Labelled accordingly in the
    UI so it is never mistaken for realised performance.
    """
    rows = conn.execute(
        """SELECT h.stock_id, h.qty FROM holding h WHERE h.user_id=?""",
        (user_id,),
    ).fetchall()
    if not rows:
        return []
    qty_by_stock = {r["stock_id"]: r["qty"] for r in rows}
    placeholders = ",".join("?" * len(qty_by_stock))
    dates = [r[0] for r in conn.execute(
        f"""SELECT DISTINCT date FROM daily_metric
            WHERE stock_id IN ({placeholders}) AND close IS NOT NULL
            ORDER BY date DESC LIMIT ?""",
        (*qty_by_stock.keys(), days),
    ).fetchall()][::-1]

    out = []
    for d in dates:
        total = 0.0
        covered = 0
        for sid, qty in qty_by_stock.items():
            m = conn.execute(
                "SELECT close FROM daily_metric WHERE stock_id=? AND date=? AND close IS NOT NULL",
                (sid, d),
            ).fetchone()
            if m:
                total += qty * m["close"]
                covered += 1
        # Only emit days where every position has a price, so the series never
        # shows a fake drop caused by one missing close.
        if covered == len(qty_by_stock):
            out.append({"date": d, "value": total})
    return out
