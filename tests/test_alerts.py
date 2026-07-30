"""Alert selection matrix, dedupe-on-rerun, and at-most-once delivery."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.users import register_user, set_prefs
from app.watchlist import add_to_watchlist
from app.alerts.selector import select_alerts, is_alert_worthy
from app.alerts.telegram import deliver_alerts, retry_failed

DATE = "2026-07-10"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _attr(conn, stock_id, outcome, rendered="explanation text", trigger="move"):
    cur = conn.execute(
        """INSERT INTO attribution (stock_id, date, trigger, outcome, rendered_text, created_at)
           VALUES (?,?,?,?,?,?)""",
        (stock_id, DATE, trigger, outcome, rendered, _now()),
    )
    conn.commit()
    return cur.lastrowid


def _metric(conn, stock_id, ret=-0.03, gate="INVESTIGATE"):
    conn.execute(
        """INSERT OR REPLACE INTO daily_metric (stock_id, date, ret, gate_result, gate_inputs_json)
           VALUES (?,?,?,?, '{}')""",
        (stock_id, DATE, ret, gate),
    )
    conn.commit()


def _driver(conn, attribution_id, confidence="HIGH"):
    conn.execute(
        """INSERT INTO driver (attribution_id, rank, evidence_ids, confidence)
           VALUES (?,1,'[1]',?)""",
        (attribution_id, confidence),
    )
    conn.commit()


# --- the outcome x preference matrix (pure) --------------------------------

@pytest.mark.parametrize("outcome,level,quiet,expected", [
    ("ATTRIBUTED", "ALL", False, True),
    ("NO_DRIVER", "ALL", False, True),
    ("EVENT_NO_MOVE", "ALL", False, True),
    ("MARKET", "ALL", False, True),
    ("MARKET", "ALL", True, False),          # quiet_market_days suppresses MARKET
    ("NOISE", "ALL", False, False),          # never a user alert
    ("DATA_ISSUE", "ALL", False, False),     # admin log only
    ("PENDING_ATTRIBUTION", "ALL", False, False),
    ("ATTRIBUTED", "EXPLAINED_ONLY", False, True),
    ("NO_DRIVER", "EXPLAINED_ONLY", False, False),
    ("MARKET", "EXPLAINED_ONLY", False, False),
    ("EVENT_NO_MOVE", "EXPLAINED_ONLY", False, True),
    ("ATTRIBUTED", "HIGH_ONLY", False, True),   # with HIGH top driver (passed below)
    ("NO_DRIVER", "HIGH_ONLY", False, False),
])
def test_alert_matrix(outcome, level, quiet, expected):
    prefs = {"min_alert_level": level, "quiet_market_days": quiet}
    top = "HIGH" if (level == "HIGH_ONLY" and outcome == "ATTRIBUTED") else None
    assert is_alert_worthy(outcome, prefs, top) is expected


def test_high_only_suppresses_medium_attributed():
    prefs = {"min_alert_level": "HIGH_ONLY"}
    assert is_alert_worthy("ATTRIBUTED", prefs, "MEDIUM") is False
    assert is_alert_worthy("ATTRIBUTED", prefs, "HIGH") is True


# --- selection + dedupe-on-rerun -------------------------------------------

def test_select_and_dedupe_on_rerun(conn, tcs):
    uid = register_user(conn, "999")
    add_to_watchlist(conn, tcs, user_id=str(uid))
    aid = _attr(conn, tcs, "ATTRIBUTED")
    _metric(conn, tcs)

    first = select_alerts(conn, DATE)
    assert len(first) == 1 and first[0].attribution_id == aid

    sent = []
    stats = deliver_alerts(conn, first, sender=lambda cid, txt: sent.append((cid, txt)))
    assert stats["sent"] == 1 and len(sent) == 1

    # Rerun: the alert row is recorded, so selection returns nothing.
    assert select_alerts(conn, DATE) == []
    # And re-delivering the same list dedupes rather than double-sending.
    stats2 = deliver_alerts(conn, first, sender=lambda cid, txt: sent.append((cid, txt)))
    assert stats2 == {"sent": 0, "failed": 0, "deduped": 1}
    assert len(sent) == 1


def test_delivery_failure_then_retry(conn, tcs):
    uid = register_user(conn, "42")
    add_to_watchlist(conn, tcs, user_id=str(uid))
    _attr(conn, tcs, "ATTRIBUTED")
    _metric(conn, tcs)
    alerts = select_alerts(conn, DATE)

    def boom(cid, txt):
        raise RuntimeError("telegram 500")

    stats = deliver_alerts(conn, alerts, sender=boom)
    assert stats["failed"] == 1
    row = conn.execute("SELECT delivery_status, error_text FROM alert").fetchone()
    assert row["delivery_status"] == "failed" and "telegram 500" in row["error_text"]

    good = []
    rstats = retry_failed(conn, sender=lambda cid, txt: good.append(cid))
    assert rstats["recovered"] == 1
    assert conn.execute("SELECT delivery_status FROM alert").fetchone()[0] == "sent"


def test_high_only_pref_selection(conn, tcs):
    uid = register_user(conn, "7")
    set_prefs(conn, uid, {"min_alert_level": "HIGH_ONLY"})
    add_to_watchlist(conn, tcs, user_id=str(uid))
    aid = _attr(conn, tcs, "ATTRIBUTED")
    _metric(conn, tcs)
    _driver(conn, aid, confidence="MEDIUM")     # only a MEDIUM driver
    assert select_alerts(conn, DATE) == []      # HIGH_ONLY suppresses it

    _driver(conn, aid, confidence="HIGH")        # now a HIGH driver exists (rank 1 tie)
    # rank-1 order is by rank asc; both rank 1 -> ensure a HIGH is first by re-inserting
    conn.execute("DELETE FROM driver WHERE attribution_id=?", (aid,))
    _driver(conn, aid, confidence="HIGH")
    assert len(select_alerts(conn, DATE)) == 1
