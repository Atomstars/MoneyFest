"""Company fundamentals: key stats, financial statements, business profile.

Two sources, chosen per field rather than one wholesale:

* **BSE ``ComHeadernew``** -- EPS, P/E, P/B, ROE, operating and net margin, computed
  on Indian accounting standards by the exchange the company files with. For an
  Indian listing these are the numbers the company itself reports, and they are
  preferred wherever both sources offer the same metric.
* **yfinance** -- market cap, 52-week range, beta, dividend yield, employees, the
  business summary, and the full income statement. Things BSE's header does not carry.

Every returned metric records which source produced it, because the two do disagree
(different consolidation, different trailing windows) and a fundamentals panel that
cannot say where a number came from is not much use when it looks wrong.

Nothing here is a valuation judgement. These are reported figures, presented as
reported -- no scoring, no "cheap/expensive", no derived signal.
"""

from __future__ import annotations

import math
import sqlite3

import httpx

from app.config import (
    BSE_COMPANY_HEADER_URL,
    BSE_HTTP_HEADERS,
    FINANCIALS_TTL_SECONDS,
    KEY_STATS_TTL_SECONDS,
    PROFILE_TTL_SECONDS,
)
from app.marketdata.cache import cached

FETCH_TIMEOUT = 30.0


def _num(value: object) -> float | None:
    if value is None:
        return None
    try:
        f = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return f


def _positive(value: object) -> float | None:
    """For ratios where 0 is BSE's 'not reported' sentinel (it sends OPM 0.00 freely)."""
    f = _num(value)
    return f if (f is not None and f != 0) else None


def _tickers(conn: sqlite3.Connection, stock_id: int) -> tuple[str | None, str | None]:
    row = conn.execute("SELECT ticker_nse, ticker_bse FROM stock WHERE id=?",
                       (stock_id,)).fetchone()
    return (row["ticker_nse"], row["ticker_bse"]) if row else (None, None)


def _yf_ticker(symbol_nse: str):
    import yfinance as yf
    return yf.Ticker(f"{symbol_nse}.NS")


# --- Key stats --------------------------------------------------------------

def fetch_bse_header(scrip_code: str) -> dict | None:
    """Exchange-reported ratios for one scrip."""
    resp = httpx.get(
        BSE_COMPANY_HEADER_URL,
        params={"quotetype": "EQ", "scripcode": str(scrip_code), "seriesid": ""},
        headers=BSE_HTTP_HEADERS, timeout=FETCH_TIMEOUT,
    )
    resp.raise_for_status()
    if "json" not in (resp.headers.get("content-type") or ""):
        return None
    body = resp.json()
    return body if isinstance(body, dict) and body.get("SecurityCode") else None


def _key_stats_payload(symbol_nse: str | None, scrip_bse: str | None) -> dict | None:
    stats: dict[str, float | None] = {}
    sources: dict[str, str] = {}
    meta: dict[str, object] = {}

    def put(field: str, value: float | None, source: str) -> None:
        if value is not None and field not in stats:
            stats[field] = value
            sources[field] = source

    if scrip_bse:
        try:
            header = fetch_bse_header(scrip_bse)
        except Exception:
            header = None
        if header:
            put("eps", _num(header.get("EPS")), "BSE")
            put("pe", _num(header.get("PE")), "BSE")
            put("pb", _num(header.get("PB")), "BSE")
            # BSE reports these as whole percent; normalise to fractions so the
            # formatter never has to guess which convention a field follows.
            roe = _positive(header.get("ROE"))
            put("roe", roe / 100.0 if roe is not None else None, "BSE")
            opm = _positive(header.get("OPM"))
            put("operating_margin", opm / 100.0 if opm is not None else None, "BSE")
            npm = _positive(header.get("NPM"))
            put("net_margin", npm / 100.0 if npm is not None else None, "BSE")
            meta["industry"] = header.get("Industry") or header.get("ISubGroup")
            meta["bse_sector"] = header.get("Sector")
            meta["isin"] = header.get("ISIN")
            meta["face_value"] = _num(header.get("FaceVal"))
            meta["index_membership"] = header.get("Index")

    if symbol_nse:
        try:
            info = _yf_ticker(symbol_nse).info or {}
        except Exception:
            info = {}
        if info:
            put("market_cap", _num(info.get("marketCap")), "yfinance")
            put("eps", _num(info.get("trailingEps")), "yfinance")
            put("pe", _num(info.get("trailingPE")), "yfinance")
            put("pb", _num(info.get("priceToBook")), "yfinance")
            put("book_value", _num(info.get("bookValue")), "yfinance")
            put("roe", _num(info.get("returnOnEquity")), "yfinance")
            put("net_margin", _num(info.get("profitMargins")), "yfinance")
            put("high_52w", _num(info.get("fiftyTwoWeekHigh")), "yfinance")
            put("low_52w", _num(info.get("fiftyTwoWeekLow")), "yfinance")
            put("beta", _num(info.get("beta")), "yfinance")
            # yfinance reports dividendYield for Indian names as whole percent.
            dy = _num(info.get("dividendYield"))
            put("dividend_yield", dy / 100.0 if dy is not None else None, "yfinance")
            de = _num(info.get("debtToEquity"))
            put("debt_to_equity", de / 100.0 if de is not None else None, "yfinance")
            meta.setdefault("industry", info.get("industry"))
            meta["currency"] = info.get("currency") or "INR"

    if not stats:
        return None
    return {"stats": stats, "sources": sources, "meta": meta}


