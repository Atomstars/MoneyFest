"""Delayed price quotes.

**This is not a real-time feed and must never be presented as one.** Live NSE/BSE
ticks require a licensed data subscription or a broker API with a logged-in session.
What we have are two public, unauthenticated, delayed sources:

1. ``api.bseindia.com/.../getScripHeaderData`` -- needs a BSE scrip code, returns
   LTP, change, previous close and the day's OHLC. Preferred: it is the exchange's
   own endpoint and gives a full day bar in one request.
2. ``yfinance.Ticker.fast_info`` -- needs an NSE symbol. Fallback, and the only
   option for the ~130 NSE-only names with no BSE listing.

Both are best-effort. Failure returns ``None`` and the caller falls back to the last
stored EOD close, which is always labelled with its own date.
"""

from __future__ import annotations

import math
import sqlite3

import httpx

from app.config import (
    BSE_HTTP_HEADERS,
    BSE_SCRIP_HEADER_URL,
    QUOTE_DISCLAIMER,
    QUOTE_TTL_SECONDS,
)
from app.marketdata.cache import cached

FETCH_TIMEOUT = 15.0


def _num(value: object) -> float | None:
    """Parse a possibly-formatted number. BSE sends strings, sometimes with commas."""
    if value is None:
        return None
    try:
        f = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def fetch_bse_quote(scrip_code: str) -> tuple[dict, str] | None:
    """Delayed quote from BSE's own scrip-header endpoint."""
    resp = httpx.get(
        BSE_SCRIP_HEADER_URL,
        params={"Debtflag": "", "scripcode": str(scrip_code), "seriesid": ""},
        headers=BSE_HTTP_HEADERS,
        timeout=FETCH_TIMEOUT,
    )
    resp.raise_for_status()
    if "json" not in (resp.headers.get("content-type") or ""):
        return None  # the missing-Referer HTML-with-200 failure
    body = resp.json()
    header = body.get("Header") or {}
    current = body.get("CurrRate") or {}

    price = _num(current.get("LTP")) or _num(header.get("LTP"))
    prev_close = _num(header.get("PrevClose"))
    if price is None:
        return None

    change = _num(current.get("Chg"))
    change_pct = _num(current.get("PcChg"))
    # Derive whichever the endpoint omitted; never invent both.
    if change is None and prev_close is not None:
        change = price - prev_close
    if change_pct is None and prev_close:
        change_pct = (price - prev_close) / prev_close * 100.0

    return ({
        "price": price,
        "prev_close": prev_close,
        "change": change,
        # Stored as a fraction to match every other percentage in this codebase;
        # BSE reports whole percent.
        "change_pct": (change_pct / 100.0) if change_pct is not None else None,
        "open": _num(header.get("Open")),
        "high": _num(header.get("High")),
        "low": _num(header.get("Low")),
        "delayed": True,
        "disclaimer": QUOTE_DISCLAIMER,
    }, "BSE")


def fetch_yf_quote(symbol_nse: str) -> tuple[dict, str] | None:
    """Delayed quote via yfinance. Used when there is no BSE scrip code."""
    try:
        import yfinance as yf
    except Exception:
        return None

    info = yf.Ticker(f"{symbol_nse}.NS").fast_info
    price = _num(info.get("lastPrice"))
    prev_close = _num(info.get("previousClose"))
    if price is None:
        return None
    change = (price - prev_close) if prev_close is not None else None
    return ({
        "price": price,
        "prev_close": prev_close,
        "change": change,
        "change_pct": (change / prev_close) if (change is not None and prev_close) else None,
        "open": _num(info.get("open")),
        "high": _num(info.get("dayHigh")),
        "low": _num(info.get("dayLow")),
        "delayed": True,
        "disclaimer": QUOTE_DISCLAIMER,
    }, "yfinance")


def _last_stored_close(conn: sqlite3.Connection, stock_id: int) -> dict | None:
    """The EOD fallback: our own last two stored closes.

    Always available offline, always honest about its date -- and it is what the
    whole rest of the app (gate, portfolio valuation) is already priced from.
    """
    rows = conn.execute(
        """SELECT date, close FROM daily_metric
           WHERE stock_id=? AND close IS NOT NULL ORDER BY date DESC LIMIT 2""",
        (stock_id,),
    ).fetchall()
    if not rows:
        return None
    price = rows[0]["close"]
    prev = rows[1]["close"] if len(rows) > 1 else None
    change = (price - prev) if prev else None
    return {
        "price": price,
        "prev_close": prev,
        "change": change,
        "change_pct": (change / prev) if (change is not None and prev) else None,
        "open": None, "high": None, "low": None,
        "delayed": True,
        "as_of_date": rows[0]["date"],
        "disclaimer": f"Closing price on {rows[0]['date']}.",
    }


def get_quote(conn: sqlite3.Connection, stock_id: int, *, force: bool = False) -> dict:
    """Best available price for a stock, with its provenance attached.

    Always returns a dict. ``source`` is one of ``BSE``, ``yfinance``, ``stored_close``
    or ``none``, so the UI can state where the number came from instead of implying
    a live tick.
    """
    stock = conn.execute(
        "SELECT ticker_nse, ticker_bse FROM stock WHERE id=?", (stock_id,)
    ).fetchone()
    if stock is None:
        return {"source": "none", "price": None,
                "disclaimer": "Unknown stock."}

    scrip, symbol = stock["ticker_bse"], stock["ticker_nse"]

    def fetch() -> tuple[dict, str] | None:
        if scrip:
            got = fetch_bse_quote(scrip)
            if got:
                return got
        if symbol:
            return fetch_yf_quote(symbol)
        return None

    entry = cached(conn, stock_id, "quote", QUOTE_TTL_SECONDS, fetch, force=force)
    if entry is not None:
        return {**entry["payload"], "source": entry["source"],
                "fetched_at": entry["fetched_at"], "stale": entry["stale"]}

    stored = _last_stored_close(conn, stock_id)
    if stored is not None:
        return {**stored, "source": "stored_close", "stale": False}
    return {"source": "none", "price": None,
            "disclaimer": "No price available for this stock yet."}
