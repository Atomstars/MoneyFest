"""Thin internal FastAPI app (Phase 1, localhost, no auth).

Endpoints:
  GET  /health
  GET  /stocks/{id}/gate?date=            -- the daily_metric row for a date
  GET  /stocks/{id}/bundle?date=          -- the persisted frozen bundle for a date
  GET  /stocks/{id}/profile               -- effective profile, with per-edge provenance
  POST /watchlist                         -- add a stock to the watchlist
  DELETE /watchlist/{id}                  -- remove a watchlist item
"""

from __future__ import annotations

import json

from fastapi import FastAPI, HTTPException, Query, Depends, Request
from pydantic import BaseModel

from app.db import fresh_db
from app.exposure.profiles import effective_profile
from app.watchlist import upsert_stock, add_to_watchlist, remove_from_watchlist
from app.web.auth import require_token
from app.web import data as webdata

app = FastAPI(title="Stock Impact Explainer", version="4.0.0")


def _conn():
    # One connection per request keeps sqlite happy across threads.
    return fresh_db()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "phase": 1}


@app.get("/stocks/{stock_id}/gate")
def get_gate(stock_id: int, date: str = Query(..., description="ISO trading date")) -> dict:
    conn = _conn()
    row = conn.execute(
        "SELECT * FROM daily_metric WHERE stock_id=? AND date=?", (stock_id, date)
    ).fetchone()
    if row is None:
        raise HTTPException(404, f"no gate result for stock {stock_id} on {date}")
    out = dict(row)
    out["gate_inputs_json"] = json.loads(out["gate_inputs_json"])
    return out


@app.get("/stocks/{stock_id}/bundle")
def get_bundle(stock_id: int, date: str = Query(...)) -> dict:
    conn = _conn()
    row = conn.execute(
        """SELECT bundle_json, outcome FROM attribution
           WHERE stock_id=? AND date=? AND bundle_json IS NOT NULL
           ORDER BY id DESC LIMIT 1""",
        (stock_id, date),
    ).fetchone()
    if row is None:
        raise HTTPException(404, f"no bundle for stock {stock_id} on {date}")
    return {"outcome": row["outcome"], "bundle": json.loads(row["bundle_json"])}


@app.get("/metrics/strips")
def get_strip_metrics() -> dict:
    """Hallucination-rate metric: verifier strip counts by stage and reason."""
    conn = _conn()
    by_stage: dict[str, int] = {}
    by_reason: dict[str, int] = {}
    total = 0
    for (log_json,) in conn.execute(
        "SELECT verifier_log_json FROM attribution WHERE verifier_log_json IS NOT NULL"
    ).fetchall():
        for entry in json.loads(log_json):
            total += 1
            by_stage[entry.get("stage", "?")] = by_stage.get(entry.get("stage", "?"), 0) + 1
            r = (entry.get("reason") or "")[:60]
            by_reason[r] = by_reason.get(r, 0) + 1
    return {"total_strips": total, "by_stage": by_stage, "by_reason": by_reason}


@app.get("/stocks/{stock_id}/profile")
def get_profile(stock_id: int) -> dict:
    conn = _conn()
    edges = effective_profile(conn, stock_id)
    return {"stock_id": stock_id, "edges": [e.to_json_dict() for e in edges]}


class WatchlistAdd(BaseModel):
    name: str
    ticker_nse: str | None = None
    ticker_bse: str | None = None
    sector: str | None = None
    qty: float | None = None
    user_id: str = "default"


@app.post("/watchlist")
def post_watchlist(body: WatchlistAdd) -> dict:
    conn = _conn()
    stock_id = upsert_stock(
        conn, name=body.name, ticker_nse=body.ticker_nse,
        ticker_bse=body.ticker_bse, sector_name=body.sector,
    )
    wid = add_to_watchlist(conn, stock_id, user_id=body.user_id, qty=body.qty)
    return {"watchlist_id": wid, "stock_id": stock_id}


@app.delete("/watchlist/{watchlist_id}")
def delete_watchlist(watchlist_id: int) -> dict:
    conn = _conn()
    remove_from_watchlist(conn, watchlist_id)
    return {"deleted": watchlist_id}


