"""The quantitative gate -- pure functions, no I/O.

Given precomputed return series and a couple of flags, classify a (stock, date)
as one of:

    NOISE | MARKET | MIXED | INVESTIGATE | EVENT_NO_MOVE | WARMING_UP | DATA_ISSUE

Everything here is a pure function (inputs -> result). All corporate-action lookups,
staleness checks and second-source cross-checks happen in the caller (tools/prices.py
+ jobs/eod.py), which passes their *conclusions* in as ``data_issue`` / ``tier1_event``.
This keeps the gate deterministic and trivially unit-testable with synthetic series.

Math is done in the standard library only (statistics + a hand-rolled OLS) so the
core has zero third-party dependencies.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from statistics import fmean, pstdev
from typing import Sequence

from app.config import GateConfig, GATE_CONFIG


# --- Result type -----------------------------------------------------------

@dataclass(frozen=True)
class GateResult:
    """The full, reproducible output of one gate evaluation."""

    outcome: str                    # NOISE | MARKET | MIXED | INVESTIGATE | EVENT_NO_MOVE | WARMING_UP | DATA_ISSUE
    ret: float | None               # r_today (raw, never winsorized)
    index_ret: float | None         # r_index_today
    sigma60: float | None           # stdev of stock returns (winsorized window)
    beta60: float | None            # clamped OLS slope vs index
    sigma_idio: float | None        # stdev of residuals
    idio_ret: float | None          # r_today - beta * r_index_today
    vol_zscore: float | None
    config_version: str
    reason: str                     # human-readable why-this-outcome
    n_obs: int                      # number of historical return observations used

    def to_json_dict(self) -> dict:
        return asdict(self)


# --- Pure math helpers -----------------------------------------------------

def log_returns(prices: Sequence[float]) -> list[float]:
    """Daily log returns from a price series (len N -> N-1 returns)."""
    out: list[float] = []
    for prev, cur in zip(prices, prices[1:]):
        if prev is None or cur is None or prev <= 0 or cur <= 0:
            raise ValueError("non-positive or missing price in series")
        out.append(math.log(cur / prev))
    return out


def winsorize(returns: Sequence[float], sigma_mult: float) -> list[float]:
    """Clip returns to +/- sigma_mult * stdev. Used for ESTIMATION windows only.

    The day being explained is never passed through here.
    """
    xs = list(returns)
    if len(xs) < 2:
        return xs
    mu = fmean(xs)
    sd = pstdev(xs)
    if sd == 0:
        return xs
    lo, hi = mu - sigma_mult * sd, mu + sigma_mult * sd
    return [min(max(x, lo), hi) for x in xs]


def stdev(xs: Sequence[float]) -> float:
    """Population stdev; 0.0 for degenerate input."""
    xs = list(xs)
    if len(xs) < 2:
        return 0.0
    return pstdev(xs)


def ols_beta(y: Sequence[float], x: Sequence[float]) -> tuple[float, float, list[float]]:
    """OLS of y on x with intercept.

    Returns (slope, intercept, residuals). residuals = y - intercept - slope*x,
    used for sigma_idio. Falls back to slope=0 when x has no variance.
    """
    ys, xs = list(y), list(x)
    n = len(xs)
    if n == 0 or n != len(ys):
        return 0.0, 0.0, []
    mx, my = fmean(xs), fmean(ys)
    var_x = sum((xi - mx) ** 2 for xi in xs)
    if var_x == 0:
        # No index variation to regress on; treat beta as 0, residuals = y - mean.
        resid = [yi - my for yi in ys]
        return 0.0, my, resid
    cov = sum((xi - mx) * (yi - my) for xi, yi in zip(xs, ys))
    slope = cov / var_x
    intercept = my - slope * mx
    resid = [yi - intercept - slope * xi for xi, yi in zip(xs, ys)]
    return slope, intercept, resid


def clamp(v: float, lo: float, hi: float) -> float:
    return min(max(v, lo), hi)


# --- The gate --------------------------------------------------------------

def classify(
    *,
    r_today: float | None,
    stock_returns: Sequence[float],
    index_returns: Sequence[float],
    r_index_today: float | None,
    tier1_event_today: bool = False,
    vol_zscore: float | None = None,
    data_issue: bool = False,
    config: GateConfig = GATE_CONFIG,
) -> GateResult:
    """Classify one (stock, date). Pure: identical inputs => identical result.

    ``stock_returns`` / ``index_returns`` are the aligned *historical* estimation
    windows (up to and excluding today). ``r_today`` / ``r_index_today`` are the
    day being explained -- they are never winsorized.

    ``data_issue`` is decided upstream (stale price, corp-action ambiguity, or a
    second-source disagreement > config.second_source_max_disagreement).
    """
    n = len(stock_returns)

    # Gate 0 -- upstream sanity already failed.
    if data_issue:
        return GateResult(
            outcome="DATA_ISSUE", ret=r_today, index_ret=r_index_today,
            sigma60=None, beta60=None, sigma_idio=None, idio_ret=None,
            vol_zscore=vol_zscore, config_version=config.version,
            reason="upstream data-sanity failure (stale/corp-action/second-source)",
            n_obs=n,
        )

    # Warming up -- can't compute stats. Only the event trigger is active.
    if n < config.min_lookback:
        if tier1_event_today:
            return GateResult(
                outcome="INVESTIGATE", ret=r_today, index_ret=r_index_today,
                sigma60=None, beta60=None, sigma_idio=None, idio_ret=None,
                vol_zscore=vol_zscore, config_version=config.version,
                reason=f"warming up ({n}<{config.min_lookback} obs) but Tier-1 event fired",
                n_obs=n,
            )
        return GateResult(
            outcome="WARMING_UP", ret=r_today, index_ret=r_index_today,
            sigma60=None, beta60=None, sigma_idio=None, idio_ret=None,
            vol_zscore=vol_zscore, config_version=config.version,
            reason=f"only {n} obs (<{config.min_lookback}); move trigger disabled",
            n_obs=n,
        )

    # Trim to the configured lookback (most recent `lookback` observations).
    sr = list(stock_returns)[-config.lookback:]
    ir = list(index_returns)[-config.lookback:]
    # Align lengths defensively.
    m = min(len(sr), len(ir))
    sr, ir = sr[-m:], ir[-m:]

    # Winsorize the ESTIMATION windows only.
    sr_w = winsorize(sr, config.winsor_sigma)
    ir_w = winsorize(ir, config.winsor_sigma)

    sigma60 = stdev(sr_w)
    beta_raw, _intercept, resid = ols_beta(sr_w, ir_w)
    beta60 = clamp(beta_raw, config.beta_clamp_low, config.beta_clamp_high)
    sigma_idio = stdev(resid)

    r = float(r_today) if r_today is not None else 0.0
    r_idx = float(r_index_today) if r_index_today is not None else 0.0
    idio = r - beta60 * r_idx

    base = dict(
        ret=r, index_ret=r_idx, sigma60=sigma60, beta60=beta60,
        sigma_idio=sigma_idio, idio_ret=idio, vol_zscore=vol_zscore,
        config_version=config.version, n_obs=m,
    )

    # Gate 1 -- noise.
    if sigma60 > 0 and abs(r) < config.noise_sigma_mult * sigma60:
        if tier1_event_today:
            return GateResult(outcome="EVENT_NO_MOVE",
                              reason="Tier-1 event but move within normal daily range",
                              **base)
        return GateResult(outcome="NOISE",
                          reason=f"|r|={abs(r):.4f} < {config.noise_sigma_mult}*sigma "
                                 f"({config.noise_sigma_mult * sigma60:.4f}); no Tier-1 event",
                          **base)

    # Gate 2 -- market.
    market_explained = (
        sigma_idio > 0
        and abs(idio) < config.market_idio_sigma_mult * sigma_idio
        and abs(r_idx) >= config.market_index_min_move
    )
    if market_explained:
        return GateResult(outcome="MARKET",
                          reason=f"|idio|={abs(idio):.4f} < {config.market_idio_sigma_mult}"
                                 f"*sigma_idio and |index|={abs(r_idx):.4f} >= "
                                 f"{config.market_index_min_move}",
                          **base)

    # Gate 3 -- dispatch.
    if sigma_idio > 0 and abs(idio) >= config.investigate_idio_sigma_mult * sigma_idio:
        return GateResult(outcome="INVESTIGATE",
                          reason=f"|idio|={abs(idio):.4f} >= "
                                 f"{config.investigate_idio_sigma_mult}*sigma_idio",
                          **base)

    # Anything left that wasn't NOISE and wasn't cleanly MARKET is at least MIXED:
    # there is unexplained movement (>=1 sigma total) with a non-trivial residual.
    return GateResult(outcome="MIXED",
                      reason=f"|idio|={abs(idio):.4f} in "
                             f"[{config.mixed_idio_sigma_mult}, "
                             f"{config.investigate_idio_sigma_mult})*sigma_idio "
                             f"(or index too quiet to call MARKET)",
                      **base)
