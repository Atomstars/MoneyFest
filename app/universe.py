"""The security master: every equity listed on NSE and BSE, searchable.

This is the catalogue a user browses *before* deciding what to track. It is
deliberately not the same thing as ``stock``:

* ``security``  -- ~7,000 rows. What exists on the exchanges. Refreshed from two
  public listing files. Cheap: one HTTP request each, no per-name work.
* ``stock``     -- dozens of rows. What this app actually analyses: prices, gate
  results, exposure profile, attribution. Expensive per name.

:func:`promote` is the one-way door between them, called when a user tracks a name.

**Why ISIN is the join key.** NSE identifies a company by symbol (``TCS``), BSE by a
numeric scrip code (``532540``). Neither appears in the other's file, and matching on
company name is a trap -- "Ltd" vs "Limited", "&" vs "and", and several genuinely
distinct companies share a leading word. ISIN is the one identifier both publish and
both agree on, so the join is exact.

That join also *derives* the BSE scrip code rather than trusting a hand-typed one.
CLAUDE.md is blunt about why this matters: a wrong scrip code silently attaches
another company's filings to a stock. A code obtained by matching ISINs cannot be
wrong in that way, which makes this a strictly safer source than the hand-maintained
``data/bse_scrip_map.yaml`` it supersedes.
"""

from __future__ import annotations

import csv
import io
import sqlite3
from datetime import datetime, timezone

import httpx

from app.config import (
    BSE_HTTP_HEADERS,
    BSE_SCRIP_LIST_URL,
    HTTP_HEADERS,
    NSE_BASE_URL,
    NSE_EQUITY_LIST_FALLBACK_URL,
    NSE_EQUITY_LIST_URL,
)

FETCH_TIMEOUT = 60.0


class UniverseError(RuntimeError):
    """Raised when a listing feed is unreachable or returns something unusable.

    Loud on purpose. A silently-empty universe is indistinguishable from "the
    exchanges delisted everything", and the same class of silent-zero bug already
    cost this project its entire Tier-1 evidence backbone for four phases.
    """


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(value: object) -> str | None:
    """Trim a CSV/JSON cell to a real value or None. NSE pads its headers and cells."""
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _to_float(value: object) -> float | None:
    try:
        f = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return f if f == f else None  # drop NaN


def _iso_date(value: object) -> str | None:
    """NSE lists dates as 06-OCT-2008. Normalise to ISO, or drop it."""
    s = _clean(value)
    if not s:
        return None
    try:
        return datetime.strptime(s, "%d-%b-%Y").date().isoformat()
    except ValueError:
        return None


# --- Fetchers ---------------------------------------------------------------

def fetch_nse_listings() -> list[dict]:
    """NSE's published equity list (EQUITY_L.csv).

    A homepage GET first: nsearchives serves the CSV only to clients carrying an
    ordinary browser session, which is the same cookie-warm-up dance the Tier-1
    announcements ingest already has to do.
    """
    last: Exception | None = None
    for url in (NSE_EQUITY_LIST_URL, NSE_EQUITY_LIST_FALLBACK_URL):
        try:
            with httpx.Client(headers=HTTP_HEADERS, timeout=FETCH_TIMEOUT,
                              follow_redirects=True) as client:
                client.get(NSE_BASE_URL, timeout=20.0)
                resp = client.get(url)
            resp.raise_for_status()
            if len(resp.content) < 1000:
                raise UniverseError(f"NSE list at {url} was suspiciously small "
                                    f"({len(resp.content)} bytes)")
            rows = list(csv.DictReader(io.StringIO(resp.text)))
            if not rows:
                raise UniverseError(f"NSE list at {url} parsed to zero rows")
            return rows
        except Exception as exc:  # try the mirror before giving up
            last = exc
    raise UniverseError(f"could not fetch the NSE equity list: {last}") from last