# --- Phase 3: delivery + operations ---------------------------------------

@app.get("/alerts")
def get_alerts(date: str | None = Query(None)) -> dict:
    conn = _conn()
    sql = ("SELECT id, user_id, stock_id, date, attribution_id, outcome, sent_at, "
           "delivery_status, error_text FROM alert")
    params: tuple = ()
    if date:
        sql += " WHERE date=?"
        params = (date,)
    sql += " ORDER BY id DESC"
    return {"alerts": [dict(r) for r in conn.execute(sql, params).fetchall()]}


@app.get("/runs")
def get_runs(limit: int = Query(50)) -> dict:
    conn = _conn()
    rows = conn.execute(
        "SELECT id, date, started_at, finished_at, summary_json FROM run_log "
        "ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["summary_json"] = json.loads(d["summary_json"]) if d["summary_json"] else None
        out.append(d)
    return {"runs": out}


@app.post("/run_eod")
def post_run_eod(date: str | None = Query(None), force: bool = Query(True),
                 _: None = Depends(require_token)) -> dict:
    """Manual (admin) EOD trigger. force defaults True so a manual run isn't calendar-gated."""
    from app.jobs.eod import run_eod
    conn = _conn()
    return run_eod(conn, run_date=date, force=force)


@app.get("/users/{user_id}/prefs")
def get_user_prefs(user_id: int) -> dict:
    from app.users import get_prefs
    return {"user_id": user_id, "prefs": get_prefs(_conn(), user_id)}


class PrefsUpdate(BaseModel):
    min_alert_level: str | None = None
    quiet_market_days: bool | None = None
    daily_digest: bool | None = None


@app.put("/users/{user_id}/prefs")
def put_user_prefs(user_id: int, body: PrefsUpdate) -> dict:
    from app.users import set_prefs
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        prefs = set_prefs(_conn(), user_id, updates)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"user_id": user_id, "prefs": prefs}


# --- Phase 4: read endpoints the UI uses + the only new mutation paths ------

@app.get("/stocks/{stock_id}/history")
def stock_history(stock_id: int, days: int = Query(30)) -> dict:
    return {"stock_id": stock_id, "history": webdata.history(_conn(), stock_id, days)}


@app.get("/stocks/{stock_id}/attribution")
def stock_attribution(stock_id: int, date: str | None = Query(None)) -> dict:
    conn = _conn()
    date = date or webdata.latest_run_date(conn)
    if date is None:
        raise HTTPException(404, "no data")
    return webdata.attribution_detail(conn, stock_id, date)


@app.get("/metrics/outcomes")
def metrics_outcomes(days: int = Query(90)) -> dict:
    return webdata.outcomes_distribution(_conn(), days)


@app.post("/exposure/{draft_id}/ratify")
def exposure_ratify(draft_id: int, _: None = Depends(require_token)) -> dict:
    from app.exposure.ratify import approve_draft
    conn = _conn()
    try:
        approve_draft(conn, draft_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"ratified": draft_id}


@app.post("/exposure/{draft_id}/reject")
def exposure_reject(draft_id: int, _: None = Depends(require_token)) -> dict:
    from app.exposure.ratify import reject_draft
    reject_draft(_conn(), draft_id)
    return {"rejected": draft_id}


@app.post("/alerts/retry")
def alerts_retry(_: None = Depends(require_token)) -> dict:
    from app.alerts.telegram import retry_failed
    return retry_failed(_conn())


# --- Portfolio -------------------------------------------------------------
# Valuation is arithmetic over stored EOD closes (see app/portfolio.py). Every
# response carries `as_of` so the client can state the pricing date rather than
# implying a live quote.

class HoldingIn(BaseModel):
    ticker: str
    qty: float
    avg_cost: float


@app.get("/portfolio")
def get_portfolio(as_of: str | None = None,
                  _: None = Depends(require_token)) -> dict:
    from app.portfolio import summary
    return summary(_conn(), as_of=as_of)


@app.get("/portfolio/allocation")
def get_allocation(as_of: str | None = None,
                   _: None = Depends(require_token)) -> list[dict]:
    from app.portfolio import allocation
    return allocation(_conn(), as_of=as_of)


