"""OFFLINE LLM drafting pipeline -- proposes company override rows.

This is the ONLY place in the whole system that calls an LLM, and it is explicitly
out of the daily loop. Given a stock and a filing-text file (e.g. an annual-report
extract), it asks Claude to fill a FIXED JSON schema restricted to:

  * the closed factor vocabulary (factor ids that exist in the registry), and
  * the closed channel enum.

Claude fills a form; it does not invent factors or channels. Every proposed row is
written with ``status='draft'``, ``provenance='llm_draft'`` and a ``source_citation``.

Structural guarantee: this tool CANNOT write ``status='ratified'``. The insert helper
hard-codes ``'draft'`` and there is no code path that sets any other status. Only the
ratification CLI (exposure/ratify.py) promotes a row to ratified.

Usage:
    python -m app.exposure.draft --stock TCS --filing path/to/extract.txt
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys

from app.config import ATTRIBUTION_MODEL
from app.exposure.registry import VALID_CHANNELS, OVERRIDE_DIRECTIONS, VALID_STRENGTHS

# Same model as the daily attribution agent -- provider-aware (see app/config.py).
MODEL = ATTRIBUTION_MODEL

# Hard invariant enforced in code, not by prompt.
FORCED_STATUS = "draft"
FORCED_PROVENANCE = "llm_draft"


def _build_schema(factor_ids: list[str]) -> dict:
    """A strict JSON schema: factor_id and channel are closed enums."""
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "rows": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "factor_id": {"type": "string", "enum": sorted(factor_ids)},
                        "channel": {"type": "string", "enum": sorted(VALID_CHANNELS)},
                        "pnl_line": {"type": "string"},
                        "direction": {"type": "string", "enum": sorted(OVERRIDE_DIRECTIONS)},
                        "condition_note": {"type": "string"},
                        "strength": {"type": "string", "enum": sorted(VALID_STRENGTHS)},
                        "rationale": {"type": "string"},
                        "source_citation": {"type": "string"},
                    },
                    "required": [
                        "factor_id", "channel", "pnl_line", "direction",
                        "strength", "rationale", "source_citation",
                    ],
                },
            }
        },
        "required": ["rows"],
    }


SYSTEM = (
    "You are a research assistant helping a curator draft company-specific exposure "
    "overrides for an Indian equity. You are filling a FIXED FORM: you may only "
    "reference factor ids and channels from the provided closed lists. Do NOT invent "
    "factors or channels. Propose an override row only when the filing text gives "
    "concrete evidence that this company's exposure differs from a generic sector "
    "template (e.g. a hedging policy, a pricing regime, a fuel-mix change, an "
    "output-price linkage). Every row must cite the specific phrase in the filing that "
    "supports it in source_citation. Use direction=+1 when a RISE in the factor is good "
    "for the company, -1 when bad, COND when it depends (then fill condition_note). "
    "Prefer proposing nothing over guessing."
)


def draft_overrides(
    conn: sqlite3.Connection,
    stock_ticker: str,
    filing_text: str,
    *,
    model: str = MODEL,
    client=None,
) -> list[dict]:
    """Call Claude to propose override rows. Returns validated draft dicts (not yet written).

    Network/LLM call via the shared app.llm helper. ``client`` is injectable for tests.
    """
    from app.llm import structured_call

    factor_ids = [r[0] for r in conn.execute("SELECT id FROM factor").fetchall()]
    schema = _build_schema(factor_ids)

    user = (
        f"Stock: {stock_ticker}\n\n"
        f"Closed factor vocabulary: {', '.join(sorted(factor_ids))}\n"
        f"Closed channel enum: {', '.join(sorted(VALID_CHANNELS))}\n\n"
        f"Filing extract:\n\"\"\"\n{filing_text}\n\"\"\"\n\n"
        "Return override rows per the schema. Use direction=SUPPRESS to REMOVE a "
        "sector-template edge that clearly does not apply to this company."
    )
    parsed = structured_call(
        model=model, system=SYSTEM, user=user, schema=schema,
        tool_name="emit_overrides", client=client,
    )
    rows = parsed.get("rows", [])
    return [_validate_row(r, set(factor_ids)) for r in rows]


def _validate_row(row: dict, known_factor_ids: set[str]) -> dict:
    """Belt-and-braces validation on top of the schema enums."""
    if row["factor_id"] not in known_factor_ids:
        raise ValueError(f"draft references unknown factor {row['factor_id']!r}")
    if row["channel"] not in VALID_CHANNELS:
        raise ValueError(f"draft has bad channel {row['channel']!r}")
    if str(row["direction"]) not in OVERRIDE_DIRECTIONS:
        raise ValueError(f"draft has bad direction {row['direction']!r}")
    if row["strength"] not in VALID_STRENGTHS:
        raise ValueError(f"draft has bad strength {row['strength']!r}")
    if str(row["direction"]) == "COND" and not row.get("condition_note"):
        raise ValueError("COND draft row needs a condition_note")
    return row


def write_drafts(conn: sqlite3.Connection, stock_id: int, rows: list[dict]) -> int:
    """Persist proposed rows. status is HARD-CODED to 'draft'; provenance to 'llm_draft'.

    There is deliberately no parameter to override status. Returns rows written.
    """
    n = 0
    for r in rows:
        conn.execute(
            """INSERT INTO exposure
                 (stock_id, factor_id, channel, pnl_line, direction, condition_note,
                  strength, rationale, provenance, source_citation, status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(stock_id, factor_id, status) DO UPDATE SET
                 channel=excluded.channel, pnl_line=excluded.pnl_line,
                 direction=excluded.direction, condition_note=excluded.condition_note,
                 strength=excluded.strength, rationale=excluded.rationale,
                 source_citation=excluded.source_citation""",
            (
                stock_id, r["factor_id"], r["channel"], r.get("pnl_line"),
                str(r["direction"]), r.get("condition_note"), r["strength"],
                r.get("rationale"), FORCED_PROVENANCE, r.get("source_citation"),
                FORCED_STATUS,  # <-- cannot be anything else
            ),
        )
        n += 1
    conn.commit()
    return n


def _resolve_stock_id(conn: sqlite3.Connection, ticker: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM stock WHERE ticker_nse=? OR ticker_bse=?", (ticker, ticker)
    ).fetchone()
    return row[0] if row else None


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description="Offline LLM exposure-override drafter")
    ap.add_argument("--stock", required=True, help="NSE ticker, e.g. TCS")
    ap.add_argument("--filing", required=True, help="path to filing-text extract")
    args = ap.parse_args(argv)

    from app.db import fresh_db
    conn = fresh_db()
    stock_id = _resolve_stock_id(conn, args.stock)
    if stock_id is None:
        print(f"Stock {args.stock!r} not found. Add it to the watchlist first.")
        return 1
    with open(args.filing, "r", encoding="utf-8") as fh:
        filing_text = fh.read()

    rows = draft_overrides(conn, args.stock, filing_text)
    written = write_drafts(conn, stock_id, rows)
    print(f"Wrote {written} DRAFT override rows for {args.stock} "
          f"(status=draft, provenance=llm_draft). Review with app.exposure.ratify.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
