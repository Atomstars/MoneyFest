"""Golden-set bundles with known-correct answers (source of truth).

20 bundles that SHOULD attribute (expected top factor or a tier-1 event), and 10 that
should honestly come back NO_DRIVER. Built programmatically so profile edge, evidence
move direction, and idio sign are internally consistent (a correct answer is reachable).

`build_golden.py` dumps these to JSON for human inspection; `test_golden.py` runs them
through the real pipeline (marked `llm`, skipped without a key).
"""

from __future__ import annotations

DATE = "2026-07-10"
PREV = "2026-07-09"
IN_WINDOW = f"{DATE}T09:30:00+05:30"       # intraday, before close
PREV_EVENING = f"{PREV}T22:30:00+05:30"    # overnight macro
AFTER_CLOSE = f"{DATE}T19:30:00+05:30"     # after 15:30 close


def _edge(factor_id, direction, strength="core", channel="input_cost", cond=None,
          chain="{factor} {dir} -> channel -> pnl {impact}."):
    return {"factor_id": factor_id, "channel": channel, "pnl_line": "pnl",
            "direction": direction, "condition_note": cond, "strength": strength,
            "chain_template_text": chain, "provenance": "template", "status": "template"}


def _ev(id, tier, headline, factor_id=None, first_seen=IN_WINDOW, diss=None, body=None,
        suspect=False):
    return {"id": id, "tier": tier, "source": f"src{id}", "url": None,
            "headline": headline, "body_text": body or headline, "factor_id": factor_id,
            "published_at": first_seen, "first_seen_at": first_seen,
            "exchange_dissemination_at": diss, "suspect_reactive": suspect}


def _bundle(name, *, idio, move, gate="INVESTIGATE", profile, evidence, sigma_idio=0.012):
    return {
        "stock_id": 1, "ticker": "TEST", "date": DATE, "prev_trading_day": PREV,
        "move": move, "idio": idio, "sigma_idio": sigma_idio, "beta": 1.0,
        "index_move": -0.002, "vol_z": 1.5, "gate_result": gate,
        "exposure_profile": profile, "evidence": evidence, "_name": name,
    }


def _sign_move(word):  # "rose"/"fell"
    return 1 if word == "rose" else -1


def _macro_case(name, factor, edge_dir, move_word, stock_name, channel="input_cost"):
    """A single-factor Tier-2 macro driver case; idio set to the resolved stock sign."""
    resolved = _sign_move(move_word) * (1 if edge_dir == "+1" else -1)
    idio = 0.03 * resolved
    ev = [_ev(2, 2, f"{factor} {move_word} 3% on {DATE}", factor_id=factor)]
    prof = [_edge(factor, edge_dir, channel=channel)]
    return {"name": name, "stock_name": stock_name,
            "bundle": _bundle(name, idio=idio, move=idio, profile=prof, evidence=ev),
            "expect": {"kind": "ATTRIBUTED", "top_factor": factor}}


def _event_case(name, headline, stock_name, direction_sign):
    """A Tier-1 stock-specific event (no factor); idio matches the event direction."""
    idio = 0.04 * direction_sign
    ev = [_ev(1, 1, headline, diss=IN_WINDOW)]
    return {"name": name, "stock_name": stock_name,
            "bundle": _bundle(name, idio=idio, move=idio, profile=[], evidence=ev),
            "expect": {"kind": "ATTRIBUTED", "top_factor": None}}


WITH_DRIVER = [
    _macro_case("crude_vs_paints", "CRUDE_BRENT", "-1", "rose", "Asian Paints"),
    _macro_case("crude_fall_vs_paints", "CRUDE_BRENT", "-1", "fell", "Berger Paints"),
    _macro_case("crude_vs_ongc", "CRUDE_BRENT", "+1", "rose", "ONGC", channel="output_price"),
    _macro_case("usdinr_vs_it", "USDINR", "+1", "rose", "TCS", channel="revenue_currency"),
    _macro_case("usdinr_vs_pharma", "USDINR", "+1", "rose", "Sun Pharma", channel="revenue_currency"),
    _macro_case("steel_vs_autos", "STEEL_HRC", "-1", "rose", "Maruti Suzuki"),
    _macro_case("coal_vs_cement", "COAL", "-1", "rose", "UltraTech Cement"),
    _macro_case("china_vs_metals", "CHINA_DEMAND", "+1", "rose", "Tata Steel", channel="output_price"),
    _macro_case("atf_vs_aviation", "AIRFARE_ATF", "-1", "rose", "IndiGo"),
    _macro_case("gas_vs_upstream", "NATURAL_GAS", "+1", "rose", "ONGC", channel="output_price"),
    _macro_case("gold_vs_jeweller", "GOLD", "+1", "rose", "Titan", channel="output_price"),
    _macro_case("in10y_vs_nbfc", "IN_10Y", "-1", "rose", "Bajaj Finance", channel="funding_cost"),
    _macro_case("us10y_vs_it", "US_10Y", "-1", "rose", "Infosys", channel="demand_driver"),
    _macro_case("freight_vs_importer", "FREIGHT_RATES", "-1", "rose", "Some Importer", channel="supply_chain"),
    _event_case("results_beat", "Q2 net profit beats estimates, revenue up 18%", "HDFC Bank", +1),
    _event_case("results_miss", "Q2 net profit misses estimates, margins fall", "Wipro", -1),
    _event_case("order_win", "Company bags defence order worth 5000 crore", "HAL", +1),
    _event_case("fda_approval", "USFDA grants approval for generic drug", "Cipla", +1),
    _event_case("ratings_downgrade", "CRISIL downgrades long-term rating; outlook negative", "Yes Bank", -1),
    _event_case("mgmt_resign", "CEO resigns with immediate effect", "Some Co", -1),
]