def fetch_bse_listings() -> list[dict]:
    """BSE's active-equity scrip list.

    ``BSE_HTTP_HEADERS`` carries the Referer/Origin pair. Without it api.bseindia.com
    answers with its HTML landing page and a **200**, which parses as "no scrips" --
    exactly the failure mode documented in CLAUDE.md.
    """
    resp = httpx.get(BSE_SCRIP_LIST_URL, headers=BSE_HTTP_HEADERS, timeout=FETCH_TIMEOUT)
    resp.raise_for_status()
    ctype = resp.headers.get("content-type", "")
    if "json" not in ctype:
        raise UniverseError(
            f"BSE scrip list returned {ctype!r}, not JSON -- this is the "
            f"missing-Referer failure (HTTP {resp.status_code}, "
            f"{len(resp.content)} bytes)."
        )
    rows = resp.json()
    if not isinstance(rows, list) or not rows:
        raise UniverseError("BSE scrip list parsed to zero rows")
    return rows


# --- The join ---------------------------------------------------------------

def merge_listings(nse_rows: list[dict], bse_rows: list[dict]) -> list[dict]:
    """Join both exchanges on ISIN into one row per security.

    Pure -- no I/O -- so the join logic is unit-testable against fixture rows.

    Where both exchanges list a company, NSE wins on name and series (its file is
    cleaner) and BSE contributes scrip code, group, industry and market cap (its
    file is richer). Rows without an ISIN are dropped: they cannot be joined, and
    an unjoinable half-record is worse than an absent one.
    """
    merged: dict[str, dict] = {}

    for row in nse_rows:
        # NSE's header row is space-padded ('  SERIES'), so index by stripped key.
        r = {(k or "").strip(): v for k, v in row.items()}
        isin = _clean(r.get("ISIN NUMBER"))
        symbol = _clean(r.get("SYMBOL"))
        if not isin or not symbol:
            continue
        merged[isin] = {
            "isin": isin,
            "symbol_nse": symbol,
            "scrip_bse": None,
            "name": _clean(r.get("NAME OF COMPANY")) or symbol,
            "series": _clean(r.get("SERIES")),
            "bse_group": None,
            "industry": None,
            "face_value": _to_float(r.get("FACE VALUE")),
            "listing_date": _iso_date(r.get("DATE OF LISTING")),
            "market_cap": None,
            "exchanges": "NSE",
            "status": "Active",
        }

    for row in bse_rows:
        isin = _clean(row.get("ISIN_NUMBER"))
        scrip = _clean(row.get("SCRIP_CD"))
        if not isin or not scrip:
            continue
        existing = merged.get(isin)
        if existing is None:
            merged[isin] = {
                "isin": isin,
                "symbol_nse": None,
                "scrip_bse": scrip,
                "name": (_clean(row.get("Issuer_Name"))
                         or _clean(row.get("Scrip_Name")) or scrip),
                "series": None,
                "bse_group": _clean(row.get("GROUP")),
                "industry": _clean(row.get("INDUSTRY")),
                "face_value": _to_float(row.get("FACE_VALUE")),
                "listing_date": None,
                "market_cap": _to_float(row.get("Mktcap")),
                "exchanges": "BSE",
                "status": _clean(row.get("Status")) or "Active",
            }
        else:
            # Dual-listed: BSE fills in what NSE's file does not carry.
            existing["scrip_bse"] = scrip
            existing["bse_group"] = _clean(row.get("GROUP"))
            existing["industry"] = _clean(row.get("INDUSTRY"))
            existing["market_cap"] = _to_float(row.get("Mktcap"))
            existing["exchanges"] = "NSE,BSE"

    return list(merged.values())


# --- Persistence ------------------------------------------------------------

