"""End-of-day job (APScheduler entrypoint, weekdays ~18:30 IST).

Pipeline per run:
  1. Refresh prices for all watchlist stocks (+ the index).
  2. Run the Tier-1/2/3 ingestors.
  3. For each watchlist stock, on its latest trading date:
       - assemble gate inputs (Gate-0 sanity in prices.py),
       - run the pure gate,
       - write the daily_metric row (with frozen gate_inputs_json),
       - NOISE / MARKET / EVENT_NO_MOVE / DATA_ISSUE -> attribution row with
         deterministic rendered text,
       - INVESTIGATE / MIXED -> build + persist the frozen bundle as
         outcome=PENDING_ATTRIBUTION (Phase 2 consumes it).

Everything here is deterministic; no LLM calls.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from app.config import GATE_CONFIG, INDEX_TICKER
from app.tools import gate as gate_mod
from app.tools.prices import PriceSeries, build_gate_inputs
from app.bundle import build_bundle
from app.render import render
from app.watchlist import watchlist_stocks, all_watchlisted_stocks

try:
    from app.tools.prices import download_prices, default_window
except Exception:  # pragma: no cover
    download_prices = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _latest_trading_date(series: PriceSeries) -> str | None:
    return series.dates[-1] if series.dates else None


def _prev_trading_date(series: PriceSeries, day: str) -> str | None:
    if day in series.dates:
        i = series.dates.index(day)
        if i > 0:
            return series.dates[i - 1]
    return None


def write_daily_metric(conn: sqlite3.Connection, stock_id: int, day: str,
                       result: gate_mod.GateResult,
                       close: float | None = None,
                       volume: float | None = None) -> None:
    gate_inputs = {
        "config": GATE_CONFIG.to_json_dict(),
        "result": result.to_json_dict(),
    }
    conn.execute(
        """INSERT INTO daily_metric
             (stock_id, date, ret, index_ret, sigma60, beta60, sigma_idio,
              idio_ret, vol_zscore, close, volume, gate_result, gate_inputs_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(stock_id, date) DO UPDATE SET
             ret=excluded.ret, index_ret=excluded.index_ret, sigma60=excluded.sigma60,
             beta60=excluded.beta60, sigma_idio=excluded.sigma_idio,
             idio_ret=excluded.idio_ret, vol_zscore=excluded.vol_zscore,
             close=COALESCE(excluded.close, daily_metric.close),
             volume=COALESCE(excluded.volume, daily_metric.volume),
             gate_result=excluded.gate_result, gate_inputs_json=excluded.gate_inputs_json""",
        (stock_id, day, result.ret, result.index_ret, result.sigma60, result.beta60,
         result.sigma_idio, result.idio_ret, result.vol_zscore, close, volume,
         result.outcome, json.dumps(gate_inputs, sort_keys=True)),
    )
    conn.commit()


def write_attribution(conn: sqlite3.Connection, stock_id: int, day: str,
                      result: gate_mod.GateResult, stock_name: str,
                      tier1_event: bool, bundle_json: str | None = None,
                      outcome: str | None = None) -> None:
    trigger = "event" if tier1_event else "move"
    outcome = outcome or result.outcome
    rendered = None if bundle_json else render(stock_name, result)
    conn.execute(
        """INSERT INTO attribution
             (stock_id, date, trigger, gate_snapshot_json, outcome, rendered_text,
              bundle_json, created_at, model_version)
           VALUES (?,?,?,?,?,?,?,?,?)
           ON CONFLICT(stock_id, date, trigger) DO UPDATE SET
             gate_snapshot_json=excluded.gate_snapshot_json, outcome=excluded.outcome,
             rendered_text=excluded.rendered_text, bundle_json=excluded.bundle_json,
             created_at=excluded.created_at""",
        (stock_id, day, trigger, json.dumps(result.to_json_dict(), sort_keys=True),
         outcome, rendered, bundle_json, _now(), None),
    )
    conn.commit()


def process_stock(conn: sqlite3.Connection, stock_row: sqlite3.Row,
                  index_series: PriceSeries) -> dict:
    """Run the full deterministic pipeline for one stock. Returns a small summary."""
    from app.ingest.nse_bse import has_tier1_today

    ticker = stock_row["ticker_nse"]
    yf_symbol = f"{ticker}.NS"
    start, end = default_window(200)
    series = download_prices(yf_symbol, start, end)
    day = _latest_trading_date(series)
    if day is None:
        return {"stock": ticker, "status": "no_price_data"}

    prev_day = _prev_trading_date(series, day)
    tier1 = has_tier1_today(conn, stock_row["id"], day)

    # Optional second source (.BO) for INVESTIGATE-scale cross-check.
    second = None
    if stock_row["ticker_bse"]:
        try:
            second = download_prices(f"{stock_row['ticker_bse']}.BO", start, end)
        except Exception:  # pragma: no cover
            second = None

    inputs = build_gate_inputs(series, index_series, day, second_source_series=second)
    result = gate_mod.classify(
        r_today=inputs.r_today,
        stock_returns=inputs.stock_returns,
        index_returns=inputs.index_returns,
        r_index_today=inputs.r_index_today,
        tier1_event_today=tier1,
        vol_zscore=inputs.vol_zscore,
        data_issue=inputs.data_issue,
    )

    write_daily_metric(conn, stock_row["id"], day, result,
                       close=_price_on(series, day), volume=_volume_on(series, day))

    if result.outcome == "WARMING_UP":
        # No explanation and not alert-worthy; the daily_metric row is enough. (The
        # attribution CHECK constraint doesn't include WARMING_UP by design.)
        return {"stock": ticker, "date": day, "gate": result.outcome}
    if result.outcome in ("INVESTIGATE", "MIXED"):
        bundle = build_bundle(conn, stock_row["id"], day, gate=result,
                              prev_trading_day=prev_day)
        write_attribution(conn, stock_row["id"], day, result, stock_row["name"],
                          tier1, bundle_json=bundle.to_json(),
                          outcome="PENDING_ATTRIBUTION")
    else:
        write_attribution(conn, stock_row["id"], day, result, stock_row["name"], tier1)

    return {"stock": ticker, "date": day, "gate": result.outcome}


def _price_on(series: PriceSeries, day: str) -> float | None:
    """Adjusted close for ``day``, or None if the instrument didn't trade."""
    try:
        return series.adj_close[series.dates.index(day)]
    except (ValueError, IndexError):
        return None


def _volume_on(series: PriceSeries, day: str) -> float | None:
    try:
        return series.volume[series.dates.index(day)]
    except (ValueError, IndexError):
        return None


def _today_ist() -> str:
    from datetime import datetime as _dt
    from zoneinfo import ZoneInfo
    from app.config import MARKET_TZ
    return _dt.now(ZoneInfo(MARKET_TZ)).date().isoformat()


def _fetch_index_with_retry(start: str, end: str):
    """Fetch the index series with bounded retries; None if it never succeeds."""
    import time
    from app.config import INDEX_FETCH_RETRIES, INDEX_FETCH_BACKOFF_SEC
    last_exc = None
    for attempt in range(INDEX_FETCH_RETRIES + 1):
        try:
            s = download_prices(INDEX_TICKER, start, end)
            if s.adj_close:
                return s
            last_exc = "empty index series"
        except Exception as exc:  # pragma: no cover - network variance
            last_exc = str(exc)
        if attempt < INDEX_FETCH_RETRIES:
            time.sleep(INDEX_FETCH_BACKOFF_SEC * (attempt + 1))
    print(f"[eod] index fetch failed after retries: {last_exc}")
    return None


def run_eod(conn: sqlite3.Connection | None = None, *, run_date: str | None = None,
            force: bool = False, sender=None) -> dict:
    """Hardened EOD run. Idempotent per date; one run_log row per attempt.

    Skips weekends/NSE holidays (unless ``force``). Aborts cleanly if the index can't be
    fetched. ``sender`` is injectable for alert delivery in tests.
    """
    from app.db import fresh_db
    from app.jobs.calendar import is_trading_day, skip_reason, start_run, finish_run
    conn = conn or fresh_db()
    run_date = run_date or _today_ist()

    # Calendar skip -- decided BEFORE any network work.
    if not force and not is_trading_day(run_date):
        reason = skip_reason(run_date)
        rid = start_run(conn, run_date)
        finish_run(conn, rid, {"skipped": reason})
        print(f"[eod] {run_date} skipped: {reason}")
        return {"date": run_date, "skipped": reason}

    if download_prices is None:  # pragma: no cover
        raise RuntimeError("yfinance not installed; cannot run EOD")

    run_id = start_run(conn, run_date)

    # 1. Ingestors (best-effort; network failures are logged, not fatal).
    _run_ingestors(conn)

    # 2. Index series once (retry; abort if unavailable -- nothing computable without it).
    start, end = default_window(200)
    index_series = _fetch_index_with_retry(start, end)
    if index_series is None:
        summary = {"date": run_date, "aborted": "index fetch failed"}
        finish_run(conn, run_id, summary)
        return summary

    effective_date = index_series.dates[-1]  # the market date being explained

    # 3. Per-stock deterministic pipeline (one stock's failure never aborts the run).
    stock_summaries = []
    for s in all_watchlisted_stocks(conn):
        try:
            stock_summaries.append(process_stock(conn, s, index_series))
        except Exception as exc:  # pragma: no cover
            stock_summaries.append({"stock": s["ticker_nse"], "error": str(exc)})

    # 4. Reasoning layer (Phase 2), only when enabled. Local import keeps the daily loop
    # LLM-free unless attribution is turned on.
    attribution = None
    from app.config import ATTRIBUTION_ENABLED
    if ATTRIBUTION_ENABLED:
        from app.attrib.pipeline import run_pending
        attribution = run_pending(conn)

    # 5. Alert selection + delivery (deterministic selection; at-most-once delivery).
    from app.alerts.selector import select_alerts
    from app.alerts.telegram import deliver_alerts, retry_failed, send_message
    alerts = select_alerts(conn, effective_date)
    delivery = deliver_alerts(conn, alerts, sender=sender or send_message)
    if delivery["failed"]:
        delivery["retry"] = retry_failed(conn, sender=sender or send_message)

    summary = {
        "date": run_date, "effective_date": effective_date,
        "stocks": stock_summaries, "attribution": attribution, "delivery": delivery,
    }
    finish_run(conn, run_id, summary)
    return summary


def _run_ingestors(conn: sqlite3.Connection) -> None:  # pragma: no cover - network
    from app.ingest import nse_bse, macro, news
    for name, fn in (("nse_bse", nse_bse.ingest_all),
                     ("macro", macro.ingest_all),
                     ("news", news.ingest_all)):
        try:
            n = fn(conn)
            print(f"[eod] {name}: {n} evidence rows")
        except Exception as exc:
            print(f"[eod] {name} failed: {exc}")


def build_scheduler():  # pragma: no cover - runtime only
    """Return an APScheduler BlockingScheduler wired to the weekday EOD job."""
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger
    from app.config import EOD_HOUR, EOD_MINUTE, MARKET_TZ

    sched = BlockingScheduler(timezone=MARKET_TZ)
    sched.add_job(
        lambda: run_eod(),
        CronTrigger(day_of_week="mon-fri", hour=EOD_HOUR, minute=EOD_MINUTE),
        id="eod",
    )
    return sched


if __name__ == "__main__":  # pragma: no cover
    for row in run_eod():
        print(row)
