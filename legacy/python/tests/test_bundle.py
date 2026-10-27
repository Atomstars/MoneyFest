"""Bundle assembler tests -- the Constraint-6 structural guarantee."""

from __future__ import annotations

from app.bundle import build_bundle
from app.ingest.normalize import EvidenceItem, upsert_evidence

TARGET = "2026-07-10"
PREV = "2026-07-09"


def _factor_evidence(conn, factor_id, day, tier=2):
    upsert_evidence(conn, EvidenceItem(
        tier=tier, source=f"MACRO:{factor_id}",
        headline=f"{factor_id} moved on {day}", body_text="…",
        factor_id=factor_id, first_seen_at=f"{day}T18:00:00+05:30",
    ))


def _stock_evidence(conn, stock_id, day_time, tier=1, headline="filing"):
    upsert_evidence(conn, EvidenceItem(
        tier=tier, source="NSE", headline=headline, body_text="…",
        stock_id=stock_id, first_seen_at=day_time,
        exchange_dissemination_at=day_time,
    ))


def test_constraint6_unlinked_macro_never_enters_bundle(conn, tcs):
    # FREIGHT_RATES (the "Red Sea" factor) is NOT in TCS's IT_SERVICES profile.
    _factor_evidence(conn, "FREIGHT_RATES", TARGET)
    # USDINR IS in TCS's profile.
    _factor_evidence(conn, "USDINR", TARGET)

    bundle = build_bundle(conn, tcs, TARGET, prev_trading_day=PREV)
    factor_ids = {e["factor_id"] for e in bundle.evidence if e["factor_id"]}

    assert "FREIGHT_RATES" not in factor_ids, "unlinked macro leaked into the bundle"
    assert "USDINR" in factor_ids


def test_tier2_overnight_macro_admitted(conn, tcs):
    # US_FED is in TCS's IT_SERVICES profile. A Fed decision first seen T-1 22:30 IST
    # (prior calendar day, still inside [prev 15:30, today 23:59]) MUST be admitted.
    upsert_evidence(conn, EvidenceItem(
        tier=2, source="MACRO:US_FED", headline="US Fed held rates on 2026-07-09",
        body_text="FOMC decision.", factor_id="US_FED",
        first_seen_at="2026-07-09T22:30:00+05:30",
    ))
    bundle = build_bundle(conn, tcs, TARGET, prev_trading_day=PREV)
    assert any(e["factor_id"] == "US_FED" for e in bundle.evidence), \
        "overnight Tier-2 macro was dropped (window too narrow)"


def test_tier1_within_window_admitted(conn, tcs):
    _stock_evidence(conn, tcs, f"{TARGET}T10:00:00+05:30", tier=1, headline="results")
    bundle = build_bundle(conn, tcs, TARGET, prev_trading_day=PREV)
    assert any(e["tier"] == 1 and e["headline"] == "results" for e in bundle.evidence)


def test_evidence_outside_window_excluded(conn, tcs):
    # First seen two days before the previous trading day's 15:30 boundary.
    _stock_evidence(conn, tcs, "2026-07-07T09:00:00+05:30", tier=3, headline="old news")
    bundle = build_bundle(conn, tcs, TARGET, prev_trading_day=PREV)
    assert not any(e["headline"] == "old news" for e in bundle.evidence)


def test_bundle_is_serialisable_and_frozen(conn, tcs):
    _factor_evidence(conn, "USDINR", TARGET)
    bundle = build_bundle(conn, tcs, TARGET, prev_trading_day=PREV)
    js = bundle.to_json()
    from app.bundle import Bundle
    restored = Bundle.from_json(js)
    assert restored.to_json() == js
    assert restored.stock_id == tcs
