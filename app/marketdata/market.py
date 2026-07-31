"""Market-wide context: index levels and the day's biggest movers.

Two things the home screen needs that are about the *market*, not about any one
stock, so neither fits ``reference_data``'s per-stock cache.

**Indices** come from yfinance (``^NSEI``, ``^BSESN``, ``^NSEBANK``, ``^CNXIT``).
Delayed, like every other quote here.

**Movers** are computed here rather than taken from an exchange endpoint, because the
obvious endpoint is broken. BSE's ``MktRGainerLoserData`` returns gainers only: both
``GLtype=gainer`` and ``GLtype=loser`` return the same rows, and for any stock that
actually fell it reports ``prevdayclose == ltradert`` and a 0.00% change. Cross-checked
against BSE's own ``getScripHeaderData``, which had TCS at -2.73% on the same day that
the movers feed called it flat. Trusting it would mean a "top losers" list that is
permanently empty and a market that never goes down.

So instead: take the **60 largest NSE-listed names by market cap** from the security
master, batch one yfinance download for all of them (~4s, a single request), and rank
the last two closes. Both sides come out, and the numbers agree with the per-stock
quote endpoint.

The large-cap restriction is the point, not a shortcut. Ranked across the whole
universe the list fills with sub-rupee microcaps pinned at their 20% circuit limit,
where a 12-paise tick is a 20% "gain" -- a top-movers list showing the same illiquid
penny stocks every day tells the reader nothing about what the market did.
"""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timezone

FETCH_TIMEOUT = 60.0

INDICES: list[tuple[str, str]] = [
    ("^NSEI", "NIFTY 50"),
    ("^BSESN", "SENSEX"),
    ("^NSEBANK", "BANK NIFTY"),
    ("^CNXIT", "NIFTY IT"),
]

INDICES_TTL_SECONDS = 120
MOVERS_TTL_SECONDS = 300

# How many large caps to rank, and how many to show per side. 60 is one batched
# yfinance request (~4s) and comfortably covers the NIFTY 50 plus near-misses.
MOVERS_UNIVERSE = 60
MOVERS_PER_SIDE = 6


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _num(value: object) -> float | None:
    if value is None:
        return None
    try:
        f = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


# --- Cache ------------------------------------------------------------------

def _read(conn: sqlite3.Connection, kind: str) -> dict | None:
    row = conn.execute(
        "SELECT payload_json, source, fetched_at FROM market_data WHERE kind=?", (kind,)
    ).fetchone()
    if row is None:
        return None
    try:
        payload = json.loads(row["payload_json"])
        fetched = datetime.fromisoformat(row["fetched_at"])
    except (ValueError, TypeError, json.JSONDecodeError):
        return None
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    return {"payload": payload, "source": row["source"],
            "fetched_at": row["fetched_at"],
            "age_seconds": (_now() - fetched).total_seconds()}


def _write(conn: sqlite3.Connection, kind: str, payload: object, source: str) -> str:
    fetched_at = _now().isoformat()
    conn.execute(
        """INSERT INTO market_data (kind, payload_json, source, fetched_at)
           VALUES (?,?,?,?)
           ON CONFLICT(kind) DO UPDATE SET
             payload_json=excluded.payload_json, source=excluded.source,
             fetched_at=excluded.fetched_at""",
        (kind, json.dumps(payload), source, fetched_at),
    )
    conn.commit()
    return fetched_at


def _cached(conn: sqlite3.Connection, kind: str, ttl: float, fetch, *, force: bool):
    """Same stale-beats-empty contract as ``marketdata.cache.cached``."""
    entry = None if force else _read(conn, kind)
    if entry is not None and entry["age_seconds"] < ttl:
        return {**entry, "stale": False}
    try:
        fetched = fetch()
    except Exception:
        fetched = None
    if fetched is not None:
        payload, source = fetched
        fetched_at = _write(conn, kind, payload, source)
        return {"payload": payload, "source": source, "fetched_at": fetched_at,
                "age_seconds": 0.0, "stale": False}
    entry = entry or _read(conn, kind)
    return {**entry, "stale": True} if entry else None


