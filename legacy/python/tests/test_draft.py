"""Drafting pipeline: rows land as draft/llm_draft, never ratified; validation holds."""

from __future__ import annotations

import pytest

from app.exposure.draft import write_drafts, _validate_row, _build_schema
from app.exposure.registry import VALID_CHANNELS


def test_write_drafts_forces_draft_status_and_provenance(conn, tcs):
    write_drafts(conn, tcs, [{
        "factor_id": "USDINR", "channel": "revenue_currency", "pnl_line": "revenue",
        "direction": "+1", "strength": "core", "rationale": "90% hedged? no -- test",
        "source_citation": "AR p.4",
    }])
    row = conn.execute(
        "SELECT status, provenance FROM exposure WHERE stock_id=? AND factor_id='USDINR'",
        (tcs,),
    ).fetchone()
    assert row["status"] == "draft"
    assert row["provenance"] == "llm_draft"


def test_no_code_path_writes_ratified_from_drafter(conn, tcs):
    write_drafts(conn, tcs, [{
        "factor_id": "IT_DEMAND_US", "channel": "demand_driver", "pnl_line": "revenue",
        "direction": "+1", "strength": "core", "rationale": "test",
        "source_citation": "test",
    }])
    ratified = conn.execute(
        "SELECT COUNT(*) FROM exposure WHERE stock_id=? AND status='ratified'", (tcs,)
    ).fetchone()[0]
    assert ratified == 0


def test_validate_row_rejects_unknown_factor():
    with pytest.raises(ValueError):
        _validate_row(
            {"factor_id": "NOT_A_FACTOR", "channel": "input_cost",
             "direction": "+1", "strength": "core"},
            known_factor_ids={"USDINR"},
        )


def test_validate_row_rejects_bad_channel():
    with pytest.raises(ValueError):
        _validate_row(
            {"factor_id": "USDINR", "channel": "made_up_channel",
             "direction": "+1", "strength": "core"},
            known_factor_ids={"USDINR"},
        )


def test_validate_row_requires_condition_note_for_cond():
    with pytest.raises(ValueError):
        _validate_row(
            {"factor_id": "USDINR", "channel": "revenue_currency",
             "direction": "COND", "strength": "core"},
            known_factor_ids={"USDINR"},
        )


def test_schema_enums_are_closed(conn):
    factor_ids = [r[0] for r in conn.execute("SELECT id FROM factor").fetchall()]
    schema = _build_schema(factor_ids)
    item = schema["properties"]["rows"]["items"]
    assert set(item["properties"]["channel"]["enum"]) == VALID_CHANNELS
    assert set(item["properties"]["factor_id"]["enum"]) == set(factor_ids)