def save_securities(conn: sqlite3.Connection, rows: list[dict]) -> dict:
    """Upsert merged rows. Preserves ``stock_id`` on names already promoted."""
    now = _now()
    before = conn.execute("SELECT COUNT(*) FROM security").fetchone()[0]
    conn.executemany(
        """INSERT INTO security (isin, symbol_nse, scrip_bse, name, series, bse_group,
                                 industry, face_value, listing_date, market_cap,
                                 exchanges, status, synced_at)
           VALUES (:isin, :symbol_nse, :scrip_bse, :name, :series, :bse_group,
                   :industry, :face_value, :listing_date, :market_cap,
                   :exchanges, :status, :synced_at)
           ON CONFLICT(isin) DO UPDATE SET
             symbol_nse=excluded.symbol_nse, scrip_bse=excluded.scrip_bse,
             name=excluded.name, series=excluded.series, bse_group=excluded.bse_group,
             industry=excluded.industry, face_value=excluded.face_value,
             listing_date=excluded.listing_date, market_cap=excluded.market_cap,
             exchanges=excluded.exchanges, status=excluded.status,
             synced_at=excluded.synced_at""",
        [{**r, "synced_at": now} for r in rows],
    )
    conn.commit()
    after = conn.execute("SELECT COUNT(*) FROM security").fetchone()[0]
    return {"received": len(rows), "added": after - before, "total": after,
            "synced_at": now}


def link_existing_stocks(conn: sqlite3.Connection) -> int:
    """Point ``security.stock_id`` at stocks that already exist.

    Only ``promote()`` sets that link, so any stock seeded before the master existed
    -- the whole original hand-built watchlist -- reads as untracked. Anything joining
    on ``stock_id`` (the movers list, search's "tracked" badge) then silently misses
    them. Matching on ticker is safe here because both sides are exchange-issued
    identifiers, not names.
    """
    cur = conn.execute(
        """UPDATE security SET stock_id = (
               SELECT s.id FROM stock s
               WHERE (s.ticker_nse IS NOT NULL AND s.ticker_nse = security.symbol_nse)
                  OR (s.ticker_bse IS NOT NULL AND s.ticker_bse = security.scrip_bse)
               LIMIT 1)
           WHERE stock_id IS NULL AND EXISTS (
               SELECT 1 FROM stock s
               WHERE (s.ticker_nse IS NOT NULL AND s.ticker_nse = security.symbol_nse)
                  OR (s.ticker_bse IS NOT NULL AND s.ticker_bse = security.scrip_bse))"""
    )
    conn.commit()
    return cur.rowcount


def sync(conn: sqlite3.Connection) -> dict:
    """Refresh the whole security master from both exchanges. Idempotent."""
    nse_rows = fetch_nse_listings()
    bse_rows = fetch_bse_listings()
    merged = merge_listings(nse_rows, bse_rows)
    result = save_securities(conn, merged)
    both = sum(1 for r in merged if r["exchanges"] == "NSE,BSE")
    result.update({"nse_rows": len(nse_rows), "bse_rows": len(bse_rows),
                   "dual_listed": both,
                   "linked_to_stocks": link_existing_stocks(conn)})
    return result


# --- Search -----------------------------------------------------------------

def search(conn: sqlite3.Connection, query: str, limit: int = 25,
           exchange: str | None = None) -> list[dict]:
    """Rank securities against a free-text query.

    Ranking is a plain CASE ladder rather than FTS5: with ~7,000 rows a scan costs
    under a millisecond, and this keeps the ordering obvious to read and to change.
    An exact ticker match must always come first -- typing "TCS" and getting
    "TCS Ltd" fourth behind three companies whose *names* contain "tcs" is the
    single most irritating thing a stock search can do.
    """
    term = (query or "").strip()
    if not term:
        return []
    upper, like, prefix = term.upper(), f"%{term.lower()}%", f"{term.lower()}%"

    sql = """
        SELECT isin, symbol_nse, scrip_bse, name, industry, exchanges,
               market_cap, stock_id,
               CASE
                 WHEN UPPER(COALESCE(symbol_nse,'')) = ?      THEN 0
                 WHEN scrip_bse = ?                           THEN 1
                 WHEN UPPER(COALESCE(symbol_nse,'')) LIKE ?   THEN 2
                 WHEN LOWER(name) LIKE ?                      THEN 3
                 ELSE 4
               END AS rank
        FROM security
        WHERE status = 'Active'
          AND (UPPER(COALESCE(symbol_nse,'')) LIKE ?
               OR LOWER(name) LIKE ?
               OR COALESCE(scrip_bse,'') = ?)
    """
    params: list[object] = [upper, term, f"{upper}%", prefix,
                            f"%{upper}%", like, term]
    if exchange in ("NSE", "BSE"):
        sql += " AND exchanges LIKE ?"
        params.append(f"%{exchange}%")
    # market_cap DESC as the tiebreak: within a rank band, the bigger company is
    # overwhelmingly the one being searched for.
    sql += " ORDER BY rank, market_cap DESC NULLS LAST, name LIMIT ?"
    params.append(limit)

    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def get_security(conn: sqlite3.Connection, isin: str) -> dict | None:
    row = conn.execute("SELECT * FROM security WHERE isin=?", (isin,)).fetchone()
    return dict(row) if row else None


