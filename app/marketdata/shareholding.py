"""Quarterly shareholding pattern -- who owns the company, and how that is changing.

Primary source is NSE's ``corporate-share-holdings-master``, which returns roughly 20
quarters of the company's own filed pattern. For TCS it reports promoter 71.77% as of
30-JUN-2026, matching the filing exactly.

**What this gives you and what it does not.** The NSE feed carries the top-level split
the regulator requires -- promoter-and-promoter-group versus public, plus employee
trusts. It does *not* break the public half into FII / DII / retail; that detail lives
inside the XBRL document each row links to, which would need a separate fetch-and-parse
pass per quarter. Rather than leave the institutional question unanswered, we take the
aggregate institutional share from yfinance's ``major_holders`` and label it plainly as
a different source with a different as-of date. It is not a substitute for the FII/DII
split, and the UI says so.

Promoter holding is the number Indian retail investors actually watch: a promoter stake
falling several quarters in a row is the classic thing people want to see. So the trend
is returned alongside the latest figure, and quarter-on-quarter *change* is computed
here rather than left to the client.
"""

from __future__ import annotations

import math
import sqlite3
from datetime import datetime

import httpx

from app.config import (
    HTTP_HEADERS,
    NSE_BASE_URL,
    NSE_SHAREHOLDING_URL,
    SHAREHOLDING_TTL_SECONDS,
)
from app.marketdata.cache import cached

FETCH_TIMEOUT = 30.0


def _pct(value: object) -> float | None:
    """NSE sends percentages as strings ('71.77'). Return a fraction, or None."""
    if value in (None, "", "-"):
        return None
    try:
        f = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f) or not (0.0 <= f <= 100.0):
        return None
    return f / 100.0


def _iso_quarter(value: object) -> str | None:
    """'30-JUN-2026' -> '2026-06-30'."""
    if not value:
        return None
    try:
        return datetime.strptime(str(value).strip(), "%d-%b-%Y").date().isoformat()
    except ValueError:
        return None


def fetch_nse_shareholding(symbol_nse: str) -> list[dict] | None:
    """Quarterly promoter/public split, newest first.

    NSE's JSON API answers only to a client that already holds a session cookie, so
    the homepage GET is required, not decorative.
    """
    with httpx.Client(headers={**HTTP_HEADERS, "Accept": "text/html,application/xhtml+xml"},
                      timeout=FETCH_TIMEOUT, follow_redirects=True) as client:
        client.get(NSE_BASE_URL, timeout=20.0)
        resp = client.get(
            NSE_SHAREHOLDING_URL,
            params={"index": "equities", "symbol": symbol_nse},
            headers={**HTTP_HEADERS,
                     "Referer": f"{NSE_BASE_URL}/get-quotes/equity?symbol={symbol_nse}"},
        )
    resp.raise_for_status()
    if "json" not in (resp.headers.get("content-type") or ""):
        return None
    rows = resp.json()
    if not isinstance(rows, list):
        return None

    quarters: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        period = _iso_quarter(row.get("date"))
        promoter = _pct(row.get("pr_and_prgrp"))
        public = _pct(row.get("public_val"))
        if period is None or (promoter is None and public is None):
            continue
        # A quarter can be filed more than once (revisions). Keep the later
        # broadcast -- a revised filing supersedes the original.
        existing = quarters.get(period)
        if existing and str(row.get("broadcastDate") or "") <= existing["_broadcast"]:
            continue
        quarters[period] = {
            "period": period,
            "promoter_pct": promoter,
            "public_pct": public,
            "employee_trusts_pct": _pct(row.get("employeeTrusts")),
            "revised": str(row.get("revisedData") or "N").upper() == "Y",
            "_broadcast": str(row.get("broadcastDate") or ""),
        }

    ordered = sorted(quarters.values(), key=lambda q: q["period"], reverse=True)
    for quarter in ordered:
        quarter.pop("_broadcast", None)
    return ordered or None


def fetch_yf_holders(symbol_nse: str) -> dict | None:
    """Aggregate institutional share. A different source and as-of date to the above."""
    try:
        import yfinance as yf
    except Exception:
        return None
    frame = yf.Ticker(f"{symbol_nse}.NS").major_holders
    if frame is None or getattr(frame, "empty", True):
        return None

    def value(key: str) -> float | None:
        try:
            v = float(frame.loc[key].iloc[0])
        except Exception:
            return None
        return v if math.isfinite(v) else None

    institutions = value("institutionsPercentHeld")
    count = value("institutionsCount")
    if institutions is None and count is None:
        return None
    return {"institutions_pct": institutions,
            "institutions_count": int(count) if count else None,
            "insiders_pct": value("insidersPercentHeld")}


def get_shareholding(conn: sqlite3.Connection, stock_id: int, *,
                     force: bool = False) -> dict | None:
    """Latest split, quarter-on-quarter change, and the full quarterly trend."""
    row = conn.execute("SELECT ticker_nse FROM stock WHERE id=?", (stock_id,)).fetchone()
    symbol = row["ticker_nse"] if row else None
    if not symbol:
        return None

    def fetch():
        quarters = fetch_nse_shareholding(symbol)
        try:
            holders = fetch_yf_holders(symbol)
        except Exception:
            holders = None
        if not quarters and not holders:
            return None

        latest = quarters[0] if quarters else None
        previous = quarters[1] if quarters and len(quarters) > 1 else None
        change = None
        if latest and previous and \
                latest["promoter_pct"] is not None and previous["promoter_pct"] is not None:
            change = latest["promoter_pct"] - previous["promoter_pct"]

        return ({
            "latest": latest,
            "promoter_change_qoq": change,
            "quarters": quarters or [],
            "institutions": holders,
            # Stated in the payload so the UI cannot forget to disclose it.
            "institutions_note": (
                "Aggregate institutional holding from yfinance, as of its own "
                "reporting date. The FII/DII split is filed only inside the "
                "exchange XBRL documents and is not shown."
            ) if holders else None,
        }, "NSE" if quarters else "yfinance")

    entry = cached(conn, stock_id, "shareholding", SHAREHOLDING_TTL_SECONDS, fetch,
                   force=force)
    if entry is None:
        return None
    return {**entry["payload"], "fetched_at": entry["fetched_at"],
            "stale": entry["stale"], "source": entry["source"]}
