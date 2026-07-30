"""Price / volume tool.

Fetches adjusted prices via yfinance, computes the return series the gate needs,
and performs the Gate-0 data-sanity work that must NOT live inside the pure gate:
corporate-action detection, staleness checks and a second-source cross-check.

Known yfinance NSE limitations (documented in README section "Data-quality caveats"):
missed corporate actions, stale quotes on illiquid names, occasional bad prints.
Gate 0 exists precisely because of these.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Sequence

from app.config import GATE_CONFIG, INDEX_TICKER

try:  # yfinance is only needed for live fetches, not for gate unit tests.
    import yfinance as yf
except Exception:  # pragma: no cover - import guarded so tests never require it
    yf = None


# --- Data types ------------------------------------------------------------

@dataclass
class PriceSeries:
    """Aligned dates + adjusted close + volume for one instrument."""

    ticker: str
    dates: list[str]           # ISO dates, ascending
    adj_close: list[float]
    volume: list[float] = field(default_factory=list)

    def returns(self) -> list[float]:
        from app.tools.gate import log_returns
        return log_returns(self.adj_close)


@dataclass
class GateInputs:
    """Everything the pure gate needs for one (stock, date), plus sanity flags."""

    stock_returns: list[float]
    index_returns: list[float]
    r_today: float | None
    r_index_today: float | None
    vol_zscore: float | None
    data_issue: bool
    data_issue_reason: str | None
    corp_action_on_day: bool


# --- yfinance fetch --------------------------------------------------------

def _require_yf():
    if yf is None:  # pragma: no cover
        raise RuntimeError(
            "yfinance is not installed. Install requirements.txt to fetch live prices."
        )


def download_prices(ticker: str, start: str, end: str) -> PriceSeries:
    """Download adjusted daily prices in [start, end). Uses auto-adjusted close."""
    _require_yf()
    df = yf.download(
        ticker, start=start, end=end, auto_adjust=True,
        progress=False, threads=False,
    )
    if df is None or df.empty:
        return PriceSeries(ticker=ticker, dates=[], adj_close=[], volume=[])
    # yfinance may return a MultiIndex when given a single ticker in newer versions.
    close_col = df["Close"]
    vol_col = df["Volume"] if "Volume" in df else None
    if hasattr(close_col, "columns"):  # DataFrame -> squeeze to Series
        close_col = close_col.iloc[:, 0]
        if vol_col is not None:
            vol_col = vol_col.iloc[:, 0]
    raw_dates = [d.date().isoformat() for d in df.index]
    raw_adj = [float(v) for v in close_col.tolist()]
    raw_vol = [float(v) for v in vol_col.tolist()] if vol_col is not None else []

    # Drop bars with a non-finite close. yfinance emits these for a session that has
    # opened but not yet settled (and occasionally for bad prints), and NaN does NOT
    # trip the usual `price <= 0` guards -- every NaN comparison is False. Left in, it
    # propagates: log(nan/prev) is nan, the gate happily classifies the day off all-NaN
    # statistics, and SQLite stores the result as NULL. A day we have no price for must
    # be absent, not present-and-meaningless.
    dates: list[str] = []
    adj: list[float] = []
    vol: list[float] = []
    for i, price in enumerate(raw_adj):
        if not math.isfinite(price) or price <= 0:
            continue
        dates.append(raw_dates[i])
        adj.append(price)
        if i < len(raw_vol):
            v = raw_vol[i]
            vol.append(v if math.isfinite(v) else 0.0)
    return PriceSeries(ticker=ticker, dates=dates, adj_close=adj, volume=vol)


def corporate_actions(ticker: str) -> list[dict]:
    """Recent splits/dividends from yfinance, as [{date, type, value}]."""
    _require_yf()
    t = yf.Ticker(ticker)
    out: list[dict] = []
    try:
        actions = t.actions
    except Exception:  # pragma: no cover
        return out
    if actions is None or actions.empty:
        return out
    for idx, row in actions.iterrows():
        d = idx.date().isoformat()
        if row.get("Dividends", 0):
            out.append({"date": d, "type": "dividend", "value": float(row["Dividends"])})
        if row.get("Stock Splits", 0):
            out.append({"date": d, "type": "split", "value": float(row["Stock Splits"])})
    return out


# --- Gate-input assembly ---------------------------------------------------

def volume_zscore(volumes: Sequence[float], today_volume: float | None) -> float | None:
    if today_volume is None or len(volumes) < 2:
        return None
    from statistics import fmean, pstdev
    mu, sd = fmean(volumes), pstdev(volumes)
    if sd == 0:
        return 0.0
    return (today_volume - mu) / sd


def _return_on_date(series: PriceSeries, target: str) -> tuple[float | None, int | None]:
    """Return (r_today, index_of_today) where r_today is the log return into `target`."""
    if target not in series.dates:
        return None, None
    i = series.dates.index(target)
    if i == 0:
        return None, i
    from math import log
    prev, cur = series.adj_close[i - 1], series.adj_close[i]
    # isfinite first: NaN fails every `<= 0` comparison, so without this a NaN close
    # yields log(nan/prev) == nan and poisons everything downstream.
    if not math.isfinite(prev) or not math.isfinite(cur) or prev <= 0 or cur <= 0:
        return None, i
    return log(cur / prev), i


def build_gate_inputs(
    stock_series: PriceSeries,
    index_series: PriceSeries,
    target_date: str,
    *,
    second_source_series: PriceSeries | None = None,
    config=GATE_CONFIG,
) -> GateInputs:
    """Assemble aligned windows and run the Gate-0 sanity checks.

    ``second_source_series`` (e.g. the .BO listing when the primary is .NS) is used
    only to cross-check the target day's price for INVESTIGATE-level moves.
    """
    reason = None
    data_issue = False

    r_today, i_today = _return_on_date(stock_series, target_date)

    # Staleness: the stock did not trade on the target date at all.
    if i_today is None:
        return GateInputs(
            stock_returns=[], index_returns=[], r_today=None, r_index_today=None,
            vol_zscore=None, data_issue=True,
            data_issue_reason="no trade on target date (stale price)",
            corp_action_on_day=False,
        )

    from app.tools.gate import log_returns

    # Historical estimation windows: paired stock/index returns strictly before today.
    #
    # Align the index window to the stock's trading dates.
    #
    # These must be paired day-for-day: ``classify`` regresses stock returns on index
    # returns, so a positional mismatch silently produces a meaningless beta (near
    # zero, wildly unstable) rather than an error -- which then makes idio == ret and
    # stops the MARKET branch ever firing.
    #
    # yfinance does NOT return identical calendars for a stock and ^NSEI (a handful of
    # dates are typically present for one and not the other), so an all-or-nothing
    # check fails routinely. Pair on the *intersection* instead: keep only dates where
    # both have a valid price, and take returns across consecutive kept days. A few
    # merged intervals are a far smaller distortion than misaligned pairs.
    idx_by_date = dict(zip(index_series.dates, index_series.adj_close))
    stock_dates_in_window = stock_series.dates[: i_today + 1]
    stock_prices_in_window = stock_series.adj_close[: i_today + 1]

    paired_stock: list[float] = []
    paired_index: list[float] = []
    for d, p in zip(stock_dates_in_window, stock_prices_in_window):
        q = idx_by_date.get(d)
        if p is not None and p > 0 and q is not None and q > 0:
            paired_stock.append(p)
            paired_index.append(q)

    index_hist: list[float] = []
    if len(paired_stock) >= 3:
        paired_stock_returns = log_returns(paired_stock)
        paired_index_returns = log_returns(paired_index)
        if target_date in idx_by_date:
            # Today is paired, so its return is the last element of each -- drop it
            # from the estimation windows (the day being explained is never estimated on).
            stock_hist = paired_stock_returns[:-1]
            index_hist = paired_index_returns[:-1]
            r_index_today = paired_index_returns[-1]
        else:
            stock_hist = paired_stock_returns
            index_hist = paired_index_returns
            r_index_today, _ = _return_on_date(index_series, target_date)
    else:
        # Not enough overlap to estimate anything; the gate will report WARMING_UP.
        r_index_today, _ = _return_on_date(index_series, target_date)
        stock_hist = []

    # Volume z-score over the historical window.
    vol_hist = stock_series.volume[max(0, i_today - config.lookback): i_today]
    today_vol = stock_series.volume[i_today] if i_today < len(stock_series.volume) else None
    vol_z = volume_zscore(vol_hist, today_vol)

    # Gate 0 -- large move triggers a corporate-action check.
    corp_action_on_day = False
    if r_today is not None and abs(r_today) > config.sanity_move_threshold:
        try:
            actions = corporate_actions(stock_series.ticker)
        except Exception:
            actions = []
        corp_action_on_day = any(a["date"] == target_date for a in actions)
        if corp_action_on_day:
            data_issue = True
            reason = "large move coincides with a corporate action record date"

    # Gate 0 -- second-source cross-check for INVESTIGATE-scale moves.
    if (not data_issue and second_source_series is not None
            and r_today is not None):
        p1 = stock_series.adj_close[i_today]
        p2_by_date = dict(zip(second_source_series.dates, second_source_series.adj_close))
        p2 = p2_by_date.get(target_date)
        if p2 and p1 and abs(p1 - p2) / p1 > config.second_source_max_disagreement:
            data_issue = True
            reason = (f"price disagreement between sources "
                      f"{abs(p1 - p2) / p1:.3%} > {config.second_source_max_disagreement:.1%}")

    return GateInputs(
        stock_returns=stock_hist,
        index_returns=index_hist,
        r_today=r_today,
        r_index_today=r_index_today,
        vol_zscore=vol_z,
        data_issue=data_issue,
        data_issue_reason=reason,
        corp_action_on_day=corp_action_on_day,
    )


def default_window(days_back: int = 200) -> tuple[str, str]:
    """A generous calendar window that yields ~60+ trading days."""
    end = date.today() + timedelta(days=1)
    start = date.today() - timedelta(days=days_back)
    return start.isoformat(), end.isoformat()