def find_security_for_stock(conn: sqlite3.Connection, stock_id: int) -> dict | None:
    """The master row behind a tracked stock, by link or by ticker."""
    row = conn.execute("SELECT * FROM security WHERE stock_id=?", (stock_id,)).fetchone()
    if row:
        return dict(row)
    stock = conn.execute("SELECT ticker_nse, ticker_bse FROM stock WHERE id=?",
                         (stock_id,)).fetchone()
    if stock is None:
        return None
    row = conn.execute(
        """SELECT * FROM security
           WHERE (symbol_nse IS NOT NULL AND symbol_nse = ?)
              OR (scrip_bse IS NOT NULL AND scrip_bse = ?) LIMIT 1""",
        (stock["ticker_nse"], stock["ticker_bse"]),
    ).fetchone()
    return dict(row) if row else None


def promote(conn: sqlite3.Connection, isin: str) -> int:
    """Turn a catalogue entry into a tracked ``stock``. Returns its stock id.

    Idempotent: promoting an already-promoted security returns the existing id
    rather than creating a duplicate.

    The sector is deliberately left unset. BSE's ``industry`` string is not the
    same vocabulary as this project's hand-curated sector templates, and guessing a
    mapping would attach a whole transmission profile -- signed, ``core``-strength
    factor edges -- to a company on the strength of a string match. DESIGN.md 7.2
    calls a wrong direction label at core strength the one error the product cannot
    survive, so an unmapped stock (generic but silent) is the correct default.
    """
    sec = get_security(conn, isin)
    if sec is None:
        raise ValueError(f"unknown ISIN {isin!r}")
    if sec["stock_id"]:
        return int(sec["stock_id"])

    # A stock may already exist from the original hand-seeded watchlist. Claim it
    # rather than inserting a twin: stock's UNIQUE(ticker_nse, ticker_bse) will NOT
    # catch that, because SQLite treats NULLs in a unique index as distinct, so an
    # NSE-only name would happily insert twice.
    existing = conn.execute(
        """SELECT id FROM stock
           WHERE (? IS NOT NULL AND ticker_nse = ?)
              OR (? IS NOT NULL AND ticker_bse = ?) LIMIT 1""",
        (sec["symbol_nse"], sec["symbol_nse"], sec["scrip_bse"], sec["scrip_bse"]),
    ).fetchone()
    if existing:
        conn.execute("UPDATE security SET stock_id=? WHERE isin=?",
                     (existing["id"], isin))
        conn.commit()
        return int(existing["id"])

    from app.watchlist import upsert_stock

    stock_id = upsert_stock(
        conn,
        name=sec["name"],
        ticker_nse=sec["symbol_nse"],
        ticker_bse=sec["scrip_bse"],
        sector_name=None,
        listing_meta={"isin": isin, "exchanges": sec["exchanges"],
                      "industry": sec["industry"],
                      "listing_date": sec["listing_date"]},
    )
    conn.execute("UPDATE security SET stock_id=? WHERE isin=?", (stock_id, isin))
    conn.commit()
    return stock_id