NO_DRIVER = [
    # 1. Pure noise: big idio, only reactive tier-3 chatter written after the move.
    {"name": "noise_tier3_reactive", "stock_name": "Random Co",
     "bundle": _bundle("noise_tier3_reactive", idio=-0.04, move=-0.04, profile=[],
                       evidence=[_ev(3, 3, "Stock slides; traders cite weak sentiment",
                                     first_seen=IN_WINDOW, suspect=True)]),
     "expect": {"kind": "NO_DRIVER"}},
    # 2. Empty bundle — nothing to explain from.
    {"name": "empty_evidence", "stock_name": "Random Co",
     "bundle": _bundle("empty_evidence", idio=-0.045, move=-0.045, profile=[], evidence=[]),
     "expect": {"kind": "NO_DRIVER"}},
    # 3. Tier-1 filing but disseminated AFTER close; the move was intraday.
    {"name": "tier1_after_close", "stock_name": "Random Co",
     "bundle": _bundle("tier1_after_close", idio=-0.05, move=-0.05, profile=[],
                       evidence=[_ev(1, 1, "Board meeting scheduled next week",
                                     first_seen=AFTER_CLOSE, diss=AFTER_CLOSE)]),
     "expect": {"kind": "NO_DRIVER"}},
    # 4. Macro item present but in the WRONG direction (mismatch) — counter only.
    {"name": "direction_mismatch", "stock_name": "Asian Paints",
     "bundle": _bundle("direction_mismatch", idio=+0.04, move=+0.04,
                       profile=[_edge("CRUDE_BRENT", "-1")],
                       evidence=[_ev(2, 2, "Brent crude rose 3%", factor_id="CRUDE_BRENT")]),
     "expect": {"kind": "NO_DRIVER"}},
    # 5. Tier-3 rumour, no factor, no linkage.
    {"name": "tier3_rumour", "stock_name": "Random Co",
     "bundle": _bundle("tier3_rumour", idio=+0.05, move=+0.05, profile=[],
                       evidence=[_ev(3, 3, "Unconfirmed chatter about the company",
                                     suspect=True)]),
     "expect": {"kind": "NO_DRIVER"}},
    # 6. Quiet news day, only an unrelated macro whose factor IS in profile but tiny/irrelevant.
    {"name": "weak_macro_only", "stock_name": "Random Co",
     "bundle": _bundle("weak_macro_only", idio=-0.05, move=-0.05,
                       profile=[_edge("GOLD", "+1", strength="secondary", channel="output_price")],
                       evidence=[_ev(2, 2, "Gold rose 0.2%", factor_id="GOLD")]),
     "expect": {"kind": "NO_DRIVER"}},
    # 7. Two contradicting tier-1 items (net ambiguous).
    {"name": "contradicting_tier1", "stock_name": "Random Co",
     "bundle": _bundle("contradicting_tier1", idio=-0.04, move=-0.04, profile=[],
                       evidence=[_ev(1, 1, "Company wins large order", diss=IN_WINDOW),
                                 _ev(9, 1, "Company loses key client", diss=IN_WINDOW)]),
     "expect": {"kind": "NO_DRIVER"}},
    # 8. Only after-hours tier-3 opinion piece.
    {"name": "afterhours_opinion", "stock_name": "Random Co",
     "bundle": _bundle("afterhours_opinion", idio=-0.06, move=-0.06, profile=[],
                       evidence=[_ev(3, 3, "Why the stock fell today", first_seen=AFTER_CLOSE,
                                     suspect=True)]),
     "expect": {"kind": "NO_DRIVER"}},
    # 9. Macro present, factor NOT in profile (belt-and-braces on the bundle filter).
    {"name": "factor_not_in_profile", "stock_name": "Random Co",
     "bundle": _bundle("factor_not_in_profile", idio=-0.05, move=-0.05,
                       profile=[_edge("USDINR", "+1", channel="revenue_currency")],
                       evidence=[_ev(2, 2, "Steel HRC rose 4%", factor_id="STEEL_HRC")]),
     "expect": {"kind": "NO_DRIVER"}},
    # 10. Large move, stale unrelated tier-3.
    {"name": "stale_unrelated", "stock_name": "Random Co",
     "bundle": _bundle("stale_unrelated", idio=+0.06, move=+0.06, profile=[],
                       evidence=[_ev(3, 3, "Sector outlook piece from earlier in the week",
                                     first_seen=f"{PREV}T10:00:00+05:30")]),
     "expect": {"kind": "NO_DRIVER"}},
]


ALL_CASES = WITH_DRIVER + NO_DRIVER
