"""Reference-data layer: return windows, the TTL cache, and quote fallback.

Offline throughout -- every fetcher is stubbed. The point of these tests is the
behaviour around the network calls, not the calls themselves: what happens on a
partial series, on an upstream failure, and on a stock with no price at all.
"""

from __future__ import annotations

import math

import pytest

from app.marketdata.cache import cached, read_cache, write_cache
from app.marketdata.quotes import _num, get_quote
from app.marketdata.windows import WINDOWS, return_windows, series_stats


# --- Return windows ---------------------------------------------------------

def _daily(n: int, start_price: float = 100.0, step: float = 1.0,
           start_date: str = "2026-01-01") -> list[tuple[str, float]]:
    """n consecutive calendar days. Consecutive keeps the arithmetic obvious."""
    from datetime import date, timedelta
    d0 = date.fromisoformat(start_date)
    return [((d0 + timedelta(days=i)).isoformat(), start_price + i * step)
            for i in range(n)]


def test_window_with_no_basis_is_none_not_zero():
    """A fabricated 0% would be a made-up number -- the one thing this product
    must never produce. Two weeks of history cannot report a 1Y return."""
    windows = return_windows(_daily(14))
    assert windows["1W"] is not None
    assert windows["1Y"] is None
    assert windows["5Y"] is None


def test_windows_are_calendar_anchored_not_row_counted():
    """Row counting silently lies across gaps -- holidays, suspensions, partial
    backfills -- and this series has all three."""
    series = [("2026-01-01", 100.0), ("2026-01-02", 101.0),
              # a three-week hole
              ("2026-01-31", 200.0), ("2026-02-01", 210.0)]
    one_month = return_windows(series)["1M"]
    assert one_month is not None
    # 30 calendar days before 2026-02-01 is 2026-01-02, whose close is 101.
    assert one_month["from_date"] == "2026-01-02"
    assert one_month["pct"] == pytest.approx((210.0 - 101.0) / 101.0)


def test_window_pct_is_a_fraction():
    windows = return_windows(_daily(40, start_price=100.0, step=0.0)
                             + [("2026-03-01", 110.0)])
    assert windows["1M"]["pct"] == pytest.approx(0.10)


def test_non_finite_and_nonpositive_closes_are_dropped():
    """yfinance emits NaN for an opened-but-unsettled session, and NaN passes every
    `> 0` guard because all NaN comparisons are False (CLAUDE.md)."""
    series = _daily(30) + [("2026-02-01", float("nan")), ("2026-02-02", 0.0),
                           ("2026-02-03", 150.0)]
    windows = return_windows(series)
    assert windows["1M"] is not None
    assert math.isfinite(windows["1M"]["pct"])
    assert windows["1M"]["to_close"] == 150.0


def test_empty_series_yields_all_none():
    assert return_windows([]) == {label: None for label in WINDOWS}


def test_as_of_ignores_later_closes():
    series = _daily(60)
    windows = return_windows(series, as_of="2026-02-01")
    assert windows["1M"]["to_date"] == "2026-02-01"


def test_series_stats_reports_its_own_coverage():
    """52w high/low come from OUR stored closes so they agree with the chart beside
    them -- which means a thin backfill must say how thin it is."""
    stats = series_stats(_daily(100))
    assert stats["high_52w"] == 199.0
    assert stats["low_52w"] == 100.0
    assert stats["band_position"] == pytest.approx(1.0)
    assert stats["covers_days"] == 99


def test_series_stats_flat_band_has_no_position():
    stats = series_stats([("2026-01-01", 50.0), ("2026-01-02", 50.0)])
    assert stats["band_position"] is None


# --- TTL cache --------------------------------------------------------------

def test_cache_roundtrip(conn, tcs):
    write_cache(conn, tcs, "key_stats", {"pe": 17.0}, "BSE")
    entry = read_cache(conn, tcs, "key_stats")
    assert entry["payload"] == {"pe": 17.0}
    assert entry["source"] == "BSE"
    assert entry["age_seconds"] < 5


