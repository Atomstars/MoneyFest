"""Telegram message composition/chunking (pure) and command dispatch (no network)."""

from __future__ import annotations

from app.alerts.telegram import chunk_message, compose_message, dispatch
from app.users import register_user
from app.watchlist import add_to_watchlist


def test_chunk_at_4096():
    text = "\n".join(f"line {i} " + "x" * 50 for i in range(300))  # > 4096 chars
    chunks = chunk_message(text, limit=4096)
    assert len(chunks) > 1
    assert all(len(c) <= 4096 for c in chunks)
    assert "".join(chunks).replace("\n", "") == text.replace("\n", "")


def test_chunk_splits_overlong_single_line():
    line = "y" * 9000
    chunks = chunk_message(line, limit=4096)
    assert all(len(c) <= 4096 for c in chunks)
    assert "".join(chunks) == line


def test_compose_escapes_html_and_appends_disclaimer():
    msg = compose_message("TCS · 2026-07-10 · moved -1.20%", "Fell on <weak> results & guidance")
    assert "&lt;weak&gt;" in msg          # HTML-escaped
    assert "&amp;" in msg
    assert "not investment advice" in msg


def test_short_message_single_chunk():
    assert chunk_message("hello") == ["hello"]


# --- command dispatch (thin) ----------------------------------------------

def test_start_registers_and_lists(conn):
    reply = dispatch(conn, "555", "/start", "Akash")
    assert "Welcome" in reply
    # empty watchlist
    assert "empty" in dispatch(conn, "555", "/list").lower()


def test_dispatch_requires_start_first(conn):
    assert "start" in dispatch(conn, "111", "/list").lower()


def test_explain_returns_latest_rendered(conn, tcs):
    register_user(conn, "555")
    conn.execute(
        """INSERT INTO attribution (stock_id,date,trigger,outcome,rendered_text,created_at)
           VALUES (?,?, 'move','NOISE','TCS moved 0.4%, nothing to explain.', '2026-07-10')""",
        (tcs, "2026-07-10"),
    )
    conn.commit()
    reply = dispatch(conn, "555", "/explain TCS")
    assert "nothing to explain" in reply  # NOISE days answer too


def test_prefs_roundtrip(conn):
    register_user(conn, "555")
    reply = dispatch(conn, "555", "/prefs min_alert_level=HIGH_ONLY")
    assert "HIGH_ONLY" in reply
    reply2 = dispatch(conn, "555", "/prefs")
    assert "min_alert_level = HIGH_ONLY" in reply2


def test_remove_command(conn, tcs):
    uid = register_user(conn, "555")
    add_to_watchlist(conn, tcs, user_id=str(uid))
    assert "Removed TCS" in dispatch(conn, "555", "/remove TCS")
    assert "empty" in dispatch(conn, "555", "/list").lower()
