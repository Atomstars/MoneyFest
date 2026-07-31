"""Warm up a stock's price history and gate results on demand.

The EOD job processes the watchlist -- dozens of names. The universe browser lets a
user open any of ~5,000, and the gate cannot say anything about a stock it has never
priced: ``GateConfig.min_lookback`` is 40 trading days before ``classify`` will return
anything but ``WARMING_UP``.

So opening an untracked stock triggers this: one price download, then the pure gate
replayed over every day in the window. Typically 3-8 seconds. The endpoint is
synchronous and the UI shows a warming state, which is honest about the wait rather
than presenting an empty page as though the stock had nothing to say.

This module owns the canonical backfill; ``app/onboard.py`` delegates here so the
watchlist path and the browse path cannot drift apart.
"""

from __future__ import annotations

import sqlite3
import threading
import time

from app.config import BACKFILL_DAYS, GATE_CONFIG, INDEX_TICKER

# The index series is identical for every stock, and a warm-up burst (a user clicking
# through five names) would otherwise re-download ^NSEI five times. Cached briefly and
# behind a lock because FastAPI serves these handlers from a thread pool.
_INDEX_CACHE: dict[str, object] = {}
_INDEX_LOCK = threading.Lock()
_INDEX_TTL_SECONDS = 900.0


def _index_series(start: str, end: str):
    from app.tools.prices import download_prices

    key = f"{start}:{end}"
    with _INDEX_LOCK:
        hit = _INDEX_CACHE.get(key)
        if hit and (time.monotonic() - hit["at"]) < _INDEX_TTL_SECONDS:  # type: ignore[index]
            return hit["series"]  # type: ignore[index]
    series = download_prices(INDEX_TICKER, start, end)
    with _INDEX_LOCK:
        _INDEX_CACHE[key] = {"series": series, "at": time.monotonic()}
    return series


def history_status(conn: sqlite3.Connection, stock_id: int) -> dict:
    """How much usable history this stock has, and whether the gate can speak yet."""
    row = conn.execute(
        """SELECT COUNT(*) AS n, MIN(date) AS first, MAX(date) AS last
           FROM daily_metric WHERE stock_id=? AND close IS NOT NULL""",
        (stock_id,),
    ).fetchone()
    days = row["n"] or 0
    return {
        "days": days,
        "first_date": row["first"],
        "last_date": row["last"],
        # The gate's own floor, not an arbitrary number -- below this every
        # classification is WARMING_UP by construction.
        "min_required": GATE_CONFIG.min_lookback,
        "warm": days >= GATE_CONFIG.min_lookback,
    }


def ensure_history(conn: sqlite3.Connection, stock_id: int, *,
                   days: int = BACKFILL_DAYS, force: bool = False) -> dict:
    """Download prices and replay the gate over them. Idempotent.

    Returns a status dict. Never raises for ordinary data problems -- a delisted or
    illiquid scrip with no yfinance history is a normal outcome the UI must render,
    not an error.
    """
    from app.jobs.eod import write_daily_metric
    from app.tools.gate import classify
    from app.tools.prices import build_gate_inputs, default_window, download_prices

    before = history_status(conn, stock_id)
    if before["warm"] and not force:
        return {**before, "status": "already_warm", "written": 0}

    stock = conn.execute("SELECT ticker_nse FROM stock WHERE id=?", (stock_id,)).fetchone()
    if stock is None:
        return {**before, "status": "unknown_stock", "written": 0}
    ticker = stock["ticker_nse"]
    if not ticker:
        # BSE-only scrip: yfinance's .BO symbols do not reliably resolve, which
        # SHIP_NOTES already flags as the reason the second price source is absent.
        return {**before, "status": "no_nse_symbol", "written": 0,
                "message": "Only NSE-listed names can be priced; this scrip is BSE-only."}

    start, end = default_window(days)
    try:
        series = download_prices(f"{ticker}.NS", start, end)
    except Exception as exc:
        return {**before, "status": "price_fetch_failed", "written": 0,
                "message": str(exc)}
    if len(series.adj_close) < 2:
        return {**before, "status": "no_price_history", "written": 0,
                "message": f"yfinance returned no usable history for {ticker}.NS."}

    try:
        index = _index_series(start, end)
    except Exception as exc:
        return {**before, "status": "index_fetch_failed", "written": 0,
                "message": str(exc)}

    written = 0
    # From index 1: the first bar has no prior close, so it has no return.
    for i, day in enumerate(series.dates[1:], start=1):
        inputs = build_gate_inputs(series, index, day)
        if inputs.r_today is None:
            continue
        result = classify(
            r_today=inputs.r_today,
            stock_returns=inputs.stock_returns,
            index_returns=inputs.index_returns,
            r_index_today=inputs.r_index_today,
            vol_zscore=inputs.vol_zscore,
            data_issue=inputs.data_issue,
        )
        write_daily_metric(
            conn, stock_id, day, result,
            close=series.adj_close[i],
            volume=series.volume[i] if i < len(series.volume) else None,
        )
        written += 1

    after = history_status(conn, stock_id)
    return {**after, "status": "backfilled", "written": written}
