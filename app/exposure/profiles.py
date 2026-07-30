"""Effective-profile resolution.

Effective profile = the stock's sector-template edges, OVERLAID by that stock's
``status='ratified'`` company override rows. On a ``factor_id`` collision the
company override wins. ``status='draft'`` rows are NEVER included -- that is the
ratification gate, and it is enforced here in code (not by convention).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class ExposureEdge:
    """One resolved transmission edge in a stock's effective profile."""

    factor_id: str
    channel: str
    pnl_line: str | None
    direction: str            # "+1" | "-1" | "COND"
    condition_note: str | None
    strength: str             # core | secondary
    chain_template_text: str
    provenance: str           # template | curator | llm_draft (source of the winning row)
    source_citation: str | None
    status: str               # always "ratified" or "template" in an effective profile

    def to_json_dict(self) -> dict:
        from dataclasses import asdict
        return asdict(self)


def _sector_id_for_stock(conn: sqlite3.Connection, stock_id: int) -> int | None:
    row = conn.execute("SELECT sector_id FROM stock WHERE id=?", (stock_id,)).fetchone()
    return row[0] if row else None


def effective_profile(conn: sqlite3.Connection, stock_id: int) -> list[ExposureEdge]:
    """Resolve the stock's effective (ratified) exposure profile.

    Steps:
      1. Start from sector-template edges for the stock's sector.
      2. Overlay ratified company overrides; a company row replaces the template
         row for the same factor_id.
      3. Draft rows are excluded entirely.
    """
    edges: dict[str, ExposureEdge] = {}

    sector_id = _sector_id_for_stock(conn, stock_id)
    if sector_id is not None:
        for r in conn.execute(
            """SELECT factor_id, channel, pnl_line, direction, condition_note,
                      strength, chain_template_text
               FROM sector_template WHERE sector_id=?""",
            (sector_id,),
        ).fetchall():
            edges[r["factor_id"]] = ExposureEdge(
                factor_id=r["factor_id"], channel=r["channel"], pnl_line=r["pnl_line"],
                direction=r["direction"], condition_note=r["condition_note"],
                strength=r["strength"], chain_template_text=r["chain_template_text"],
                provenance="template", source_citation=None, status="template",
            )

    # Overlay ratified company overrides (draft rows are filtered out by the WHERE clause).
    for r in conn.execute(
        """SELECT factor_id, channel, pnl_line, direction, condition_note, strength,
                  rationale, provenance, source_citation
           FROM exposure
           WHERE stock_id=? AND status='ratified'""",
        (stock_id,),
    ).fetchall():
        # SUPPRESS removes the edge entirely (a ratified curator decision that this
        # stock has no such exposure). It also drops out of the bundle filter.
        if r["direction"] == "SUPPRESS":
            edges.pop(r["factor_id"], None)
            continue

        # The exposure table carries no chain text of its own; reuse the sector chain
        # for the same factor when present, else fall back to the rationale.
        template_chain = (
            edges[r["factor_id"]].chain_template_text if r["factor_id"] in edges else ""
        )
        edges[r["factor_id"]] = ExposureEdge(
            factor_id=r["factor_id"], channel=r["channel"], pnl_line=r["pnl_line"],
            direction=r["direction"], condition_note=r["condition_note"],
            strength=r["strength"],
            chain_template_text=template_chain or (r["rationale"] or ""),
            provenance=r["provenance"], source_citation=r["source_citation"],
            status="ratified",
        )

    return list(edges.values())


def effective_factor_ids(conn: sqlite3.Connection, stock_id: int) -> set[str]:
    """Just the factor_ids in the effective profile -- the bundle-filter allow-list."""
    return {e.factor_id for e in effective_profile(conn, stock_id)}
