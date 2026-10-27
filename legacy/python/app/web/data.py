"""Read-only query helpers for the web UI and its JSON endpoints (Phase 4).

Every value returned here comes straight from a DB column -- no financial quantity is
recomputed. These helpers are shared by the server-rendered pages and the JSON API so the
two never diverge.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import MARKET_TZ, HISTORY_DAYS, OUTCOMES_WINDOW_DAYS, NO_DRIVER_ZERO_WINDOW

IST = ZoneInfo(MARKET_TZ)

# The chip states the UI knows how to render.
EVENTFUL = {"ATTRIBUTED", "MIXED", "INVESTIGATE", "EVENT_NO_MOVE", "DATA_ISSUE",
            "PENDING_ATTRIBUTION", "NO_DRIVER"}


def display_outcome(outcome: str | None) -> str:
    if outcome == "PENDING_ATTRIBUTION":
        return "PENDING"
    return outcome or "—"


def fmt_ist(s: str | None) -> str:
    """Format an ISO timestamp in IST with the zone label."""
    if not s:
        return ""
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return s
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return dt.astimezone(IST).strftime("%Y-%m-%d %H:%M IST")


def latest_run_date(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT MAX(date) FROM daily_metric").fetchone()
    return row[0] if row and row[0] else None


def _outcome_for(conn: sqlite3.Connection, stock_id: int, date: str):
    """(outcome, rendered_text) from attribution if present, else the gate result."""
    row = conn.execute(
        """SELECT outcome, rendered_text FROM attribution
           WHERE stock_id=? AND date=? ORDER BY id DESC LIMIT 1""",
        (stock_id, date),
    ).fetchone()
    if row:
        return row["outcome"], row["rendered_text"]
    gm = conn.execute(
        "SELECT gate_result FROM daily_metric WHERE stock_id=? AND date=?",
        (stock_id, date),
    ).fetchone()
    return (gm["gate_result"] if gm else None), None


def _first_sentence(text: str | None) -> str:
    if not text:
        return ""
    for sep in (". ", ".\n", "\n"):
        i = text.find(sep)
        if i != -1:
            return text[: i + 1].strip()
    return text.strip()[:200]


def dashboard(conn: sqlite3.Connection, date: str) -> list[dict]:
    """One row per watchlisted stock for ``date``. Eventful first, then |move| desc."""
    rows = []
    for s in conn.execute(
        """SELECT DISTINCT s.id, s.ticker_nse, s.name FROM stock s
           JOIN watchlist_item w ON w.stock_id = s.id"""
    ).fetchall():
        outcome, rendered = _outcome_for(conn, s["id"], date)
        dm = conn.execute(
            "SELECT ret FROM daily_metric WHERE stock_id=? AND date=?", (s["id"], date)
        ).fetchone()
        move = dm["ret"] if dm else None
        rows.append({
            "stock_id": s["id"], "ticker": s["ticker_nse"], "name": s["name"],
            "move": move, "outcome": outcome, "outcome_display": display_outcome(outcome),
            "teaser": _first_sentence(rendered),
        })
    rows.sort(key=lambda r: (0 if (r["outcome"] in EVENTFUL) else 1,
                             -abs(r["move"] or 0.0)))
    return rows


def stock_header(conn: sqlite3.Connection, stock_id: int, date: str) -> dict | None:
    s = conn.execute(
        """SELECT s.id, s.ticker_nse, s.ticker_bse, s.name, sec.name AS sector
           FROM stock s LEFT JOIN sector sec ON sec.id = s.sector_id WHERE s.id=?""",
        (stock_id,),
    ).fetchone()
    if not s:
        return None
    dm = conn.execute(
        """SELECT ret, index_ret, sigma60, beta60, sigma_idio, idio_ret, vol_zscore,
                  gate_result, gate_inputs_json
           FROM daily_metric WHERE stock_id=? AND date=?""",
        (stock_id, date),
    ).fetchone()
    gate = dict(dm) if dm else {}
    if gate.get("gate_inputs_json"):
        try:
            gate["config"] = json.loads(gate["gate_inputs_json"]).get("config", {})
        except (json.JSONDecodeError, TypeError):
            gate["config"] = {}
    return {"stock": dict(s), "date": date, "gate": gate}


def _evidence_for(conn: sqlite3.Connection, ids: list[int]) -> list[dict]:
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    out = []
    for e in conn.execute(
        f"""SELECT id, tier, source, url, headline, first_seen_at,
                   exchange_dissemination_at, suspect_reactive, factor_id
            FROM evidence WHERE id IN ({placeholders})""", ids
    ).fetchall():
        d = dict(e)
        d["first_seen_ist"] = fmt_ist(e["first_seen_at"])
        d["dissemination_ist"] = fmt_ist(e["exchange_dissemination_at"])
        d["tier_label"] = {1: "Exchange filing", 2: "Macro data", 3: "News"}.get(e["tier"], "")
        d["suspect_reactive"] = bool(e["suspect_reactive"])
        out.append(d)
    return out


def attribution_detail(conn: sqlite3.Connection, stock_id: int, date: str) -> dict:
    """Full detail for the stock-detail page: outcome, verbatim text, driver+evidence join."""
    a = conn.execute(
        """SELECT id, outcome, rendered_text, model_version FROM attribution
           WHERE stock_id=? AND date=? ORDER BY id DESC LIMIT 1""",
        (stock_id, date),
    ).fetchone()
    if not a:
        outcome, rendered = _outcome_for(conn, stock_id, date)
        return {"outcome": outcome, "outcome_display": display_outcome(outcome),
                "rendered_text": rendered, "drivers": []}
    drivers = []
    for d in conn.execute(
        """SELECT rank, factor_id, evidence_ids, chain_text, direction, confidence,
                  confidence_reason FROM driver WHERE attribution_id=? ORDER BY rank ASC""",
        (a["id"],),
    ).fetchall():
        ids = json.loads(d["evidence_ids"] or "[]")
        drivers.append({
            "rank": d["rank"], "factor_id": d["factor_id"], "chain_text": d["chain_text"],
            "direction": d["direction"], "confidence": d["confidence"],
            "confidence_reason": d["confidence_reason"],
            "evidence": _evidence_for(conn, ids),
        })
    return {
        "attribution_id": a["id"], "outcome": a["outcome"],
        "outcome_display": display_outcome(a["outcome"]),
        "rendered_text": a["rendered_text"], "model_version": a["model_version"],
        "drivers": drivers,
    }


def history(conn: sqlite3.Connection, stock_id: int, days: int = HISTORY_DAYS) -> list[dict]:
    out = []
    for dm in conn.execute(
        "SELECT date FROM daily_metric WHERE stock_id=? ORDER BY date DESC LIMIT ?",
        (stock_id, days),
    ).fetchall():
        outcome, _ = _outcome_for(conn, stock_id, dm["date"])
        out.append({"date": dm["date"], "outcome": outcome,
                    "outcome_display": display_outcome(outcome)})
    return list(reversed(out))


def outcomes_distribution(conn: sqlite3.Connection, days: int = OUTCOMES_WINDOW_DAYS) -> dict:
    """Outcome counts over the trailing window + the NO_DRIVER-zero callout."""
    dates = [r[0] for r in conn.execute(
        "SELECT DISTINCT date FROM daily_metric ORDER BY date DESC LIMIT ?", (days,)
    ).fetchall()]
    counts: dict[str, int] = {}
    for stock_id, date in conn.execute(
        "SELECT stock_id, date FROM daily_metric WHERE date IN "
        f"({','.join('?' for _ in dates) or 'NULL'})", dates
    ).fetchall() if dates else []:
        outcome, _ = _outcome_for(conn, stock_id, date)
        key = display_outcome(outcome)
        counts[key] = counts.get(key, 0) + 1

    # NO_DRIVER-frequency check over the trailing eventful window (DESIGN §7).
    eventful = 0
    no_driver = 0
    for stock_id, date in conn.execute(
        "SELECT stock_id, date FROM daily_metric ORDER BY date DESC LIMIT ?",
        (NO_DRIVER_ZERO_WINDOW * 50,)  # generous cap; filtered below
    ).fetchall():
        outcome, _ = _outcome_for(conn, stock_id, date)
        if outcome in ("ATTRIBUTED", "NO_DRIVER"):
            eventful += 1
            if outcome == "NO_DRIVER":
                no_driver += 1
    no_driver_zero = eventful >= 10 and no_driver == 0
    return {"counts": counts, "no_driver_zero_warning": no_driver_zero,
            "eventful_considered": eventful}


def strip_metrics(conn: sqlite3.Connection) -> dict:
    by_stage: dict[str, int] = {}
    by_reason: dict[str, int] = {}
    total = 0
    for (log_json,) in conn.execute(
        "SELECT verifier_log_json FROM attribution WHERE verifier_log_json IS NOT NULL"
    ).fetchall():
        for entry in json.loads(log_json):
            total += 1
            st = entry.get("stage", "?")
            by_stage[st] = by_stage.get(st, 0) + 1
            r = (entry.get("reason") or "")[:60]
            by_reason[r] = by_reason.get(r, 0) + 1
    return {"total": total, "by_stage": by_stage, "by_reason": by_reason}


def run_log(conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
    out = []
    for r in conn.execute(
        "SELECT id, date, started_at, finished_at, summary_json FROM run_log "
        "ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall():
        d = dict(r)
        d["summary"] = json.loads(d.pop("summary_json")) if d["summary_json"] else None
        out.append(d)
    return out


def alert_log(conn: sqlite3.Connection, limit: int = 100) -> list[dict]:
    return [dict(r) for r in conn.execute(
        """SELECT al.id, al.date, al.outcome, al.delivery_status, al.error_text,
                  al.sent_at, s.ticker_nse
           FROM alert al JOIN stock s ON s.id = al.stock_id
           ORDER BY al.id DESC LIMIT ?""", (limit,)
    ).fetchall()]


def pending_drafts(conn: sqlite3.Connection, stock_id: int) -> list[dict]:
    return [dict(r) for r in conn.execute(
        """SELECT id, factor_id, channel, pnl_line, direction, condition_note,
                  strength, rationale, source_citation
           FROM exposure WHERE stock_id=? AND status='draft' ORDER BY factor_id""",
        (stock_id,),
    ).fetchall()]
