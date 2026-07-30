"""Rubric decision-table tests -- every level and every cap, with synthetic drivers."""

from __future__ import annotations

from app.attrib.rubric import (
    score_driver, classify_event, text_move_sign, CONF_ORDER,
)


def _bundle(*, idio=-0.03, sigma_idio=0.01, gate="INVESTIGATE",
            evidence=None, profile=None):
    return {
        "date": "2026-07-10", "prev_trading_day": "2026-07-09",
        "idio": idio, "sigma_idio": sigma_idio, "gate_result": gate,
        "evidence": evidence or [], "exposure_profile": profile or [],
    }


def _ev(id, tier, headline, factor_id=None, diss=None, first_seen=None, body=""):
    return {"id": id, "tier": tier, "source": "src", "headline": headline,
            "body_text": body, "factor_id": factor_id,
            "exchange_dissemination_at": diss,
            "first_seen_at": first_seen or diss or "2026-07-10T09:00:00+05:30",
            "suspect_reactive": False}


def _edge(factor_id, direction, strength="core", cond=None):
    return {"factor_id": factor_id, "channel": "input_cost", "pnl_line": "gm",
            "direction": direction, "condition_note": cond, "strength": strength,
            "chain_template_text": "…", "provenance": "template", "status": "template"}


# --- helper functions ------------------------------------------------------

def test_text_move_sign():
    assert text_move_sign("Brent crude rose 3%") == 1
    assert text_move_sign("Steel fell 2%") == -1
    assert text_move_sign("no direction word here") == 0


def test_classify_event():
    assert classify_event("Q2 net profit beats estimates") == "results"
    assert classify_event("Company bags order worth 500cr") == "order_win"
    assert classify_event("random chatter") is None


# --- HIGH ------------------------------------------------------------------

def test_high_tier1_sameday_unambiguous_matches():
    b = _bundle(idio=-0.03, evidence=[
        _ev(1, 1, "Q2 net profit misses estimates", diss="2026-07-10T09:00:00+05:30"),
    ])
    d = {"rank": 1, "evidence_ids": [1], "factor_id": None, "direction": "negative"}
    level, reason, cond = score_driver(d, b)
    assert level == "HIGH"


# --- MEDIUM ----------------------------------------------------------------

def test_medium_tier2_core_edge_matches():
    b = _bundle(idio=-0.03,
                profile=[_edge("CRUDE_BRENT", "-1", "core")],
                evidence=[_ev(2, 2, "Brent crude rose 3%", factor_id="CRUDE_BRENT")])
    d = {"rank": 1, "evidence_ids": [2], "factor_id": "CRUDE_BRENT", "direction": "negative"}
    level, reason, cond = score_driver(d, b)
    assert level == "MEDIUM"


# --- LOW -------------------------------------------------------------------

def test_low_tier3_only():
    b = _bundle(idio=-0.03, evidence=[_ev(3, 3, "Traders say the stock fell on sentiment")])
    d = {"rank": 1, "evidence_ids": [3], "factor_id": None, "direction": "negative"}
    level, reason, cond = score_driver(d, b)
    assert level == "LOW"


def test_low_secondary_strength_edge():
    b = _bundle(idio=-0.03,
                profile=[_edge("CRUDE_BRENT", "-1", "secondary")],
                evidence=[_ev(2, 2, "Brent crude rose 3%", factor_id="CRUDE_BRENT")])
    d = {"rank": 1, "evidence_ids": [2], "factor_id": "CRUDE_BRENT", "direction": "negative"}
    level, _, _ = score_driver(d, b)
    assert level == "LOW"


# --- caps ------------------------------------------------------------------

def test_mixed_gate_caps_at_medium():
    b = _bundle(idio=-0.03, gate="MIXED", evidence=[
        _ev(1, 1, "Q2 net profit misses estimates", diss="2026-07-10T09:00:00+05:30"),
    ])
    d = {"rank": 1, "evidence_ids": [1], "factor_id": None, "direction": "negative"}
    level, _, _ = score_driver(d, b)
    assert level == "MEDIUM"  # would be HIGH, capped by MIXED


def test_cond_edge_caps_and_flags_condition():
    b = _bundle(idio=-0.03,
                profile=[_edge("RBI_REPO", "COND", "core", cond="regime-dependent")],
                evidence=[_ev(2, 2, "RBI repo rose 25bps", factor_id="RBI_REPO")])
    d = {"rank": 1, "evidence_ids": [2], "factor_id": "RBI_REPO", "direction": "negative"}
    level, reason, needs_cond = score_driver(d, b)
    assert needs_cond is True
    assert CONF_ORDER[level] <= CONF_ORDER["MEDIUM"]


# --- direction-mismatch demotion ------------------------------------------

def test_direction_mismatch_demotes_to_counter_evidence():
    # idio positive, but crude-rose × input-cost edge implies negative -> mismatch.
    b = _bundle(idio=+0.03,
                profile=[_edge("CRUDE_BRENT", "-1", "core")],
                evidence=[_ev(2, 2, "Brent crude rose 3%", factor_id="CRUDE_BRENT")])
    d = {"rank": 1, "evidence_ids": [2], "factor_id": "CRUDE_BRENT", "direction": "negative"}
    level, reason, _ = score_driver(d, b)
    assert level is None  # demoted, not a driver


def test_high_blocked_by_tier1_counter_evidence():
    b = _bundle(idio=-0.03, evidence=[
        _ev(1, 1, "Q2 net profit misses estimates", diss="2026-07-10T09:00:00+05:30"),
        _ev(9, 1, "Board approves buyback", diss="2026-07-10T09:30:00+05:30"),
    ])
    d = {"rank": 1, "evidence_ids": [1], "factor_id": None, "direction": "negative"}
    level, _, _ = score_driver(d, b, counter_evidence_ids=[9])
    assert level != "HIGH"  # a tier-1 counter-item blocks HIGH
