"""Stock onboarding (Phase 3).

``add_stock`` resolves a ticker to NSE/BSE symbols + name, assigns a sector via the
hand-maintained data/sector_map.yaml, warms price history (so the gate isn't WARMING_UP
longer than necessary) with a daily_metric backfill, and reminds the operator to run the
exposure drafting/ratification flow. It does NOT auto-run the LLM drafter.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from functools import lru_cache

import yaml

from app.config import SECTOR_MAP_YAML
from app.watchlist import upsert_stock, add_to_watchlist

try:
    from app.tools.prices import download_prices, default_window
except Exception:  # pragma: no cover
    download_prices = None


@lru_cache(maxsize=1)
def _sector_map() -> dict[str, str]:
    try:
        doc = yaml.safe_load(open(SECTOR_MAP_YAML, "r", encoding="utf-8"))
    except FileNotFoundError:  # pragma: no cover
        return {}
    return {str(k).upper(): v for k, v in (doc.get("map") or {}).items()}


def resolve_sector(ticker: str) -> str | None:
    """Sector-template key for a ticker, or None if unmapped."""
    return _sector_map().get(ticker.upper())


@dataclass
class OnboardResult:
    stock_id: int
    ticker_nse: str
    name: str
    sector: str | None
    warning: str | None
    backfilled_days: int


def _resolve_symbol(ticker: str):
    """Return (name, ticker_bse|None) for an NSE ticker, or raise if unresolvable.

    ``ticker_bse`` comes from the hand-verified data/bse_scrip_map.yaml, never from a
    guess or a lookup -- a wrong scrip code attaches another company's Tier-1 filings
    to this stock. Unmapped tickers get None and simply receive no BSE evidence.
    """
    if download_prices is None:  # pragma: no cover
        raise RuntimeError("yfinance not installed")
    import yfinance as yf
    from app.ingest.nse_bse import resolve_scrip
    t = yf.Ticker(f"{ticker}.NS")
    name = None
    try:
        info = getattr(t, "info", {}) or {}
        name = info.get("longName") or info.get("shortName")
    except Exception:  # pragma: no cover - yfinance flakiness
        name = None
    if not name:
        # Fall back to a price probe: if there's no price history it isn't tradable.
        start, end = default_window(30)
        series = download_prices(f"{ticker}.NS", start, end)
        if not series.adj_close:
            raise ValueError(f"could not resolve ticker {ticker!r} on NSE")
        name = ticker
    return name, resolve_scrip(ticker)


def _backfill(conn: sqlite3.Connection, stock_id: int, ticker: str) -> int:
    """Warm 200d of history and backfill daily_metric using the pure gate. Returns days."""
    from app.config import INDEX_TICKER
    from app.tools.prices import build_gate_inputs
    from app.tools.gate import classify
    from app.jobs.eod import write_daily_metric

    start, end = default_window(200)
    series = download_prices(f"{ticker}.NS", start, end)
    if len(series.adj_close) < 2:
        return 0
    index = download_prices(INDEX_TICKER, start, end)
    n = 0
    for i, day in enumerate(series.dates[1:], start=1):  # need a prior day for a return
        gi = build_gate_inputs(series, index, day)
        if gi.r_today is None:
            continue
        res = classify(r_today=gi.r_today, stock_returns=gi.stock_returns,
                       index_returns=gi.index_returns, r_index_today=gi.r_index_today,
                       vol_zscore=gi.vol_zscore, data_issue=gi.data_issue)
        write_daily_metric(
            conn, stock_id, day, res,
            close=series.adj_close[i],
            volume=series.volume[i] if i < len(series.volume) else None,
        )
        n += 1
    return n


def add_stock(conn: sqlite3.Connection, user_id: int | str, ticker: str) -> OnboardResult:
    """Resolve, sector-assign, warm, and watchlist a ticker for a user."""
    ticker = ticker.strip().upper()
    name, ticker_bse = _resolve_symbol(ticker)

    sector = resolve_sector(ticker)
    warning = None
    if sector is None:
        warning = (f"{ticker} has no sector mapping -- it will run with an empty exposure "
                   f"profile, so only the event trigger produces rich output. Add it to "
                   f"data/sector_map.yaml to enable Tier-2 attribution.")

    stock_id = upsert_stock(conn, name=name, ticker_nse=ticker,
                            ticker_bse=ticker_bse, sector_name=sector)
    add_to_watchlist(conn, stock_id, user_id=str(user_id))

    days = 0
    try:
        days = _backfill(conn, stock_id, ticker)
    except Exception as exc:  # pragma: no cover - network variance
        warning = (warning + " " if warning else "") + f"price warm-up failed: {exc}"

    print(f"[onboard] {ticker} added (sector={sector or 'NONE'}, backfilled {days} days). "
          f"Next: run `python -m app.exposure.draft --stock {ticker} --filing <extract>` "
          f"then `python -m app.exposure.ratify --stock {ticker}` to enable rich Tier-2 "
          f"attribution.")

    return OnboardResult(stock_id=stock_id, ticker_nse=ticker, name=name,
                         sector=sector, warning=warning, backfilled_days=days)
