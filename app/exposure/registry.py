"""Factor registry + sector-template loaders.

Seeds the ``factor``, ``sector`` and ``sector_template`` tables from the two
canonical YAML files. Idempotent: safe to run repeatedly (upserts by primary key).
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

import yaml

from app.config import FACTORS_YAML, SECTOR_TEMPLATES_YAML

VALID_CHANNELS = {
    "input_cost", "output_price", "revenue_currency", "cost_currency",
    "funding_cost", "demand_driver", "regulatory", "supply_chain", "competitive",
}
VALID_DIRECTIONS = {"+1", "-1", "COND"}          # sector templates: no SUPPRESS
OVERRIDE_DIRECTIONS = VALID_DIRECTIONS | {"SUPPRESS"}  # company overrides may remove an edge
VALID_STRENGTHS = {"core", "secondary"}


def _load_yaml(path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def seed_factors(conn: sqlite3.Connection, path=FACTORS_YAML) -> int:
    """Load factors.yaml into the factor table. Returns rows written."""
    doc = _load_yaml(path)
    rows = doc.get("factors", [])
    n = 0
    for f in rows:
        if f["kind"] not in ("series", "event"):
            raise ValueError(f"factor {f['id']}: bad kind {f['kind']!r}")
        conn.execute(
            """INSERT INTO factor (id, name, kind, series_source, keywords, tier, unit, description)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 name=excluded.name, kind=excluded.kind,
                 series_source=excluded.series_source, keywords=excluded.keywords,
                 tier=excluded.tier, unit=excluded.unit, description=excluded.description""",
            (
                f["id"], f["name"], f["kind"], f.get("series_source"),
                json.dumps(f.get("keywords", [])),
                2 if f["kind"] == "series" else 3,
                f.get("unit"), f.get("description"),
            ),
        )
        n += 1
    conn.commit()
    return n


def seed_sector_templates(conn: sqlite3.Connection, path=SECTOR_TEMPLATES_YAML) -> int:
    """Load sector_templates.yaml. Creates sector rows on demand. Returns edges written."""
    doc = _load_yaml(path)
    version = doc.get("version", "unversioned")
    sectors = doc.get("sectors", {})
    edges = 0
    for sector_name, sector_edges in sectors.items():
        cur = conn.execute(
            """INSERT INTO sector (name, template_version) VALUES (?, ?)
               ON CONFLICT(name) DO UPDATE SET template_version=excluded.template_version
               RETURNING id""",
            (sector_name, version),
        )
        sector_id = cur.fetchone()[0]
        for e in sector_edges:
            _validate_edge(sector_name, e)
            conn.execute(
                """INSERT INTO sector_template
                     (sector_id, factor_id, channel, pnl_line, direction,
                      condition_note, strength, chain_template_text)
                   VALUES (?,?,?,?,?,?,?,?)
                   ON CONFLICT(sector_id, factor_id) DO UPDATE SET
                     channel=excluded.channel, pnl_line=excluded.pnl_line,
                     direction=excluded.direction, condition_note=excluded.condition_note,
                     strength=excluded.strength,
                     chain_template_text=excluded.chain_template_text""",
                (
                    sector_id, e["factor_id"], e["channel"], e.get("pnl_line"),
                    str(e["direction"]), e.get("condition_note"), e["strength"],
                    e["chain_template_text"],
                ),
            )
            edges += 1
    conn.commit()
    return edges


def _validate_edge(sector_name: str, e: dict) -> None:
    fid = e.get("factor_id")
    if e["channel"] not in VALID_CHANNELS:
        raise ValueError(f"{sector_name}/{fid}: bad channel {e['channel']!r}")
    if str(e["direction"]) not in VALID_DIRECTIONS:
        raise ValueError(f"{sector_name}/{fid}: bad direction {e['direction']!r}")
    if e["strength"] not in VALID_STRENGTHS:
        raise ValueError(f"{sector_name}/{fid}: bad strength {e['strength']!r}")
    if str(e["direction"]) == "COND" and not e.get("condition_note"):
        raise ValueError(f"{sector_name}/{fid}: COND edge needs a condition_note")


def seed_all(conn: sqlite3.Connection) -> tuple[int, int]:
    """Seed factors then templates (templates FK the factor table). Validates FKs."""
    nf = seed_factors(conn)
    # Cross-check every template factor_id exists in the registry (closed vocabulary).
    known = {r[0] for r in conn.execute("SELECT id FROM factor").fetchall()}
    doc = _load_yaml(SECTOR_TEMPLATES_YAML)
    for sector_name, edges in doc.get("sectors", {}).items():
        for e in edges:
            if e["factor_id"] not in known:
                raise ValueError(
                    f"{sector_name}: factor {e['factor_id']!r} not in registry "
                    f"(closed vocabulary violation)"
                )
    ne = seed_sector_templates(conn)
    return nf, ne


def known_factor_ids(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute("SELECT id FROM factor").fetchall()}


def factor_keywords(conn: sqlite3.Connection) -> dict[str, list[str]]:
    """Map factor_id -> keyword list, for the Tier-3 tagger."""
    out: dict[str, list[str]] = {}
    for r in conn.execute("SELECT id, keywords FROM factor").fetchall():
        out[r[0]] = json.loads(r[1] or "[]")
    return out


if __name__ == "__main__":  # pragma: no cover
    from app.db import fresh_db
    c = fresh_db()
    nf, ne = seed_all(c)
    print(f"Seeded {nf} factors and {ne} sector-template edges.")
