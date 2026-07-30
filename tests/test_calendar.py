"""Trading calendar, holiday skip, and run_log."""

from __future__ import annotations

from app.jobs.calendar import is_trading_day, skip_reason, start_run, finish_run
from app.jobs.eod import run_eod


def test_weekend_is_not_trading_day():
    assert is_trading_day("2026-07-11") is False   # Saturday
    assert is_trading_day("2026-07-12") is False   # Sunday
    assert is_trading_day("2026-07-10") is True    # Friday


def test_listed_holiday_skipped():
    assert is_trading_day("2026-01-26") is False    # Republic Day (seeded)
    assert skip_reason("2026-01-26") == "NSE holiday"
    assert skip_reason("2026-07-11") == "weekend"
    assert skip_reason("2026-07-10") is None


def test_run_eod_skips_non_trading_day_without_network(conn):
    # A weekend run_date returns skipped BEFORE any price fetch, and logs the attempt.
    result = run_eod(conn, run_date="2026-07-11", force=False)
    assert result["skipped"] == "weekend"
    row = conn.execute("SELECT date, summary_json FROM run_log ORDER BY id DESC LIMIT 1").fetchone()
    assert row["date"] == "2026-07-11"
    assert "weekend" in row["summary_json"]


def test_run_log_lifecycle(conn):
    rid = start_run(conn, "2026-07-10")
    finish_run(conn, rid, {"stocks": 3, "ok": True})
    row = conn.execute("SELECT started_at, finished_at, summary_json FROM run_log WHERE id=?",
                       (rid,)).fetchone()
    assert row["started_at"] and row["finished_at"]
    assert '"ok": true' in row["summary_json"]
