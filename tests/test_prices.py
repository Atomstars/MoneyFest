"""Gate-input assembly tests -- specifically stock/index return alignment.

These cover the bug described in STATUS_REPORT.md section 2.9: when the index series was
missing even one of the stock's trading dates, ``build_gate_inputs`` fell back to the
index's *own* unaligned return series. ``classify`` then regressed stock returns against
index returns for different days, producing a meaningless beta (near zero, wildly
unstable). Nothing raised -- idio silently collapsed to ret and the MARKET branch
effectively stopped firing.

Pure: synthetic series, no network.
"""

from __future__ import annotations

import math

from app.tools.prices import PriceSeries, build_gate_inputs
from app.tools.gate import classify


def _dates(n: int, skip: set[int] | None = None) -> list[str]:
    """n consecutive business-ish ISO dates, optionally skipping some ordinals."""
    skip = skip or set()
    return [f"2026-01-{d:02d}" for d in range(1, n + 1) if d not in skip]


def _prices_from_returns(returns: list[float], start: float = 100.0) -> list[float]:
    prices = [start]
    for r in returns:
        prices.append(prices[-1] * math.exp(r))
    return prices


def _series(ticker: str, dates: list[str], prices: list[float]) -> PriceSeries:
    return PriceSeries(ticker=ticker, dates=dates, adj_close=prices,
                       volume=[1_000_000.0] * len(dates))


def _beta_case(index_skips: set[int]):
    """Build a stock that is exactly 1.5x the index, with the index missing some dates.

    Returns the GateResult. True beta is 1.5 by construction, so any large deviation
    means the two return windows were not paired day-for-day.
    """
    n = 70
    idx_returns = [0.01 * ((-1) ** i) * (1 + (i % 7) * 0.15) for i in range(n)]
    stock_returns = [1.5 * r for r in idx_returns]

    stock_dates = _dates(n + 1)
    stock_prices = _prices_from_returns(stock_returns)

    # The index is missing some of the stock's trading dates.
    keep = [i for i, d in enumerate(stock_dates) if (i + 1) not in index_skips]
    idx_prices_full = _prices_from_returns(idx_returns)
    index_dates = [stock_dates[i] for i in keep]
    index_prices = [idx_prices_full[i] for i in keep]

    target = stock_dates[-1]
    gi = build_gate_inputs(_series("STK", stock_dates, stock_prices),
                           _series("^NSEI", index_dates, index_prices),
                           target)
    return classify(
        r_today=gi.r_today, stock_returns=gi.stock_returns,
        index_returns=gi.index_returns, r_index_today=gi.r_index_today,
        vol_zscore=gi.vol_zscore, data_issue=gi.data_issue,
    )


def test_windows_are_equal_length_when_index_has_gaps():
    """The gate contract requires aligned windows; unequal lengths mean unpaired days."""
    stock_dates = _dates(41)
    stock_prices = _prices_from_returns([0.01 * ((-1) ** i) for i in range(40)])
    keep = [i for i in range(len(stock_dates)) if i not in (5, 17, 29)]
    idx_prices_full = _prices_from_returns([0.005 * ((-1) ** i) for i in range(40)])

    gi = build_gate_inputs(
        _series("STK", stock_dates, stock_prices),
        _series("^NSEI", [stock_dates[i] for i in keep], [idx_prices_full[i] for i in keep]),
        stock_dates[-1],
    )
    assert len(gi.stock_returns) == len(gi.index_returns)


def test_beta_recovered_when_index_calendar_is_complete():
    """Baseline: with identical calendars the known beta of 1.5 comes back."""
    assert abs(_beta_case(set()).beta60 - 1.5) < 0.05


def test_beta_survives_missing_index_dates():
    """The real-world case: ^NSEI is missing a few of the stock's trading dates.

    Before the fix this returned a beta near zero because the fallback path paired
    day i of the stock with day i of a shorter index series.
    """
    result = _beta_case({8, 22, 41, 55})
    assert abs(result.beta60 - 1.5) < 0.15, (
        f"beta {result.beta60:.3f} is far from the true 1.5 -- return windows "
        "are misaligned"
    )


def test_nan_close_does_not_produce_a_bogus_classification():
    """A NaN close must be dropped, not classified.

    yfinance returns a bar with close=NaN for a session that has opened but not
    settled. NaN passes every `price <= 0` guard (all NaN comparisons are False), so
    it used to flow straight through: log(nan/prev) is nan, the gate classified the
    day off all-NaN statistics, and the row landed in the DB as a real-looking
    outcome with NULL stats.
    """
    dates = _dates(41)
    prices = _prices_from_returns([0.01 * ((-1) ** i) for i in range(40)])
    prices[-1] = float("nan")  # today's bar hasn't settled

    idx_prices = _prices_from_returns([0.005 * ((-1) ** i) for i in range(40)])
    gi = build_gate_inputs(_series("STK", dates, prices),
                           _series("^NSEI", dates, idx_prices), dates[-1])

    # r_today must be None (no priced observation), never NaN dressed up as a return.
    assert gi.r_today is None or math.isfinite(gi.r_today), \
        f"NaN return leaked into the gate inputs: {gi.r_today}"
    assert all(math.isfinite(r) for r in gi.stock_returns), "NaN in estimation window"
    assert all(math.isfinite(r) for r in gi.index_returns), "NaN in index window"


def test_idio_does_not_collapse_to_raw_return():
    """With a real market relationship, idio must be materially smaller than ret.

    The misalignment bug's visible symptom was idio == ret, which stops MARKET
    ever firing.
    """
    result = _beta_case({8, 22, 41, 55})
    assert result.sigma_idio < result.sigma60 * 0.5, (
        f"sigma_idio {result.sigma_idio:.5f} vs sigma60 {result.sigma60:.5f} -- "
        "the market component is not being removed"
    )
