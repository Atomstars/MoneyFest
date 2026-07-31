"""Backfill-on-open: the path that lets a user open any of ~5,000 listed names.

Offline -- the price download is stubbed. What matters here is the guard behaviour:
the gate needs GateConfig.min_lookback days before it can say anything, and every
way that can fail must return a renderable status rather than raise.
"""

from __future__ import annotations

from app.config import GATE_CONFIG
from app.jobs.backfill import ensure_history, history_status
from app.tools.prices import PriceSeries


def _seed_metrics(conn, stock_id, n, start="2026-01-01"):
    from datetime import date, timedelta
    d0 = date.fromisoformat(start)
    conn.executemany(
        """INSERT INTO daily_metric (stock_id, date, close, gate_result, gate_inputs_json)
           VALUES (?,?,?,?,'{}')""",
        [(stock_id, (d0 + timedelta(days=i)).isoformat(), 100.0 + i, "NOISE")
         for i in range(n)],
    )
    conn.commit()


def test_history_status_uses_the_gates_own_floor(conn, tcs):
    status = history_status(conn, tcs)
    assert status["days"] == 0
    assert status["warm"] is False
    # Not an arbitrary number: below this every classification is WARMING_UP.
    assert status["min_required"] == GATE_CONFIG.min_lookback


def test_history_status_turns_warm_at_the_floor(conn, tcs):
    _seed_metrics(conn, tcs, GATE_CONFIG.min_lookback)
    status = history_status(conn, tcs)
    assert status["days"] == GATE_CONFIG.min_lookback
    assert status["warm"] is True


def test_already_warm_stock_is_a_cheap_no_op(conn, tcs, monkeypatch):
    """Clicking through five stocks must not re-download five times."""
    _seed_metrics(conn, tcs, 60)

    def boom(*a, **k):
        raise AssertionError("must not download for an already-warm stock")

    monkeypatch.setattr("app.tools.prices.download_prices", boom)
    result = ensure_history(conn, tcs)
    assert result["status"] == "already_warm"
    assert result["written"] == 0


def test_bse_only_scrip_reports_why_it_cannot_be_priced(conn):
    """yfinance's .BO symbols do not reliably resolve -- SHIP_NOTES already flags
    this as why the second price source is absent. Say so, don't fail obscurely."""
    from app.watchlist import upsert_stock
    stock_id = upsert_stock(conn, name="BSE Only Ltd", ticker_nse=None,
                            ticker_bse="590104", sector_name=None)
    result = ensure_history(conn, stock_id)
    assert result["status"] == "no_nse_symbol"
    assert "BSE-only" in result["message"]


def test_unknown_stock_returns_status_not_exception(conn):
    assert ensure_history(conn, 99999)["status"] == "unknown_stock"


def test_empty_price_history_is_a_normal_outcome(conn, tcs, monkeypatch):
    """A delisted or illiquid scrip with no yfinance history is something the UI
    renders, not an error that takes the page down."""
    monkeypatch.setattr("app.tools.prices.download_prices",
                        lambda *a, **k: PriceSeries(ticker="X", dates=[], adj_close=[]))
    result = ensure_history(conn, tcs)
    assert result["status"] == "no_price_history"
    assert result["written"] == 0


def test_price_fetch_failure_is_caught(conn, tcs, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("yfinance exploded")

    monkeypatch.setattr("app.tools.prices.download_prices", boom)
    result = ensure_history(conn, tcs)
    assert result["status"] == "price_fetch_failed"
    assert "yfinance exploded" in result["message"]


def test_backfill_writes_metrics_and_warms_the_stock(conn, tcs, monkeypatch):
    from datetime import date, timedelta

    d0 = date.fromisoformat("2026-01-01")
    n = 80
    dates = [(d0 + timedelta(days=i)).isoformat() for i in range(n)]
    # Deterministic zig-zag so returns are non-zero and beta is estimable.
    stock = PriceSeries(ticker="TCS.NS", dates=dates,
                        adj_close=[100.0 + (i % 7) + i * 0.4 for i in range(n)],
                        volume=[1000.0] * n)
    index = PriceSeries(ticker="^NSEI", dates=dates,
                        adj_close=[200.0 + (i % 5) + i * 0.3 for i in range(n)],
                        volume=[0.0] * n)

    def fake_download(ticker, start, end):
        return index if ticker == "^NSEI" else stock

    monkeypatch.setattr("app.tools.prices.download_prices", fake_download)
    # The index cache is module-level and shared across calls; bypass it here.
    monkeypatch.setattr("app.jobs.backfill._index_series",
                        lambda start, end: index)

    result = ensure_history(conn, tcs)
    assert result["status"] == "backfilled"
    assert result["written"] == n - 1  # the first bar has no prior close
    assert result["warm"] is True

    rows = conn.execute(
        "SELECT COUNT(*) FROM daily_metric WHERE stock_id=? AND close IS NOT NULL",
        (tcs,),
    ).fetchone()[0]
    assert rows == n - 1