@app.get("/portfolio/history")
def get_portfolio_history(days: int = 90,
                          _: None = Depends(require_token)) -> list[dict]:
    from app.portfolio import history
    return history(_conn(), days=days)


@app.put("/portfolio/holding")
def put_holding(body: HoldingIn, _: None = Depends(require_token)) -> dict:
    from app.portfolio import upsert_holding
    conn = _conn()
    row = conn.execute("SELECT id FROM stock WHERE ticker_nse=?",
                       (body.ticker.upper(),)).fetchone()
    if row is None:
        raise HTTPException(404, f"{body.ticker!r} is not on the watchlist; add it first")
    try:
        hid = upsert_holding(conn, row["id"], body.qty, body.avg_cost)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"holding_id": hid, "ticker": body.ticker.upper()}


@app.delete("/portfolio/holding/{ticker}")
def delete_holding(ticker: str, _: None = Depends(require_token)) -> dict:
    from app.portfolio import remove_holding
    conn = _conn()
    row = conn.execute("SELECT id FROM stock WHERE ticker_nse=?",
                       (ticker.upper(),)).fetchone()
    if row is None:
        raise HTTPException(404, f"unknown ticker {ticker!r}")
    remove_holding(conn, row["id"])
    return {"removed": ticker.upper()}


@app.get("/stocks")
def list_stocks(_: None = Depends(require_token)) -> list[dict]:
    """Every tracked stock with its latest close, day change and gate outcome.

    One query per stock rather than a window function -- the watchlist is dozens of
    names, not thousands, and this stays readable.
    """
    conn = _conn()
    out: list[dict] = []
    for s in conn.execute(
        """SELECT s.id, s.ticker_nse, s.ticker_bse, s.name, sec.name AS sector,
                  (SELECT COUNT(*) FROM holding h WHERE h.stock_id = s.id) AS held
           FROM stock s LEFT JOIN sector sec ON sec.id = s.sector_id
           ORDER BY s.ticker_nse"""
    ).fetchall():
        rows = conn.execute(
            """SELECT date, close, ret, gate_result FROM daily_metric
               WHERE stock_id=? AND close IS NOT NULL
               ORDER BY date DESC LIMIT 2""",
            (s["id"],),
        ).fetchall()
        latest = rows[0] if rows else None
        prev = rows[1] if len(rows) > 1 else None
        change = None
        if latest and prev and prev["close"]:
            change = (latest["close"] - prev["close"]) / prev["close"]
        out.append({
            "stock_id": s["id"],
            "ticker": s["ticker_nse"],
            "name": s["name"],
            "sector": s["sector"],
            "held": bool(s["held"]),
            "date": latest["date"] if latest else None,
            "close": latest["close"] if latest else None,
            "change_pct": change,
            "gate_result": latest["gate_result"] if latest else None,
        })
    return out


@app.get("/stocks/{stock_id}/prices")
def get_prices(stock_id: int, days: int = 90,
               _: None = Depends(require_token)) -> list[dict]:
    """Stored close series for charting -- no network call."""
    rows = _conn().execute(
        """SELECT date, close, ret, gate_result FROM daily_metric
           WHERE stock_id=? AND close IS NOT NULL
           ORDER BY date DESC LIMIT ?""",
        (stock_id, days),
    ).fetchall()
    return [dict(r) for r in rows][::-1]


# Mount the server-rendered UI and its vendored static assets.
from pathlib import Path as _Path  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from app.web.routes import router as _web_router  # noqa: E402

app.include_router(_web_router)
app.mount("/ui/static",
          StaticFiles(directory=str(_Path(__file__).resolve().parent / "web" / "static")),
          name="static")


def run_server():  # pragma: no cover - runtime entrypoint
    """Serve on localhost only (WEB_TOKEN gates the UI; localhost binding is the seatbelt)."""
    import uvicorn
    from app.config import API_HOST, API_PORT
    uvicorn.run(app, host=API_HOST, port=API_PORT)


if __name__ == "__main__":  # pragma: no cover
    run_server()
