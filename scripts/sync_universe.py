"""Refresh the NSE+BSE security master.

    python -m scripts.sync_universe

Idempotent and safe to re-run: rows are upserted on ISIN and ``stock_id`` links to
already-tracked names are preserved. Worth running weekly -- new listings appear and
delisted ones flip status.

``--check`` re-verifies the BSE scrip codes in data/bse_scrip_map.yaml against the
codes the ISIN join derives, which is the cheap way to catch a hand-typed mistake in
that file (a wrong code silently attaches another company's filings to a stock).
"""

from __future__ import annotations

import argparse
import sys

from app.db import fresh_db
from app.universe import UniverseError, sync


def _check_scrip_map(conn) -> int:
    """Compare data/bse_scrip_map.yaml against ISIN-derived codes. Returns exit code."""
    import yaml

    from app.config import BSE_SCRIP_MAP_YAML

    if not BSE_SCRIP_MAP_YAML.exists():
        print("no bse_scrip_map.yaml to check")
        return 0
    doc = yaml.safe_load(BSE_SCRIP_MAP_YAML.read_text(encoding="utf-8")) or {}
    mapping = doc.get("map", doc) if isinstance(doc, dict) else {}
    mapping = {k: v for k, v in mapping.items() if k != "version"}

    problems = 0
    for symbol, code in (mapping or {}).items():
        row = conn.execute(
            "SELECT scrip_bse, name FROM security WHERE UPPER(symbol_nse)=?",
            (str(symbol).upper(),),
        ).fetchone()
        if row is None:
            print(f"  ?  {symbol}: not in the NSE listing file")
            continue
        derived = row["scrip_bse"]
        if derived is None:
            print(f"  ?  {symbol}: no BSE listing found via ISIN")
        elif str(derived) != str(code):
            print(f"  !! {symbol}: yaml says {code}, ISIN join says {derived} "
                  f"({row['name']})")
            problems += 1
        else:
            print(f"  ok {symbol}: {code}")
    return 1 if problems else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="verify data/bse_scrip_map.yaml against the ISIN join")
    args = parser.parse_args()

    conn = fresh_db()
    try:
        result = sync(conn)
    except UniverseError as exc:
        print(f"universe sync FAILED: {exc}", file=sys.stderr)
        return 2

    print(f"NSE listings : {result['nse_rows']:>6}")
    print(f"BSE listings : {result['bse_rows']:>6}")
    print(f"dual-listed  : {result['dual_listed']:>6}")
    print(f"securities   : {result['total']:>6}  (+{result['added']} new)")

    if args.check:
        print("\nverifying data/bse_scrip_map.yaml against the ISIN join:")
        return _check_scrip_map(conn)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
