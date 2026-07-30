"""Deterministic verifier checks -- each of the six strips a crafted case."""

from __future__ import annotations

from app.attrib.verify import (
    check_evidence_ids_exist, check_factor_in_profile, check_direction,
    check_quotes, check_temporal, check_advice, deterministic_verify,
)


def _bundle(evidence, profile=None):
    return {"date": "2026-07-10", "prev_trading_day": "2026-07-09",
            "idio": -0.03, "sigma_idio": 0.01, "gate_result": "INVESTIGATE",
            "evidence": evidence, "exposure_profile": profile or []}


def _ev(id, tier, headline="h", factor_id=None, first_seen="2026-07-10T09:00:00+05:30", body="body"):
    return {"id": id, "tier": tier, "source": "src", "headline": headline,
            "body_text": body, "factor_id": factor_id, "first_seen_at": first_seen,
            "exchange_dissemination_at": first_seen, "suspect_reactive": False}


def _edge(fid, direction, strength="core"):
    return {"factor_id": fid, "channel": "input_cost", "pnl_line": "gm",
            "direction": direction, "condition_note": None, "strength": strength,
            "chain_template_text": "…", "provenance": "template", "status": "template"}


def test_check1_unknown_evidence_id_strips():
    b = _bundle([_ev(1, 3)])
    assert check_evidence_ids_exist({"evidence_ids": [99]}, b) is not None
    assert check_evidence_ids_exist({"evidence_ids": [1]}, b) is None


def test_check2_factor_not_in_profile_strips():
    b = _bundle([_ev(1, 2, factor_id="CRUDE_BRENT")], profile=[_edge("USDINR", "+1")])
    assert check_factor_in_profile({"factor_id": "CRUDE_BRENT"}, b) is not None
    assert check_factor_in_profile({"factor_id": "USDINR"}, b) is None
    assert check_factor_in_profile({"factor_id": None}, b) is None


def test_check3_direction_contradiction_strips():
    b = _bundle([_ev(2, 2, "Brent crude rose 3%", factor_id="CRUDE_BRENT")],
                profile=[_edge("CRUDE_BRENT", "-1")])
    # crude rose × -1 edge => negative for stock; claiming positive contradicts.
    bad = {"factor_id": "CRUDE_BRENT", "evidence_ids": [2], "direction": "positive"}
    good = {"factor_id": "CRUDE_BRENT", "evidence_ids": [2], "direction": "negative"}
    assert check_direction(bad, b) is not None
    assert check_direction(good, b) is None


def test_check4_fabricated_quote_strips():
    b = _bundle([_ev(1, 1, headline="Results out", body="Net profit fell 10%.")])
    assert check_quotes({"evidence_ids": [1], "quotes": ["profit doubled"]}, b) is not None
    assert check_quotes({"evidence_ids": [1], "quotes": ["Net profit fell 10%."]}, b) is None


def test_check5_evidence_after_close_strips():
    b = _bundle([_ev(1, 1, first_seen="2026-07-10T19:00:00+05:30")])  # after 15:30 close
    assert check_temporal({"evidence_ids": [1]}, b) is not None
    b2 = _bundle([_ev(1, 1, first_seen="2026-07-10T10:00:00+05:30")])
    assert check_temporal({"evidence_ids": [1]}, b2) is None


def test_check6_advice_language_strips():
    assert check_advice({"chain_text": "You should buy this stock", "direction_reason": ""}) is not None
    assert check_advice({"chain_text": "Crude rose, margins compressed", "direction_reason": ""}) is None


def test_deterministic_verify_blanks_advice_residual():
    b = _bundle([_ev(1, 1, first_seen="2026-07-10T10:00:00+05:30")])
    agent_out = {"drivers": [], "residual_note": "Consider a hold here.",
                 "counter_evidence_ids": []}
    survivors, logs, residual = deterministic_verify(agent_out, b)
    assert residual == ""
    assert any(l["stage"] == "det:advice" for l in logs)
