"""One-shot bootstrap: create the DB, seed the factor registry + sector templates,
and add the five acceptance-criteria stocks to the watchlist.

    python -m scripts.bootstrap
"""

from __future__ import annotations

from app.db import fresh_db
from app.exposure.registry import seed_all
from app.watchlist import upsert_stock, add_to_watchlist

# (name, NSE, BSE, sector-template key)
ACCEPTANCE_STOCKS = [
    ("Tata Consultancy Services", "TCS", "532540", "IT_SERVICES"),
    ("Asian Paints", "ASIANPAINT", "500820", "PAINTS"),
    ("Oil and Natural Gas Corporation", "ONGC", "500312", "UPSTREAM_OIL"),
    ("HDFC Bank", "HDFCBANK", "500180", "BANKS_PRIVATE"),
    ("Maruti Suzuki India", "MARUTI", "532500", "AUTOS"),
]


def main() -> None:
    conn = fresh_db()
    nf, ne = seed_all(conn)
    print(f"Seeded {nf} factors and {ne} sector-template edges.")
    for name, nse, bse, sector in ACCEPTANCE_STOCKS:
        sid = upsert_stock(conn, name=name, ticker_nse=nse, ticker_bse=bse,
                           sector_name=sector)
        add_to_watchlist(conn, sid)
        print(f"  watchlisted {nse} ({sector})")
    print("Bootstrap complete. Run the EOD job with: python -m app.jobs.eod")


if __name__ == "__main__":
    main()
