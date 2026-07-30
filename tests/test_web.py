"""Web UI tests: auth gating, ratify/reject via UI, forbidden-language scan, and the
dashboard rendering all outcome states. No network, no LLM."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.render import _FORBIDDEN

WEB_DIR = Path("app/web")
DATE = "2026-07-10"


@pytest.fixture()
def web(tmp_path, monkeypatch):
    """A logged-in TestClient wired to a fresh seeded DB, plus a direct connection."""
    db = str(tmp_path / "web.db")
    monkeypatch.setenv("WEB_TOKEN", "secret")
    monkeypatch.setattr("app.db.DB_PATH", db, raising=False)

    from app.db import fresh_db
    from app.exposure.registry import seed_all
    conn = fresh_db(db)
    seed_all(conn)

    from starlette.testclient import TestClient
    from app.api import app
    client = TestClient(app)
    client.post("/ui/login", data={"token": "secret"})
    return client, conn


def _seed_stock(conn, ticker, sector="PAINTS"):
    from app.users import register_user
    from app.watchlist import upsert_stock, add_to_watchlist
    uid = register_user(conn, "web-ui", "Web UI")
    sid = upsert_stock(conn, name=f"{ticker} Ltd", ticker_nse=ticker, ticker_bse=None,
                       sector_name=sector)
    add_to_watchlist(conn, sid, user_id=str(uid))
    return sid


def _metric(conn, sid, ret=-0.03, gate="INVESTIGATE"):
    conn.execute("INSERT OR REPLACE INTO daily_metric "
                 "(stock_id,date,ret,gate_result,gate_inputs_json) VALUES (?,?,?,?, '{}')",
                 (sid, DATE, ret, gate))
    conn.commit()


def _attr(conn, sid, outcome, text="x"):
    conn.execute("INSERT INTO attribution (stock_id,date,trigger,outcome,rendered_text,created_at) "
                 "VALUES (?,?,?,?,?,?)",
                 (sid, DATE, "move", outcome, text, datetime.now(timezone.utc).isoformat()))
    conn.commit()


# --- auth ------------------------------------------------------------------

def test_ui_requires_auth(web, tmp_path, monkeypatch):
    _client, _conn = web
    from starlette.testclient import TestClient
    from app.api import app
    anon = TestClient(app)  # no login cookie
    assert anon.get("/ui", follow_redirects=False).status_code == 303
    assert anon.get("/ui/ops", follow_redirects=False).status_code == 303
    assert anon.get("/ui", follow_redirects=False).headers["location"] == "/ui/login"


def test_mutating_api_requires_token(web):
    _client, conn = web
    from starlette.testclient import TestClient
    from app.api import app
    anon = TestClient(app)
    assert anon.post("/run_eod").status_code == 401
    assert anon.post("/exposure/1/ratify").status_code == 401
    assert anon.post("/alerts/retry").status_code == 401


def test_bad_login_rejected(web):
    client, _conn = web
    from starlette.testclient import TestClient
    from app.api import app
    anon = TestClient(app)
    assert anon.post("/ui/login", data={"token": "wrong"}).status_code == 401


# --- dashboard: all outcome states ----------------------------------------

def test_dashboard_renders_all_outcome_states(web):
    client, conn = web
    states = ["NOISE", "MARKET", "ATTRIBUTED", "NO_DRIVER", "EVENT_NO_MOVE",
              "DATA_ISSUE", "PENDING_ATTRIBUTION"]
    for i, outcome in enumerate(states):
        sid = _seed_stock(conn, f"STK{i}")
        _metric(conn, sid, ret=-0.02 * (i + 1))
        _attr(conn, sid, outcome, text=f"{outcome} explanation.")
    html = client.get(f"/ui?date={DATE}").text
    for chip in ["NOISE", "MARKET", "ATTRIBUTED", "NO_DRIVER", "EVENT_NO_MOVE",
                 "DATA_ISSUE", "PENDING"]:
        assert chip in html, f"dashboard missing the {chip} chip"


# --- ratify / reject via the UI -------------------------------------------

def test_ratify_via_ui_promotes_draft(web):
    client, conn = web
    from app.exposure.draft import write_drafts
    from app.exposure.profiles import effective_factor_ids
    sid = _seed_stock(conn, "ONGCX", sector="UPSTREAM_OIL")
    write_drafts(conn, sid, [{
        "factor_id": "GOLD", "channel": "output_price", "pnl_line": "rev",
        "direction": "+1", "strength": "secondary", "rationale": "adds edge",
        "source_citation": "AR p.1"}])
    draft_id = conn.execute("SELECT id FROM exposure WHERE stock_id=? AND status='draft'",
                            (sid,)).fetchone()[0]
    assert "GOLD" not in effective_factor_ids(conn, sid)

    r = client.post(f"/ui/exposure/{draft_id}/ratify", data={"stock_id": sid},
                    follow_redirects=False)
    assert r.status_code == 303
    # Re-read from a fresh connection to the same DB.
    from app.db import connect
    c2 = connect(conn.execute("PRAGMA database_list").fetchone()[2])
    assert "GOLD" in effective_factor_ids(c2, sid)


def test_reject_via_ui_removes_draft(web):
    client, conn = web
    from app.exposure.draft import write_drafts
    sid = _seed_stock(conn, "ONGCY", sector="UPSTREAM_OIL")
    write_drafts(conn, sid, [{
        "factor_id": "GOLD", "channel": "output_price", "pnl_line": "rev",
        "direction": "+1", "strength": "secondary", "rationale": "x",
        "source_citation": "y"}])
    draft_id = conn.execute("SELECT id FROM exposure WHERE stock_id=? AND status='draft'",
                            (sid,)).fetchone()[0]
    client.post(f"/ui/exposure/{draft_id}/reject", data={"stock_id": sid},
                follow_redirects=False)
    from app.db import connect
    c2 = connect(conn.execute("PRAGMA database_list").fetchone()[2])
    assert c2.execute("SELECT COUNT(*) FROM exposure WHERE id=?", (draft_id,)).fetchone()[0] == 0


# --- no-advice guarantee ---------------------------------------------------

def test_no_forbidden_language_in_templates_or_css():
    files = list((WEB_DIR / "templates").glob("*.html")) + [WEB_DIR / "static" / "style.css"]
    phrases = [w for w in _FORBIDDEN if " " in w]
    words = [w for w in _FORBIDDEN if " " not in w]
    for f in files:
        text = f.read_text(encoding="utf-8").lower()
        for p in phrases:
            assert p not in text, f"{f.name} contains forbidden phrase {p!r}"
        for w in words:
            assert not re.search(rf"\b{re.escape(w)}\b", text), \
                f"{f.name} contains forbidden word {w!r}"


def test_rendered_pages_contain_no_advice(web):
    client, conn = web
    sid = _seed_stock(conn, "AP1")
    _metric(conn, sid)
    _attr(conn, sid, "ATTRIBUTED", text="Crude rose, margin fell. Negative for this stock.")
    for path in ["/ui", f"/ui/stock/{sid}", f"/ui/stock/{sid}/profile", "/ui/ops", "/ui/login"]:
        low = client.get(path).text.lower()
        for w in _FORBIDDEN:
            if " " in w:
                assert w not in low, f"{path} contains {w!r}"
            else:
                assert not re.search(rf"\b{re.escape(w)}\b", low), f"{path} contains {w!r}"


# --- JSON endpoints --------------------------------------------------------

def test_json_history_and_outcomes(web):
    client, conn = web
    sid = _seed_stock(conn, "AP2")
    _metric(conn, sid)
    _attr(conn, sid, "ATTRIBUTED")
    assert client.get(f"/stocks/{sid}/history?days=30").json()["history"][0]["outcome"] == "ATTRIBUTED"
    assert "counts" in client.get("/metrics/outcomes?days=90").json()
