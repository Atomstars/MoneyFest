"""Golden-set evaluation -- runs the REAL two-call pipeline (LLM).

Marked ``llm`` and skipped unless a credential exists for the *currently configured*
provider (``app.config.LLM_PROVIDER`` -- "groq" needs GROQ_API_KEY, "anthropic" needs
ANTHROPIC_API_KEY), so CI stays offline-safe under either backend. Reports top-driver
hit rate on the 20 attributable cases, NO_DRIVER honesty on the 10, and a per-stage
strip-rate. Run explicitly with:

    pytest -m llm -s tests/test_golden.py
"""

from __future__ import annotations

import os
import collections

import pytest

from app.attrib.pipeline import process_bundle
from app.config import LLM_PROVIDER
from tests.golden.dataset import WITH_DRIVER, NO_DRIVER

_PROVIDER_ENV = {"groq": "GROQ_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}
_credential_var = _PROVIDER_ENV.get(LLM_PROVIDER, "ANTHROPIC_API_KEY")

pytestmark = [
    pytest.mark.llm,
    pytest.mark.skipif(
        not os.environ.get(_credential_var),
        reason=f"{_credential_var} not set for provider {LLM_PROVIDER!r}; golden LLM run skipped",
    ),
]


def _top_factor_ok(result, expected_factor):
    if result["outcome"] != "ATTRIBUTED" or not result["drivers"]:
        return False
    return result["drivers"][0].get("factor_id") == expected_factor


def test_golden_set():
    strip_counts = collections.Counter()

    hits = 0
    for case in WITH_DRIVER:
        res = process_bundle(case["bundle"], case["stock_name"])
        strip_counts.update(l["stage"] for l in res["verifier_log"])
        if _top_factor_ok(res, case["expect"]["top_factor"]):
            hits += 1
    hit_rate = hits / len(WITH_DRIVER)

    honest = 0
    for case in NO_DRIVER:
        res = process_bundle(case["bundle"], case["stock_name"])
        strip_counts.update(l["stage"] for l in res["verifier_log"])
        if res["outcome"] == "NO_DRIVER":
            honest += 1

    print("\n=== GOLDEN REPORT ===")
    print(f"top-driver hit rate (20): {hits}/{len(WITH_DRIVER)} = {hit_rate:.0%}")
    print(f"NO_DRIVER honesty (10):   {honest}/{len(NO_DRIVER)}")
    print("strip-rate by stage:", dict(strip_counts))

    # NO_DRIVER honesty is the load-bearing safety metric (DESIGN 7 honourable mention).
    assert honest >= 8, f"NO_DRIVER honesty too low: {honest}/10 (tighten the prompt)"
    # Coverage regression guard on the attributable set.
    assert hit_rate >= 0.6, f"top-driver hit rate too low: {hit_rate:.0%}"