def get_key_stats(conn: sqlite3.Connection, stock_id: int, *,
                  force: bool = False) -> dict | None:
    symbol, scrip = _tickers(conn, stock_id)
    if not symbol and not scrip:
        return None

    def fetch():
        payload = _key_stats_payload(symbol, scrip)
        if payload is None:
            return None
        used = sorted(set(payload["sources"].values()))
        return payload, "+".join(used) or "unknown"

    entry = cached(conn, stock_id, "key_stats", KEY_STATS_TTL_SECONDS, fetch, force=force)
    if entry is None:
        return None
    return {**entry["payload"], "fetched_at": entry["fetched_at"],
            "stale": entry["stale"], "source": entry["source"]}


# --- Financial statements ---------------------------------------------------

# yfinance's income-statement row labels. Order matters: first match wins, so the
# most specific label is listed before its fallbacks.
_REVENUE_ROWS = ("Total Revenue", "Operating Revenue", "Revenue")
_NET_INCOME_ROWS = ("Net Income", "Net Income Common Stockholders",
                    "Net Income From Continuing Operation Net Minority Interest")
_EBITDA_ROWS = ("EBITDA", "Normalized EBITDA")


def _pick_row(frame, labels: tuple[str, ...]):
    for label in labels:
        if label in frame.index:
            return frame.loc[label]
    return None


def _statement_periods(frame, limit: int) -> list[dict]:
    """Turn a yfinance statement frame into plain period dicts, newest first."""
    if frame is None or getattr(frame, "empty", True):
        return []
    revenue = _pick_row(frame, _REVENUE_ROWS)
    net_income = _pick_row(frame, _NET_INCOME_ROWS)
    ebitda = _pick_row(frame, _EBITDA_ROWS)

    periods: list[dict] = []
    for column in list(frame.columns)[:limit]:
        rev = _num(revenue[column]) if revenue is not None else None
        net = _num(net_income[column]) if net_income is not None else None
        if rev is None and net is None:
            continue
        periods.append({
            "period": str(column)[:10],
            "revenue": rev,
            "net_income": net,
            "ebitda": _num(ebitda[column]) if ebitda is not None else None,
            "net_margin": (net / rev) if (rev and net is not None) else None,
        })
    return periods


def get_financials(conn: sqlite3.Connection, stock_id: int, *,
                   force: bool = False) -> dict | None:
    """Annual and quarterly revenue / profit history.

    Amounts are absolute rupees as reported by the source; the UI formats them into
    crore. No growth rates are computed here -- the chart shows the levels and lets
    the reader draw the trend.
    """
    symbol, _ = _tickers(conn, stock_id)
    if not symbol:
        return None

    def fetch():
        ticker = _yf_ticker(symbol)
        annual = _statement_periods(ticker.income_stmt, 5)
        quarterly = _statement_periods(ticker.quarterly_income_stmt, 8)
        if not annual and not quarterly:
            return None
        return {"annual": annual, "quarterly": quarterly, "currency": "INR"}, "yfinance"

    entry = cached(conn, stock_id, "financials", FINANCIALS_TTL_SECONDS, fetch, force=force)
    if entry is None:
        return None
    return {**entry["payload"], "fetched_at": entry["fetched_at"],
            "stale": entry["stale"], "source": entry["source"]}


# --- Company profile --------------------------------------------------------

def get_profile(conn: sqlite3.Connection, stock_id: int, *,
                force: bool = False) -> dict | None:
    """Business summary, industry, employees, website, listing date."""
    symbol, _ = _tickers(conn, stock_id)

    from app.universe import find_security_for_stock
    security = find_security_for_stock(conn, stock_id)

    def fetch():
        info = {}
        if symbol:
            try:
                info = _yf_ticker(symbol).info or {}
            except Exception:
                info = {}
        payload = {
            "summary": info.get("longBusinessSummary"),
            "website": info.get("website"),
            "employees": info.get("fullTimeEmployees"),
            "industry": (info.get("industry")
                         or (security or {}).get("industry")),
            "sector": info.get("sector"),
            "city": info.get("city"),
            "isin": (security or {}).get("isin"),
            "listing_date": (security or {}).get("listing_date"),
            "exchanges": (security or {}).get("exchanges"),
            "bse_group": (security or {}).get("bse_group"),
        }
        if not any(payload.values()):
            return None
        source = "yfinance" if info else "security_master"
        return payload, source

    entry = cached(conn, stock_id, "profile", PROFILE_TTL_SECONDS, fetch, force=force)
    if entry is None:
        return None
    return {**entry["payload"], "fetched_at": entry["fetched_at"],
            "stale": entry["stale"], "source": entry["source"]}
