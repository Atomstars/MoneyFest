"""Attribution pipeline end-to-end, driven by injected fake LLM clients (no network)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from app.attrib.pipeline import process_bundle, run_pending
from tests.conftest import FakeLLMClient


def _bundle(idio=-0.03, profile=None, evidence=None, move=-0.03):
    return {
        "date": "2026-07-10", "prev_trading_day": "2026-07-09",
        "idio": idio, "sigma_idio": 0.01, "gate_result": "INVESTIGATE",
        "move": move, "beta": 1.0, "index_move": -0.002, "vol_z": 1.0,
        "exposure_profile": profile or [{
            "factor_id": "CRUDE_BRENT", "channel": "input_cost", "pnl_line": "gm",
            "direction": "-1", "condition_note": None, "strength": "core",
            "chain_template_text": "Crude {dir} -> …", "provenance": "template",
            "status": "template"}],
        "evidence": evidence or [{
            "id": 2, "tier": 2, "source": "MACRO:CRUDE_BRENT",
            "headline": "Brent crude rose 3%", "body_text": "Brent crude rose 3%.",
            "factor_id": "CRUDE_BRENT", "first_seen_at": "2026-07-10T09:00:00+05:30",
            "exchange_dissemination_at": None, "suspect_reactive": False}],
    }


_AGENT_HIT = {"drivers": [{
    "rank": 1, "evidence_ids": [2], "factor_id": "CRUDE_BRENT",
    "chain_text": "Crude rose so input costs rose, margin fell, negative.",
    "direction": "negative", "direction_reason": "input cost channel",
    "confidence_claim": "HIGH", "quotes": ["Brent crude rose 3%"]}],
    "residual_note": "", "counter_evidence_ids": []}

_PASS = {"verdict": "pass", "reason": "entailed"}
_FAIL = {"verdict": "fail", "reason": "not entailed"}


def test_attributed_end_to_end():
    res = process_bundle(_bundle(), "Asian Paints",
                         verifier_client=FakeLLMClient(_PASS), agent_out=_AGENT_HIT)
    assert res["outcome"] == "ATTRIBUTED"
    assert len(res["drivers"]) == 1
    assert res["drivers"][0]["confidence"] == "MEDIUM"
    assert "Asian Paints" in res["rendered_text"]


def test_empty_agent_is_no_driver():
    res = process_bundle(_bundle(), "Asian Paints",
                         agent_out={"drivers": [], "residual_note": "", "counter_evidence_ids": []})
    assert res["outcome"] == "NO_DRIVER"
    assert "No attributable driver" in res["rendered_text"]


def test_verifier_fail_yields_no_driver():
    res = process_bundle(_bundle(), "Asian Paints",
                         verifier_client=FakeLLMClient(_FAIL), agent_out=_AGENT_HIT)
    assert res["outcome"] == "NO_DRIVER"
    assert any(l["stage"] == "llm" for l in res["verifier_log"])


def test_direction_mismatch_becomes_no_driver_with_counter():
    # idio positive but crude-rose × input-cost => negative -> mismatch, demoted.
    res = process_bundle(_bundle(idio=+0.03, move=+0.03), "Asian Paints",
                         verifier_client=FakeLLMClient(_PASS), agent_out=_AGENT_HIT)
    assert res["outcome"] == "NO_DRIVER"
    assert any(l["stage"] == "rubric" for l in res["verifier_log"])


def test_run_pending_persists(conn, ongc):
    # Direction-consistent bundle (crude rose × -1 input-cost edge => negative == idio).
    bundle = _bundle()
    conn.execute(
        """INSERT INTO attribution (stock_id, date, trigger, outcome, bundle_json, created_at)
           VALUES (?,?,?,?,?,?)""",
        (ongc, "2026-07-10", "move", "PENDING_ATTRIBUTION", json.dumps(bundle),
         datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()

    summaries = run_pending(conn, agent_client=FakeLLMClient(_AGENT_HIT),
                            verifier_client=FakeLLMClient(_PASS))
    assert summaries and summaries[0]["outcome"] == "ATTRIBUTED"

    row = conn.execute(
        "SELECT outcome, model_version, verifier_log_json FROM attribution WHERE stock_id=?",
        (ongc,),
    ).fetchone()
    assert row["outcome"] == "ATTRIBUTED"
    assert "agent=" in row["model_version"]
    ndrivers = conn.execute(
        """SELECT COUNT(*) FROM driver d JOIN attribution a ON a.id=d.attribution_id
           WHERE a.stock_id=?""", (ongc,)).fetchone()[0]
    assert ndrivers == 1
