"""Offline self-validation of the golden set (no LLM).

Proves each of the 20 attributable bundles is reachable (feeding the pipeline an ideal
agent output yields ATTRIBUTED with the expected top factor), and that the
deterministically-catchable NO_DRIVER cases are filtered even when the agent is tempted
into a driver. This guards the dataset itself without needing an API key.
"""

from __future__ import annotations

import pytest

from app.attrib.pipeline import process_bundle
from tests.conftest import FakeLLMClient
from tests.golden.dataset import WITH_DRIVER

_PASS = FakeLLMClient({"verdict": "pass", "reason": "entailed"})


def _ideal_agent_out(case):
    b = case["bundle"]
    factor = case["expect"]["top_factor"]
    ev = b["evidence"]
    ev_id = ev[0]["id"]
    direction = "positive" if b["idio"] > 0 else "negative"
    return {"drivers": [{
        "rank": 1, "evidence_ids": [ev_id], "factor_id": factor,
        "chain_text": "Factor moved through its channel; margin/revenue effect follows.",
        "direction": direction, "direction_reason": "resolved from the exposure edge",
        "confidence_claim": "MEDIUM", "quotes": [ev[0]["headline"]],
    }], "residual_note": "", "counter_evidence_ids": []}


@pytest.mark.parametrize("case", WITH_DRIVER, ids=[c["name"] for c in WITH_DRIVER])
def test_with_driver_cases_are_reachable(case):
    res = process_bundle(case["bundle"], case["stock_name"],
                         verifier_client=_PASS, agent_out=_ideal_agent_out(case))
    assert res["outcome"] == "ATTRIBUTED", case["name"]
    assert res["drivers"][0]["factor_id"] == case["expect"]["top_factor"], case["name"]


def _tempted(bundle, factor, ev_id, direction):
    return {"drivers": [{
        "rank": 1, "evidence_ids": [ev_id], "factor_id": factor,
        "chain_text": "Factor moved; effect follows.", "direction": direction,
        "direction_reason": "tempted link", "confidence_claim": "HIGH",
        "quotes": [],
    }], "residual_note": "", "counter_evidence_ids": []}


@pytest.mark.parametrize("name,factor,ev_id,direction", [
    ("direction_mismatch", "CRUDE_BRENT", 2, "negative"),  # rubric demotes vs +idio
    ("tier1_after_close", None, 1, "negative"),            # temporal strip
    ("factor_not_in_profile", "STEEL_HRC", 2, "negative"), # factor-not-in-profile strip
    ("weak_macro_only", "GOLD", 2, "positive"),            # rubric demotes vs -idio
])
def test_deterministically_catchable_no_driver(name, factor, ev_id, direction):
    from tests.golden.dataset import NO_DRIVER
    case = next(c for c in NO_DRIVER if c["name"] == name)
    res = process_bundle(case["bundle"], case["stock_name"],
                         verifier_client=_PASS,
                         agent_out=_tempted(case["bundle"], factor, ev_id, direction))
    assert res["outcome"] == "NO_DRIVER", name
