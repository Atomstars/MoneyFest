"""Tier-2 ingestor: macro factor series.

For every ``kind=series`` factor that has a fetchable ``series_source``, download the
daily series and emit one evidence row per day whose |log move| >= that factor's own
60-day 1-sigma. Each row is tagged with the factor_id (no stock_id -- Tier-2 items
reach a stock's bundle only via the exposure filter, never directly).

Runnable standalone:  python -m app.ingest.macro
"""

from __future__ import annotations

import sqlite3
from statistics import pstdev

from app.config import GATE_CONFIG
from app.ingest.normalize import EvidenceItem, upsert_evidence
from app.tools.gate import log_returns

try:
    from app.tools.prices import download_prices, default_window
except Exception:  # pragma: no cover
    download_prices = None


def _series_factors(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, name, series_source, unit FROM factor "
        "WHERE kind='series' AND series_source IS NOT NULL AND series_source != ''"
    ).fetchall()


def ingest_series(conn: sqlite3.Connection, lookback_days: int = 200) -> int:
    """Emit evidence for material daily moves in each fetchable macro series.

    A move is 'material' when |daily log return| >= the series' own trailing 1-sigma.
    Returns the number of new evidence rows inserted.
    """
    if download_prices is None:  # pragma: no cover
        raise RuntimeError("prices tool unavailable (yfinance not installed)")

    start, end = default_window(lookback_days)
    inserted = 0
    for f in _series_factors(conn):
        try:
            series = download_prices(f["series_source"], start, end)
        except Exception as exc:  # pragma: no cover - network variance
            print(f"[macro] fetch failed for {f['id']} ({f['series_source']}): {exc}")
            continue
        if len(series.adj_close) < GATE_CONFIG.min_lookback:
            continue
        rets = log_returns(series.adj_close)
        # Trailing sigma over the lookback window (whole available series here).
        sigma = pstdev(rets[-GATE_CONFIG.lookback:]) if len(rets) >= 2 else 0.0
        if sigma == 0:
            continue
        # returns[i] corresponds to the move INTO dates[i+1].
        for i, r in enumerate(rets):
            if abs(r) < sigma:
                continue
            day = series.dates[i + 1]
            direction_word = "rose" if r > 0 else "fell"
            headline = f"{f['name']} {direction_word} {abs(r) * 100:.2f}% on {day}"
            body = (f"{f['name']} ({f['series_source']}) {direction_word} "
                    f"{abs(r) * 100:.2f}% (>= 1-sigma of {sigma * 100:.2f}%) on {day}. "
                    f"Unit: {f['unit']}.")
            item = EvidenceItem(
                tier=2, source=f"MACRO:{f['series_source']}",
                headline=headline, body_text=body, factor_id=f["id"],
                published_at=day + "T18:00:00", first_seen_at=day + "T18:00:00",
            )
            _, ins = upsert_evidence(conn, item)
            inserted += int(ins)
    return inserted


def ingest_all(conn: sqlite3.Connection) -> int:
    return ingest_series(conn)


if __name__ == "__main__":  # pragma: no cover
    from app.db import fresh_db
    c = fresh_db()
    print(f"[macro] inserted {ingest_all(c)} macro-move evidence rows")
