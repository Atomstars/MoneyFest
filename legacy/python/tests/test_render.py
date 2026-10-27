"""Rendering tests for ATTRIBUTED / NO_DRIVER, including the no-advice guard."""

from __future__ import annotations

import pytest

from app.render import render_attributed, render_no_driver


def _bundle():
    return {"date": "2026-07-10", "prev_trading_day": "2026-07-09",
            "move": -0.031, "idio": -0.028, "sigma_idio": 0.011}


def _driver(chain_text="Crude rose -> input costs up -> margin down -> negative.",
            confidence="MEDIUM", direction="negative"):
    return {
        "confidence": confidence, "confidence_reason": "Tier-2 core edge, direction matches",
        "needs_condition": False, "condition_note": None,
        "chain_text": chain_text, "direction": direction, "direction_reason": "input cost",
        "cited": [{"id": 2, "tier": 2, "source": "MACRO:CRUDE_BRENT",
                   "headline": "Brent crude rose 3%", "first_seen_at": "2026-07-10T09:00:00+05:30",
                   "exchange_dissemination_at": None, "url": None}],
    }


def test_render_attributed_happy_path():
    text = render_attributed("Asian Paints", _bundle(), [_driver()],
                             residual_note="part of the move remains unexplained")
    assert "Asian Paints" in text
    assert "Medium confidence" in text
    assert "unexplained" in text


def test_render_attributed_rejects_advice_language():
    bad = _driver(chain_text="This is a strong buy at these levels")
    with pytest.raises(AssertionError):
        render_attributed("Asian Paints", _bundle(), [bad])


def test_render_attributed_limits_to_max():
    drivers = [_driver() for _ in range(5)]
    text = render_attributed("X", _bundle(), drivers, max_drivers=2)
    assert "3. " not in text  # only two rendered


def test_render_no_driver_states_sigma_and_possibilities():
    text = render_no_driver("Some Co", _bundle())
    assert "No attributable driver" in text
    assert "sigma" in text
    assert "block deals" in text
