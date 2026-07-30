"""Portfolio valuation tests -- pure arithmetic over stored closes, no network."""

from __future__ import annotations

import pytest

from app.portfolio import (
    upsert_holding, remove_holding, positions, summary, allocation, history,
)


def _metric(conn, stock_id, date, close, gate="NOISE"):
    conn.execute(
        """INSERT INTO daily_metric (stock_id, date, close, gate_result, gate_inputs_json)
           VALUES (?,?,?,?,'{}')
           ON CONFLICT(stock_id, date) DO UPDATE SET close=excluded.close""",
        (stock_id, date, close, gate),
    )
    conn.commit()


def test_pnl_and_day_change(conn, tcs):
    _metric(conn, tcs, "2026-07-29", 100.0)
    _metric(conn, tcs, "2026-07-30", 110.0)
    upsert_holding(conn, tcs, qty=10, avg_cost=90.0)

    p = positions(conn)[0]
    assert p["invested"] == pytest.approx(900.0)
    assert p["market_value"] == pytest.approx(1100.0)
    assert p["pnl"] == pytest.approx(200.0)
    assert p["pnl_pct"] == pytest.approx(200 / 900)
    # Day change is vs the previous stored close, not vs cost.
    assert p["day_change"] == pytest.approx(100.0)
    assert p["day_change_pct"] == pytest.approx(0.10)


def test_summary_totals_and_weights(conn, tcs, ongc):
    _metric(conn, tcs, "2026-07-30", 100.0)
    _metric(conn, ongc, "2026-07-30", 100.0)
    upsert_holding(conn, tcs, qty=30, avg_cost=50.0)
    upsert_holding(conn, ongc, qty=10, avg_cost=50.0)

    s = summary(conn)
    assert s["total_value"] == pytest.approx(4000.0)
    assert s["total_invested"] == pytest.approx(2000.0)
    assert s["total_pnl"] == pytest.approx(2000.0)
    weights = {p["ticker"]: p["weight"] for p in s["positions"]}
    assert weights["TCS"] == pytest.approx(0.75)
    assert weights["ONGC"] == pytest.approx(0.25)


def test_unpriced_position_is_reported_not_zeroed(conn, tcs, ongc):
    """A missing close must never read as a real loss."""
    _metric(conn, tcs, "2026-07-30", 100.0)
    upsert_holding(conn, tcs, qty=10, avg_cost=50.0)
    upsert_holding(conn, ongc, qty=10, avg_cost=50.0)  # no price for ONGC

    s = summary(conn)
    assert s["priced_positions"] == 1
    assert s["unpriced_positions"] == 1
    ongc_pos = next(p for p in s["positions"] if p["ticker"] == "ONGC")
    assert ongc_pos["market_value"] is None
    assert ongc_pos["pnl"] is None          # not 0, not -500
    # Totals cover only what could be valued.
    assert s["total_value"] == pytest.approx(1000.0)
    assert s["total_invested"] == pytest.approx(500.0)


def test_negative_qty_rejected(conn, tcs):
    with pytest.raises(ValueError):
        upsert_holding(conn, tcs, qty=-5, avg_cost=100.0)


def test_upsert_replaces_and_remove_deletes(conn, tcs):
    _metric(conn, tcs, "2026-07-30", 100.0)
    upsert_holding(conn, tcs, qty=10, avg_cost=50.0)
    upsert_holding(conn, tcs, qty=25, avg_cost=60.0)
    assert len(positions(conn)) == 1
    assert positions(conn)[0]["qty"] == 25

    remove_holding(conn, tcs)
    assert positions(conn) == []


def test_allocation_groups_by_sector(conn, tcs, ongc):
    _metric(conn, tcs, "2026-07-30", 100.0)
    _metric(conn, ongc, "2026-07-30", 100.0)
    upsert_holding(conn, tcs, qty=30, avg_cost=1.0)
    upsert_holding(conn, ongc, qty=10, avg_cost=1.0)

    alloc = {a["sector"]: a["weight"] for a in allocation(conn)}
    assert alloc["IT_SERVICES"] == pytest.approx(0.75)
    assert alloc["UPSTREAM_OIL"] == pytest.approx(0.25)


def test_history_skips_days_missing_any_position(conn, tcs, ongc):
    """A day where one holding lacks a close must be omitted, not undercounted."""
    _metric(conn, tcs, "2026-07-29", 100.0)
    _metric(conn, ongc, "2026-07-29", 100.0)
    _metric(conn, tcs, "2026-07-30", 110.0)   # ONGC missing on the 30th
    upsert_holding(conn, tcs, qty=1, avg_cost=1.0)
    upsert_holding(conn, ongc, qty=1, avg_cost=1.0)

    h = history(conn)
    assert [d["date"] for d in h] == ["2026-07-29"]
    assert h[0]["value"] == pytest.approx(200.0)