def test_cached_serves_fresh_without_refetching(conn, tcs):
    calls = []

    def fetch():
        calls.append(1)
        return {"n": len(calls)}, "src"

    first = cached(conn, tcs, "key_stats", 3600, fetch)
    second = cached(conn, tcs, "key_stats", 3600, fetch)
    assert first["payload"] == second["payload"] == {"n": 1}
    assert len(calls) == 1


def test_cached_refetches_once_stale(conn, tcs):
    calls = []

    def fetch():
        calls.append(1)
        return {"n": len(calls)}, "src"

    cached(conn, tcs, "key_stats", 3600, fetch)
    # ttl=0 makes anything already stored stale.
    entry = cached(conn, tcs, "key_stats", 0, fetch)
    assert entry["payload"] == {"n": 2}
    assert entry["stale"] is False


def test_cached_serves_expired_data_when_refresh_fails(conn, tcs):
    """Yesterday's market cap beats a blank panel -- as long as we say it is stale."""
    cached(conn, tcs, "key_stats", 3600, lambda: ({"pe": 17.0}, "BSE"))

    def boom():
        raise RuntimeError("upstream down")

    entry = cached(conn, tcs, "key_stats", 0, boom)
    assert entry["payload"] == {"pe": 17.0}
    assert entry["stale"] is True


def test_cached_returns_none_when_nothing_fresh_or_stored(conn, tcs):
    assert cached(conn, tcs, "key_stats", 0, lambda: None) is None


def test_cached_treats_a_none_fetch_as_failure_not_a_value(conn, tcs):
    """A fetcher returning None means 'upstream had nothing usable', which must not
    overwrite a good cached payload with emptiness."""
    cached(conn, tcs, "profile", 3600, lambda: ({"summary": "x"}, "yfinance"))
    entry = cached(conn, tcs, "profile", 0, lambda: None)
    assert entry["payload"] == {"summary": "x"}
    assert entry["stale"] is True


# --- Quotes -----------------------------------------------------------------

def test_num_parses_bse_formatted_strings():
    assert _num("2,431.90") == 2431.90
    assert _num("  17.05 ") == 17.05
    assert _num(None) is None
    assert _num("n/a") is None
    assert _num("nan") is None


def test_quote_falls_back_to_stored_close(conn, tcs, monkeypatch):
    """With both networked sources unavailable, our own EOD close is the answer --
    and it is labelled with its date rather than implying a live tick."""
    monkeypatch.setattr("app.marketdata.quotes.fetch_bse_quote",
                        lambda scrip: (_ for _ in ()).throw(RuntimeError("no net")))
    monkeypatch.setattr("app.marketdata.quotes.fetch_yf_quote", lambda sym: None)
    conn.execute(
        """INSERT INTO daily_metric (stock_id, date, close, gate_result, gate_inputs_json)
           VALUES (?,?,?,?,?), (?,?,?,?,?)""",
        (tcs, "2026-07-28", 100.0, "NOISE", "{}",
         tcs, "2026-07-29", 110.0, "NOISE", "{}"),
    )
    conn.commit()

    quote = get_quote(conn, tcs)
    assert quote["source"] == "stored_close"
    assert quote["price"] == 110.0
    assert quote["change_pct"] == pytest.approx(0.10)
    assert "2026-07-29" in quote["disclaimer"]


def test_quote_with_no_data_at_all_is_explicit(conn, tcs, monkeypatch):
    monkeypatch.setattr("app.marketdata.quotes.fetch_bse_quote", lambda scrip: None)
    monkeypatch.setattr("app.marketdata.quotes.fetch_yf_quote", lambda sym: None)
    quote = get_quote(conn, tcs)
    assert quote["source"] == "none"
    assert quote["price"] is None


def test_quote_prefers_bse_and_marks_itself_delayed(conn, tcs, monkeypatch):
    monkeypatch.setattr(
        "app.marketdata.quotes.fetch_bse_quote",
        lambda scrip: ({"price": 2365.8, "prev_close": 2431.9, "change": -66.1,
                        "change_pct": -0.0272, "open": None, "high": None,
                        "low": None, "delayed": True,
                        "disclaimer": "Delayed price — not a live feed."}, "BSE"),
    )
    quote = get_quote(conn, tcs, force=True)
    assert quote["source"] == "BSE"
    assert quote["delayed"] is True
    assert "not a live feed" in quote["disclaimer"]
