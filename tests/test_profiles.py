"""Effective-profile resolution: templates ⊕ ratified overrides; drafts excluded."""

from __future__ import annotations

from app.exposure.profiles import effective_profile, effective_factor_ids
from app.exposure.draft import write_drafts
from app.exposure.ratify import approve_draft, list_drafts


def test_template_only_profile(conn, tcs):
    ids = effective_factor_ids(conn, tcs)
    # IT_SERVICES template seeds USDINR, IT_DEMAND_US, US_FED.
    assert {"USDINR", "IT_DEMAND_US", "US_FED"} <= ids
    # TCS has no crude exposure in the template.
    assert "CRUDE_BRENT" not in ids


def test_draft_rows_never_enter_effective_profile(conn, ongc):
    # ONGC upstream template has CRUDE_BRENT direction +1 (output price).
    before = {e.factor_id: e.direction for e in effective_profile(conn, ongc)}
    assert before["CRUDE_BRENT"] == "+1"

    # A DRAFT override that flips CRUDE_BRENT to -1 must be ignored until ratified.
    write_drafts(conn, ongc, [{
        "factor_id": "CRUDE_BRENT", "channel": "input_cost", "pnl_line": "gross_margin",
        "direction": "-1", "strength": "core", "rationale": "hypothetical flip",
        "source_citation": "test",
    }])
    after = {e.factor_id: e.direction for e in effective_profile(conn, ongc)}
    assert after["CRUDE_BRENT"] == "+1", "draft leaked into the effective profile"


def test_ratified_override_wins_on_collision(conn, ongc):
    write_drafts(conn, ongc, [{
        "factor_id": "CRUDE_BRENT", "channel": "input_cost", "pnl_line": "gross_margin",
        "direction": "-1", "strength": "core", "rationale": "flip after review",
        "source_citation": "annual report p.12",
    }])
    draft_id = list_drafts(conn, ongc)[0]["id"]
    approve_draft(conn, draft_id)

    edges = {e.factor_id: e for e in effective_profile(conn, ongc)}
    assert edges["CRUDE_BRENT"].direction == "-1"
    assert edges["CRUDE_BRENT"].provenance == "llm_draft"
    assert edges["CRUDE_BRENT"].status == "ratified"


def test_suppress_override_removes_edge(conn, tcs):
    # USDINR is a core edge in the IT_SERVICES template.
    assert "USDINR" in effective_factor_ids(conn, tcs)
    # A ratified SUPPRESS override removes it (e.g. a fully-hedged IT firm).
    write_drafts(conn, tcs, [{
        "factor_id": "USDINR", "channel": "revenue_currency", "pnl_line": "revenue",
        "direction": "SUPPRESS", "strength": "core", "rationale": "100% hedged",
        "source_citation": "AR p.7",
    }])
    approve_draft(conn, list_drafts(conn, tcs)[0]["id"])
    assert "USDINR" not in effective_factor_ids(conn, tcs), \
        "SUPPRESS override did not remove the edge"


def test_add_new_edge_via_override(conn, tcs):
    # FREIGHT_RATES is not in the IT template; a ratified override can ADD it.
    write_drafts(conn, tcs, [{
        "factor_id": "FREIGHT_RATES", "channel": "supply_chain", "pnl_line": "cost",
        "direction": "-1", "strength": "secondary", "rationale": "add edge",
        "source_citation": "test",
    }])
    approve_draft(conn, list_drafts(conn, tcs)[0]["id"])
    assert "FREIGHT_RATES" in effective_factor_ids(conn, tcs)
