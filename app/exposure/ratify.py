"""Ratification CLI -- the human gate that turns drafts into production edges.

Lists ``status='draft'`` rows, shows each against the current effective profile, and
lets a curator approve / reject / edit row-by-row. Approving promotes the row to
``status='ratified'`` and stamps ``last_reviewed_at``; only THIS module writes
``ratified``. The drafting tool (exposure/draft.py) can never produce a ratified row.

Usage:
    python -m app.exposure.ratify --stock TCS            # interactive review
    python -m app.exposure.ratify --stock TCS --list     # just list drafts
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone

from app.exposure.profiles import effective_profile


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_drafts(conn: sqlite3.Connection, stock_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT id, factor_id, channel, pnl_line, direction, condition_note,
                  strength, rationale, source_citation
           FROM exposure WHERE stock_id=? AND status='draft'
           ORDER BY factor_id""",
        (stock_id,),
    ).fetchall()


def approve_draft(conn: sqlite3.Connection, draft_id: int) -> None:
    """Promote a draft row to ratified, replacing any existing ratified row for its factor."""
    row = conn.execute(
        "SELECT stock_id, factor_id FROM exposure WHERE id=? AND status='draft'",
        (draft_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"no draft row with id {draft_id}")
    stock_id, factor_id = row["stock_id"], row["factor_id"]
    # Remove any currently-ratified row for the same (stock, factor) so the unique
    # (stock_id, factor_id, status) index doesn't block the promotion.
    conn.execute(
        "DELETE FROM exposure WHERE stock_id=? AND factor_id=? AND status='ratified'",
        (stock_id, factor_id),
    )
    conn.execute(
        "UPDATE exposure SET status='ratified', last_reviewed_at=? WHERE id=?",
        (now_iso(), draft_id),
    )
    conn.commit()


def reject_draft(conn: sqlite3.Connection, draft_id: int) -> None:
    conn.execute("DELETE FROM exposure WHERE id=? AND status='draft'", (draft_id,))
    conn.commit()


def edit_draft(conn: sqlite3.Connection, draft_id: int, **fields) -> None:
    """Edit selected fields of a draft row in place (before approval)."""
    allowed = {"channel", "pnl_line", "direction", "condition_note", "strength",
               "rationale", "source_citation"}
    sets = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not sets:
        return
    assignments = ", ".join(f"{k}=?" for k in sets)
    conn.execute(
        f"UPDATE exposure SET {assignments} WHERE id=? AND status='draft'",
        (*sets.values(), draft_id),
    )
    conn.commit()


def _current_edge(conn: sqlite3.Connection, stock_id: int, factor_id: str):
    for e in effective_profile(conn, stock_id):
        if e.factor_id == factor_id:
            return e
    return None


def _resolve_stock_id(conn: sqlite3.Connection, ticker: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM stock WHERE ticker_nse=? OR ticker_bse=?", (ticker, ticker)
    ).fetchone()
    return row[0] if row else None


def _review_interactive(conn: sqlite3.Connection, stock_id: int) -> None:  # pragma: no cover
    drafts = list_drafts(conn, stock_id)
    if not drafts:
        print("No draft rows to review.")
        return
    for d in drafts:
        cur = _current_edge(conn, stock_id, d["factor_id"])
        print("\n" + "=" * 60)
        print(f"DRAFT #{d['id']}  factor={d['factor_id']}")
        print(f"  proposed: channel={d['channel']} direction={d['direction']} "
              f"strength={d['strength']} pnl_line={d['pnl_line']}")
        if d["condition_note"]:
            print(f"  condition: {d['condition_note']}")
        print(f"  rationale: {d['rationale']}")
        print(f"  citation:  {d['source_citation']}")
        if cur is None:
            print("  current effective edge: (none -- this would ADD an edge)")
        else:
            print(f"  current effective edge: channel={cur.channel} "
                  f"direction={cur.direction} strength={cur.strength} "
                  f"provenance={cur.provenance}")
        choice = input("  [a]pprove / [r]eject / [s]kip ? ").strip().lower()
        if choice == "a":
            approve_draft(conn, d["id"])
            print("  -> ratified.")
        elif choice == "r":
            reject_draft(conn, d["id"])
            print("  -> rejected (deleted).")
        else:
            print("  -> skipped.")


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description="Ratify LLM-drafted exposure overrides")
    ap.add_argument("--stock", required=True, help="NSE ticker, e.g. TCS")
    ap.add_argument("--list", action="store_true", help="list drafts and exit")
    args = ap.parse_args(argv)

    from app.db import fresh_db
    conn = fresh_db()
    stock_id = _resolve_stock_id(conn, args.stock)
    if stock_id is None:
        print(f"Stock {args.stock!r} not found.")
        return 1

    if args.list:
        for d in list_drafts(conn, stock_id):
            print(f"#{d['id']}  {d['factor_id']:16s} {d['direction']:>4s} "
                  f"{d['channel']:14s} {d['strength']}")
        return 0

    _review_interactive(conn, stock_id)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
