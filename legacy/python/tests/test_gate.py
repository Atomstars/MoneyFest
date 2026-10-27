"""Gate unit tests -- the six synthetic scenarios from the Phase-1 spec, plus the
event trigger. Pure functions, no DB, no network."""

from __future__ import annotations

from app.tools.gate import classify, GateConfig, log_returns, ols_beta, winsorize

CFG = GateConfig()


def _market_series(n: int = 60, beta: float = 1.2):
    """Aligned (stock, index) return windows where stock ~= beta*index + tiny idio."""
    idx, stk = [], []
    for i in range(n):
        r_idx = 0.01 * ((-1) ** i) * (1 + (i % 5) * 0.1)
        idio = 0.001 * ((-1) ** (i // 2))
        idx.append(r_idx)
        stk.append(beta * r_idx + idio)
    return stk, idx


# --- Scenario 1: quiet stock / quiet index -> NOISE ------------------------

def test_quiet_stock_quiet_index_is_noise():
    stock = [0.01, -0.01] * 30          # sigma == 0.01
    index = [0.004, -0.004] * 30
    r = classify(
        r_today=0.005, stock_returns=stock, index_returns=index,
        r_index_today=0.001, tier1_event_today=False, config=CFG,
    )
    assert r.outcome == "NOISE"


# --- Scenario 2: market-wide crash day, high-beta name -> MARKET -----------

def test_market_wide_crash_is_market_for_high_beta():
    stock, index = _market_series(beta=1.2)
    # A crash: index down 2%, stock down ~beta*2% with ~zero idio.
    r = classify(
        r_today=1.2 * -0.02, stock_returns=stock, index_returns=index,
        r_index_today=-0.02, tier1_event_today=False, config=CFG,
    )
    assert r.outcome == "MARKET"
    assert r.beta60 > 1.0  # recovered the high beta


# --- Scenario 3: large idiosyncratic move -> INVESTIGATE -------------------

def test_large_idio_move_is_investigate():
    stock, index = _market_series(beta=1.2)
    r = classify(
        r_today=-0.05, stock_returns=stock, index_returns=index,
        r_index_today=-0.005, tier1_event_today=False, config=CFG,
    )
    assert r.outcome == "INVESTIGATE"
    assert abs(r.idio_ret) >= CFG.investigate_idio_sigma_mult * r.sigma_idio


# --- Scenario 4: split day -> DATA_ISSUE (sanity failure upstream) ---------

def test_split_day_is_data_issue():
    stock, index = _market_series()
    r = classify(
        r_today=-0.50, stock_returns=stock, index_returns=index,
        r_index_today=-0.005, tier1_event_today=False, data_issue=True, config=CFG,
    )
    assert r.outcome == "DATA_ISSUE"


# --- Scenario 5: warming-up stock (<40 obs) -> WARMING_UP ------------------

def test_warming_up_stock():
    stock = [0.01, -0.01] * 15          # 30 obs < min_lookback (40)
    index = [0.004, -0.004] * 15
    r = classify(
        r_today=0.03, stock_returns=stock, index_returns=index,
        r_index_today=0.001, tier1_event_today=False, config=CFG,
    )
    assert r.outcome == "WARMING_UP"


def test_warming_up_stock_with_event_still_fires():
    stock = [0.01, -0.01] * 15
    index = [0.004, -0.004] * 15
    r = classify(
        r_today=0.03, stock_returns=stock, index_returns=index,
        r_index_today=0.001, tier1_event_today=True, config=CFG,
    )
    assert r.outcome == "INVESTIGATE"  # event trigger active while warming up


# --- Scenario 6: stale price -> DATA_ISSUE --------------------------------

def test_stale_price_is_data_issue():
    # Upstream (prices.py) sets data_issue=True when the stock didn't trade today.
    r = classify(
        r_today=None, stock_returns=[], index_returns=[],
        r_index_today=None, data_issue=True, config=CFG,
    )
    assert r.outcome == "DATA_ISSUE"


# --- Event trigger: material filing, muted move -> EVENT_NO_MOVE ----------

def test_event_no_move():
    stock = [0.01, -0.01] * 30
    index = [0.004, -0.004] * 30
    r = classify(
        r_today=0.003, stock_returns=stock, index_returns=index,
        r_index_today=0.001, tier1_event_today=True, config=CFG,
    )
    assert r.outcome == "EVENT_NO_MOVE"


# --- Determinism: same inputs + same config => identical result -----------

def test_determinism():
    stock, index = _market_series()
    kwargs = dict(r_today=-0.05, stock_returns=stock, index_returns=index,
                  r_index_today=-0.005, config=CFG)
    assert classify(**kwargs).to_json_dict() == classify(**kwargs).to_json_dict()


# --- Pure-math helpers -----------------------------------------------------

def test_log_returns_and_ols():
    prices = [100, 101, 102, 101]
    rets = log_returns(prices)
    assert len(rets) == 3
    slope, intercept, resid = ols_beta([2, 4, 6], [1, 2, 3])
    assert abs(slope - 2.0) < 1e-9
    assert all(abs(x) < 1e-9 for x in resid)


def test_winsorize_clips_outliers_only():
    xs = [0.0] * 10 + [1.0]        # one large outlier
    w = winsorize(xs, sigma_mult=1.0)
    assert max(w) < 1.0            # the outlier was clipped inward
