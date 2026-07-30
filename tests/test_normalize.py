"""Evidence normalisation: body_hash dedupe, suspect_reactive flag, Tier-3 tagging."""

from __future__ import annotations

from app.ingest.normalize import EvidenceItem, upsert_evidence, body_hash
from app.ingest.news import tag_item


def test_body_hash_dedupe_is_idempotent(conn):
    item = EvidenceItem(tier=3, source="wire", headline="TCS wins deal",
                        body_text="Big BFSI deal.", first_seen_at="2026-07-10T11:00:00+05:30")
    id1, ins1 = upsert_evidence(conn, item)
    # A republished copy with different whitespace hashes the same.
    dup = EvidenceItem(tier=3, source="other-wire", headline="TCS   wins deal",
                       body_text="Big BFSI deal.", first_seen_at="2026-07-10T12:00:00+05:30")
    id2, ins2 = upsert_evidence(conn, dup)
    assert ins1 is True and ins2 is False
    assert id1 == id2
    assert body_hash("TCS wins deal", "Big BFSI deal.") == \
        body_hash("TCS   wins deal", "Big BFSI deal.")


def test_suspect_reactive_after_cutoff(conn):
    # Tier-3, first seen after 09:30 IST on the move day -> suspect_reactive.
    late = EvidenceItem(tier=3, source="wire", headline="Why TCS fell",
                        body_text="Analysts say…", first_seen_at="2026-07-10T14:00:00+05:30")
    eid, _ = upsert_evidence(conn, late, move_day="2026-07-10")
    row = conn.execute("SELECT suspect_reactive FROM evidence WHERE id=?", (eid,)).fetchone()
    assert row["suspect_reactive"] == 1


def test_not_suspect_before_cutoff(conn):
    early = EvidenceItem(tier=3, source="wire", headline="TCS pre-open note",
                         body_text="…", first_seen_at="2026-07-10T08:00:00+05:30")
    eid, _ = upsert_evidence(conn, early, move_day="2026-07-10")
    row = conn.execute("SELECT suspect_reactive FROM evidence WHERE id=?", (eid,)).fetchone()
    assert row["suspect_reactive"] == 0


def test_tier1_never_suspect(conn):
    late_t1 = EvidenceItem(tier=1, source="NSE", headline="Board meeting outcome",
                           body_text="…", first_seen_at="2026-07-10T20:00:00+05:30")
    eid, _ = upsert_evidence(conn, late_t1, move_day="2026-07-10")
    row = conn.execute("SELECT suspect_reactive FROM evidence WHERE id=?", (eid,)).fetchone()
    assert row["suspect_reactive"] == 0


def test_tag_item_matches_stock_and_factor():
    stock_tokens = {1: ["tata consultancy services", "tcs"]}
    kw = {"USDINR": ["rupee", "usdinr"], "CRUDE_BRENT": ["brent", "crude"]}
    stocks, factors = tag_item(
        "TCS gains as rupee weakens", "The rupee slid against the dollar.",
        stock_tokens, kw,
    )
    assert 1 in stocks
    assert "USDINR" in factors
    assert "CRUDE_BRENT" not in factors