# --- Indices ----------------------------------------------------------------

def fetch_indices() -> tuple[list[dict], str] | None:
    try:
        import yfinance as yf
    except Exception:
        return None

    out: list[dict] = []
    for symbol, name in INDICES:
        try:
            info = yf.Ticker(symbol).fast_info
            last = _num(info.get("lastPrice"))
            prev = _num(info.get("previousClose"))
        except Exception:
            continue  # one dead index must not blank the whole strip
        if last is None:
            continue
        change = (last - prev) if prev is not None else None
        out.append({
            "symbol": symbol,
            "name": name,
            "value": last,
            "prev_close": prev,
            "change": change,
            "change_pct": (change / prev) if (change is not None and prev) else None,
        })
    return (out, "yfinance") if out else None


def get_indices(conn: sqlite3.Connection, *, force: bool = False) -> dict:
    entry = _cached(conn, "indices", INDICES_TTL_SECONDS, fetch_indices, force=force)
    if entry is None:
        return {"indices": [], "stale": False, "source": None, "fetched_at": None}
    return {"indices": entry["payload"], "stale": entry["stale"],
            "source": entry["source"], "fetched_at": entry["fetched_at"]}


# --- Movers -----------------------------------------------------------------

def largest_symbols(conn: sqlite3.Connection, limit: int = MOVERS_UNIVERSE) -> list[dict]:
    """The N biggest NSE-listed names by BSE-reported market cap."""
    return [dict(r) for r in conn.execute(
        """SELECT symbol_nse, name, stock_id FROM security
           WHERE symbol_nse IS NOT NULL AND market_cap IS NOT NULL
             AND status = 'Active'
           ORDER BY market_cap DESC LIMIT ?""",
        (limit,),
    ).fetchall()]


def fetch_movers(conn: sqlite3.Connection) -> tuple[dict, str] | None:
    """Rank today's biggest gainers and losers among the large caps."""
    try:
        import yfinance as yf
    except Exception:
        return None

    universe = largest_symbols(conn)
    if not universe:
        return None  # security master not synced yet
    by_symbol = {r["symbol_nse"]: r for r in universe}

    frame = yf.download([f"{s}.NS" for s in by_symbol], period="5d",
                        auto_adjust=True, progress=False, threads=True,
                        group_by="column")
    if frame is None or getattr(frame, "empty", True) or "Close" not in frame:
        return None
    closes = frame["Close"].dropna(how="all")
    if len(closes) < 2:
        return None

    last_row, prev_row = closes.iloc[-1], closes.iloc[-2]
    as_of = str(closes.index[-1])[:10]

    movers: list[dict] = []
    for column in closes.columns:
        symbol = str(column).removesuffix(".NS")
        meta = by_symbol.get(symbol)
        price, prev = _num(last_row.get(column)), _num(prev_row.get(column))
        if meta is None or price is None or prev is None or prev <= 0:
            continue
        movers.append({
            "symbol": symbol,
            "stock_id": meta["stock_id"],
            "name": meta["name"],
            "price": price,
            "change": price - prev,
            # Fractions everywhere in this codebase, never whole percent.
            "change_pct": (price - prev) / prev,
        })

    if not movers:
        return None
    ranked = sorted(movers, key=lambda r: r["change_pct"], reverse=True)
    return ({
        "gainers": [r for r in ranked if r["change_pct"] > 0][:MOVERS_PER_SIDE],
        "losers": [r for r in reversed(ranked) if r["change_pct"] < 0][:MOVERS_PER_SIDE],
        "universe": len(movers),
        "as_of": as_of,
    }, "yfinance")


def get_movers(conn: sqlite3.Connection, *, force: bool = False) -> dict:
    entry = _cached(conn, "movers", MOVERS_TTL_SECONDS,
                    lambda: fetch_movers(conn), force=force)
    if entry is None:
        return {"gainers": [], "losers": [], "universe": 0, "as_of": None,
                "stale": False, "source": None}
    return {**entry["payload"], "stale": entry["stale"], "source": entry["source"],
            "fetched_at": entry["fetched_at"]}
