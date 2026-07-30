"""Tier-1 ingestor: NSE & BSE corporate announcement feeds.

These are the Tier-1 backbone. yfinance does not carry announcements, so we scrape
the exchange feeds directly (per DESIGN.md section 1.4). Announcements are mapped to
watchlist stocks by NSE symbol / BSE scrip code, and the exchange's own
dissemination timestamp is captured (trusted for HIGH-confidence timing in Phase 2).

Field notes (learned the hard way -- see STATUS_REPORT.md section 2.1):

* **BSE** serves JSON only when the request carries a bseindia.com ``Referer``;
  without it you get the HTML landing page with a *200*, which used to parse as
  "no announcements". The working endpoint is ``AnnSubCategoryGetData`` (not
  ``AnnGetData``) and the scrip parameter is ``strScrip`` -- capital S.
* **NSE** works, but only after a cookie warm-up GET against a real page, and the
  unparameterised endpoint returns just the latest ~20 announcements *exchange-wide* --
  so a watchlist stock almost never appears in it. Both sources are therefore queried
  **per symbol with an explicit date window**, which is precise and self-healing.

Every fetch failure is now **reported**, never swallowed -- a Tier-1 outage silently
reading as "no news today" is the worst failure this module can have, because
"no Tier-1 evidence" is indistinguishable from "nothing was filed".

Runnable standalone:
    python -m app.ingest.nse_bse
    python -m app.ingest.nse_bse --verify-scrip 500325
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from functools import lru_cache

import yaml

from app.config import (
    NSE_ANNOUNCEMENTS_URL, BSE_ANNOUNCEMENTS_URL, BSE_SCRIP_HEADER_URL,
    HTTP_HEADERS, BSE_HTTP_HEADERS, BSE_SCRIP_MAP_YAML,
)
from app.ingest.normalize import EvidenceItem, upsert_evidence, now_ist_iso

try:
    import httpx
except Exception:  # pragma: no cover
    httpx = None

# How many days back to ask each exchange for on a run. The daily job only needs a day
# or two, but a small window makes the ingestor self-healing after a missed run.
BSE_LOOKBACK_DAYS = 7
NSE_LOOKBACK_DAYS = 7

# NSE's API rejects a client that hasn't visited a real page first (cookie gate).
NSE_WARM_UP_URL = "https://www.nseindia.com/companies-listing/corporate-filings-announcements"


class IngestError(RuntimeError):
    """A Tier-1 source could not be read. Raised so the caller reports it."""


@lru_cache(maxsize=1)
def scrip_map() -> dict[str, str]:
    """NSE ticker -> BSE scrip code, from the hand-verified data/bse_scrip_map.yaml."""
    try:
        doc = yaml.safe_load(open(BSE_SCRIP_MAP_YAML, "r", encoding="utf-8"))
    except FileNotFoundError:  # pragma: no cover
        return {}
    return {str(k).upper(): str(v) for k, v in (doc.get("map") or {}).items()}


def resolve_scrip(ticker: str) -> str | None:
    """BSE scrip code for an NSE ticker, or None if not in the verified map."""
    return scrip_map().get(ticker.upper())


def _stock_maps(conn: sqlite3.Connection) -> tuple[dict[str, int], dict[str, int]]:
    """Return (nse_symbol -> stock_id, bse_scrip -> stock_id) for watchlist stocks.

    A stock with no ``ticker_bse`` column value falls back to the verified scrip map,
    so Tier-1 works for already-onboarded stocks without a DB migration.
    """
    nse: dict[str, int] = {}
    bse: dict[str, int] = {}
    for r in conn.execute(
        """SELECT DISTINCT s.id, s.ticker_nse, s.ticker_bse
           FROM stock s JOIN watchlist_item w ON w.stock_id = s.id"""
    ).fetchall():
        ticker = (r["ticker_nse"] or "").upper()
        if ticker:
            nse[ticker] = r["id"]
        scrip = str(r["ticker_bse"]) if r["ticker_bse"] else resolve_scrip(ticker)
        if scrip:
            bse[scrip] = r["id"]
    return nse, bse


def _fetch_json(url: str, *, params: dict | None = None, headers: dict | None = None,
                warm_up: str | None = None):
    """GET ``url`` and return parsed JSON, or raise IngestError describing the failure.

    Guards the two ways these endpoints lie about success: an HTML body served with a
    200, and a bare JSON string such as ``"No Record Found!"`` where a table was
    expected. Both previously read as "zero announcements".

    ``warm_up`` is a page URL fetched first to pick up cookies -- NSE's API rejects a
    client that has not visited a real page.
    """
    if httpx is None:  # pragma: no cover
        raise IngestError("httpx not installed; cannot fetch live announcements")
    try:
        with httpx.Client(headers=headers or HTTP_HEADERS, timeout=25.0,
                          follow_redirects=True) as c:
            if warm_up:
                try:
                    c.get(warm_up)
                except Exception:  # pragma: no cover - warm-up is best-effort
                    pass
            resp = c.get(url, params=params)
    except Exception as exc:  # pragma: no cover - network variance
        raise IngestError(f"request failed: {type(exc).__name__}: {exc}") from exc

    if resp.status_code != 200:
        raise IngestError(f"HTTP {resp.status_code}")
    ctype = resp.headers.get("content-type", "")
    if "json" not in ctype.lower():
        raise IngestError(f"expected JSON, got {ctype!r} ({len(resp.content)} bytes)")
    try:
        return resp.json()
    except Exception as exc:
        raise IngestError(f"malformed JSON: {exc}") from exc


def verify_scrip(scrip: str) -> str | None:
    """Return the company name BSE reports for ``scrip``, for map verification.

    Used by ``--verify-scrip``. Never guess a scrip code: a wrong one attaches another
    company's filings to a stock (DESIGN.md section 7.2's unsurvivable error).
    """
    data = _fetch_json(BSE_SCRIP_HEADER_URL,
                       params={"Debtflag": "", "scripcode": str(scrip), "seriesid": ""},
                       headers=BSE_HTTP_HEADERS)
    if not isinstance(data, dict):
        return None
    return (data.get("Cmpname") or {}).get("FullN")


def ingest_nse(conn: sqlite3.Connection, *, lookback_days: int = NSE_LOOKBACK_DAYS) -> int:
    """Ingest NSE corporate announcements for watchlist stocks. Returns rows inserted.

    Queried per symbol with an explicit date window: the unparameterised endpoint only
    returns the latest ~20 announcements across the whole exchange, so watchlist stocks
    would almost never appear in it.
    """
    nse_map, _ = _stock_maps(conn)
    if not nse_map:
        return 0

    today = datetime.now().date()
    to_date = today.strftime("%d-%m-%Y")
    from_date = (today - timedelta(days=lookback_days)).strftime("%d-%m-%Y")

    inserted = 0
    failures: list[str] = []
    for symbol, stock_id in nse_map.items():
        try:
            data = _fetch_json(
                NSE_ANNOUNCEMENTS_URL.split("?")[0],
                params={"index": "equities", "symbol": symbol,
                        "from_date": from_date, "to_date": to_date},
                headers=HTTP_HEADERS, warm_up=NSE_WARM_UP_URL,
            )
        except IngestError as exc:
            failures.append(f"{symbol}: {exc}")
            continue
        rows = data if isinstance(data, list) else (data or {}).get("data", [])
        for a in rows:
            if str(a.get("symbol", "")).upper() != symbol:
                continue  # defensive: never attach another company's filing
            headline = a.get("desc") or a.get("subject") or a.get("attchmntText") or ""
            body = a.get("attchmntText") or a.get("smIndustry") or headline
            diss = a.get("an_dt") or a.get("dt") or a.get("sort_date")
            item = EvidenceItem(
                tier=1, source="NSE", headline=headline, body_text=body,
                url=a.get("attchmntFile"), stock_id=stock_id,
                published_at=diss, exchange_dissemination_at=_norm_ts(diss),
                first_seen_at=now_ist_iso(),
            )
            _, ins = upsert_evidence(conn, item)
            inserted += int(ins)

    if failures and not inserted:
        raise IngestError("all NSE symbol queries failed: " + "; ".join(failures[:3]))
    for f in failures:
        print(f"[nse_bse] NSE partial failure {f}")
    return inserted


def _bse_params(scrip: str, prev_date: str, to_date: str) -> dict:
    """Query params for AnnSubCategoryGetData. Note ``strScrip`` -- capital S."""
    return {
        "pageno": "1",
        "strCat": "-1",
        "strPrevDate": prev_date,
        "strScrip": scrip,
        "strSearch": "P",
        "strToDate": to_date,
        "strType": "C",
        "subcategory": "-1",
    }


def ingest_bse(conn: sqlite3.Connection, *, lookback_days: int = BSE_LOOKBACK_DAYS) -> int:
    """Ingest BSE corporate announcements for watchlist stocks. Returns rows inserted.

    Queries per scrip (precise, and only as many requests as there are mapped stocks)
    rather than pulling the whole exchange feed and filtering.
    """
    _, bse_map = _stock_maps(conn)
    if not bse_map:
        return 0

    today = datetime.now().date()
    to_date = today.strftime("%Y%m%d")
    prev_date = (today - timedelta(days=lookback_days)).strftime("%Y%m%d")

    inserted = 0
    failures: list[str] = []
    for scrip, stock_id in bse_map.items():
        try:
            data = _fetch_json(BSE_ANNOUNCEMENTS_URL,
                               params=_bse_params(scrip, prev_date, to_date),
                               headers=BSE_HTTP_HEADERS)
        except IngestError as exc:
            failures.append(f"{scrip}: {exc}")
            continue
        # A bare string ("No Record Found!") means no filings in the window -- normal.
        if isinstance(data, str) or not isinstance(data, dict):
            continue
        for a in data.get("Table") or []:
            headline = a.get("HEADLINE") or a.get("NEWSSUB") or ""
            body = a.get("MORE") or a.get("NEWSSUB") or headline
            diss = a.get("NEWS_DT") or a.get("DT_TM")
            item = EvidenceItem(
                tier=1, source="BSE", headline=headline, body_text=body,
                url=_attachment_url(a.get("ATTACHMENTNAME")), stock_id=stock_id,
                published_at=diss, exchange_dissemination_at=_norm_ts(diss),
                first_seen_at=now_ist_iso(),
            )
            _, ins = upsert_evidence(conn, item)
            inserted += int(ins)

    if failures and not inserted:
        raise IngestError("all BSE scrip queries failed: " + "; ".join(failures[:3]))
    for f in failures:
        print(f"[nse_bse] BSE partial failure {f}")
    return inserted


def _attachment_url(name: str | None) -> str | None:
    """Absolute URL for a BSE announcement PDF, so evidence links are clickable."""
    if not name:
        return None
    return f"https://www.bseindia.com/xml-data/corpfiling/AttachLive/{name}"


def _norm_ts(raw: str | None) -> str | None:
    """Normalise an exchange timestamp to ISO-8601, tolerating fractional seconds.

    BSE emits ``2026-07-25T14:37:43.477``; the plain ``%Y-%m-%dT%H:%M:%S`` pattern
    rejects the fraction, so it is tried explicitly.
    """
    if not raw:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%d-%b-%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
                "%d %b %Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt).isoformat()
        except ValueError:
            continue
    return raw  # keep the raw string if we can't parse it


def ingest_all(conn: sqlite3.Connection) -> int:
    """Run both Tier-1 sources. Returns rows inserted; reports per-source failures.

    One source being down never hides the other, and a total Tier-1 outage is printed
    loudly -- "no Tier-1 evidence" must never be confused with "nothing was filed".
    """
    total = 0
    statuses: list[str] = []
    for name, fn in (("NSE", ingest_nse), ("BSE", ingest_bse)):
        try:
            n = fn(conn)
            total += n
            statuses.append(f"{name}={n}")
        except IngestError as exc:
            statuses.append(f"{name}=UNAVAILABLE({exc})")
    print(f"[nse_bse] Tier-1 " + "  ".join(statuses))
    if all("UNAVAILABLE" in s for s in statuses):
        print("[nse_bse] WARNING: no Tier-1 source reachable -- HIGH-confidence "
              "attribution is impossible this run, and absence of filings cannot "
              "be distinguished from absence of data.")
    return total


def has_tier1_today(conn: sqlite3.Connection, stock_id: int, day: str) -> bool:
    """Did a Tier-1 filing for this stock disseminate on `day` (IST date)?"""
    row = conn.execute(
        """SELECT 1 FROM evidence
           WHERE tier=1 AND stock_id=?
             AND substr(COALESCE(exchange_dissemination_at, first_seen_at),1,10)=?
           LIMIT 1""",
        (stock_id, day),
    ).fetchone()
    return row is not None


if __name__ == "__main__":  # pragma: no cover
    import sys
    if "--verify-scrip" in sys.argv:
        code = sys.argv[sys.argv.index("--verify-scrip") + 1]
        print(f"{code} -> {verify_scrip(code)!r}")
        sys.exit(0)
    from app.db import fresh_db
    c = fresh_db()
    print(f"[nse_bse] inserted {ingest_all(c)} announcement rows")
