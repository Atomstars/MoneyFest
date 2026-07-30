"""Telegram delivery + inbound command worker (Phase 3).

Raw Bot API over httpx -- no heavy framework. Rendered text is delivered VERBATIM; the
only transforms are HTML-escaping, 4096-char chunking, a one-line metadata header, and
the fixed disclaimer appended at delivery. The bot layer contains no business logic --
handlers are thin wrappers over users.py / onboard.py / DB reads.

Delivery is at-most-once: the alert row is claimed (inserted, marked) BEFORE the network
call, so an EOD rerun never double-sends. Secrets come only from env; the token is never
logged.

    python -m app.alerts.telegram poll      # run the long-polling command worker
"""

from __future__ import annotations

import html
import os
import sqlite3
from datetime import datetime, timezone

from app.config import (
    DISCLAIMER, TELEGRAM_API_BASE, TELEGRAM_MESSAGE_LIMIT, TELEGRAM_POLL_TIMEOUT,
)

try:
    import httpx
except Exception:  # pragma: no cover
    httpx = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- Pure message helpers (no network) -------------------------------------

def compose_message(metadata_line: str, rendered_text: str,
                    disclaimer: str = DISCLAIMER) -> str:
    """metadata header + verbatim rendered text + disclaimer. HTML for Telegram."""
    body = (f"<b>{html.escape(metadata_line)}</b>\n\n"
            f"{html.escape(rendered_text)}\n\n"
            f"<i>{html.escape(disclaimer)}</i>")
    return body


def chunk_message(text: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    """Split into <=limit chunks, preferring newline boundaries. Never splits mid-line
    unless a single line exceeds the limit."""
    if len(text) <= limit:
        return [text]
    chunks, cur = [], ""
    for line in text.split("\n"):
        while len(line) > limit:  # a single very long line
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(line[:limit])
            line = line[limit:]
        add = (("\n" if cur else "") + line)
        if len(cur) + len(add) > limit:
            chunks.append(cur)
            cur = line
        else:
            cur += add
    if cur:
        chunks.append(cur)
    return chunks


# --- Network send ----------------------------------------------------------

def _token() -> str:
    tok = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not tok:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set")
    return tok


def send_message(chat_id: str, text: str) -> None:
    """Send (chunked) to a chat via the Bot API. Raises on HTTP error."""
    if httpx is None:  # pragma: no cover
        raise RuntimeError("httpx not installed")
    url = f"{TELEGRAM_API_BASE}/bot{_token()}/sendMessage"
    with httpx.Client(timeout=30.0) as c:
        for chunk in chunk_message(text):
            resp = c.post(url, json={"chat_id": chat_id, "text": chunk,
                                     "parse_mode": "HTML"})
            resp.raise_for_status()


# --- Delivery (at-most-once) -----------------------------------------------

def deliver_alerts(conn: sqlite3.Connection, alerts, sender=send_message) -> dict:
    """Record + send each alert. ``sender(chat_id, text)`` is injectable for tests."""
    sent = failed = deduped = 0
    for a in alerts:
        # Claim the row BEFORE the network call (at-most-once). If it already exists
        # (rerun), INSERT OR IGNORE no-ops and we skip -- never double-send.
        cur = conn.execute(
            """INSERT OR IGNORE INTO alert
                 (user_id, stock_id, date, attribution_id, outcome, sent_at, delivery_status)
               VALUES (?,?,?,?,?,?, 'sent')""",
            (a.user_id, a.stock_id, a.date, a.attribution_id, a.outcome, _now()),
        )
        conn.commit()
        if cur.rowcount == 0:
            deduped += 1
            continue
        text = compose_message(a.metadata_line(), a.rendered_text)
        try:
            if a.chat_id:
                sender(a.chat_id, text)
            sent += 1
        except Exception as exc:
            conn.execute(
                "UPDATE alert SET delivery_status='failed', error_text=? "
                "WHERE user_id=? AND attribution_id=?",
                (str(exc)[:500], a.user_id, a.attribution_id),
            )
            conn.commit()
            failed += 1
    return {"sent": sent, "failed": failed, "deduped": deduped}


def retry_failed(conn: sqlite3.Connection, sender=send_message) -> dict:
    """Retry every failed alert once. Rebuilds the message from stored rows."""
    retried = recovered = 0
    rows = conn.execute(
        """SELECT al.id, al.user_id, al.attribution_id, al.date, al.outcome,
                  u.telegram_chat_id AS chat_id, a.rendered_text,
                  s.ticker_nse, s.name, dm.ret
           FROM alert al
           JOIN user u ON CAST(u.id AS TEXT) = al.user_id
           JOIN attribution a ON a.id = al.attribution_id
           JOIN stock s ON s.id = al.stock_id
           LEFT JOIN daily_metric dm ON dm.stock_id = al.stock_id AND dm.date = al.date
           WHERE al.delivery_status = 'failed'"""
    ).fetchall()
    for r in rows:
        retried += 1
        pct = "n/a" if r["ret"] is None else f"{r['ret'] * 100:+.2f}%"
        meta = f"{r['ticker_nse'] or r['name']} · {r['date']} · moved {pct}"
        text = compose_message(meta, r["rendered_text"] or "")
        try:
            if r["chat_id"]:
                sender(r["chat_id"], text)
            conn.execute(
                "UPDATE alert SET delivery_status='sent', sent_at=?, error_text=NULL WHERE id=?",
                (_now(), r["id"]),
            )
            conn.commit()
            recovered += 1
        except Exception as exc:
            conn.execute("UPDATE alert SET error_text=? WHERE id=?",
                         (str(exc)[:500], r["id"]))
            conn.commit()
    return {"retried": retried, "recovered": recovered}


# --- Inbound command handling (thin) ---------------------------------------

def dispatch(conn: sqlite3.Connection, chat_id: str, text: str,
             from_name: str | None = None) -> str:
    """Route a slash command to the right thin handler. Returns the reply text."""
    from app.users import register_user, user_by_chat, set_prefs, get_prefs
    from app.watchlist import remove_from_watchlist

    text = (text or "").strip()
    parts = text.split()
    cmd = parts[0].lower() if parts else ""
    arg = parts[1] if len(parts) > 1 else None

    if cmd == "/start":
        register_user(conn, chat_id, from_name)
        return ("Welcome. I explain why your NSE/BSE stocks moved.\n"
                "Commands: /add TICKER, /remove TICKER, /list, /explain TICKER, "
                "/prefs key=value.")

    user = user_by_chat(conn, chat_id)
    if user is None:
        return "Please send /start first."
    uid = user["id"]

    if cmd == "/add":
        if not arg:
            return "Usage: /add TICKER"
        from app.onboard import add_stock
        res = add_stock(conn, uid, arg)
        msg = f"Added {res.ticker_nse} ({res.name}); sector={res.sector or 'none'}."
        return msg + (f"\nNote: {res.warning}" if res.warning else "")

    if cmd == "/remove":
        if not arg:
            return "Usage: /remove TICKER"
        row = conn.execute(
            """SELECT w.id FROM watchlist_item w JOIN stock s ON s.id=w.stock_id
               WHERE w.user_id=? AND s.ticker_nse=?""",
            (str(uid), arg.upper()),
        ).fetchone()
        if not row:
            return f"{arg.upper()} is not on your watchlist."
        remove_from_watchlist(conn, row[0])
        return f"Removed {arg.upper()}."

    if cmd == "/list":
        rows = conn.execute(
            """SELECT s.ticker_nse, s.name FROM watchlist_item w
               JOIN stock s ON s.id=w.stock_id WHERE w.user_id=? ORDER BY s.ticker_nse""",
            (str(uid),),
        ).fetchall()
        if not rows:
            return "Your watchlist is empty. Add one with /add TICKER."
        return "Watchlist:\n" + "\n".join(f"- {r[0]} ({r[1]})" for r in rows)

    if cmd == "/explain":
        if not arg:
            return "Usage: /explain TICKER"
        row = conn.execute(
            """SELECT a.rendered_text, a.date, a.outcome FROM attribution a
               JOIN stock s ON s.id=a.stock_id
               WHERE s.ticker_nse=? AND a.rendered_text IS NOT NULL
               ORDER BY a.date DESC, a.id DESC LIMIT 1""",
            (arg.upper(),),
        ).fetchone()
        if not row:
            return f"No explanation on record yet for {arg.upper()}."
        return f"{arg.upper()} · {row['date']} · {row['outcome']}\n\n{row['rendered_text']}"

    if cmd == "/prefs":
        updates = {}
        for kv in parts[1:]:
            if "=" in kv:
                k, v = kv.split("=", 1)
                updates[k.strip()] = v.strip()
        if updates:
            try:
                prefs = set_prefs(conn, uid, updates)
            except ValueError as e:
                return str(e)
        else:
            prefs = get_prefs(conn, uid)
        return "Preferences:\n" + "\n".join(f"- {k} = {v}" for k, v in prefs.items())

    return "Unknown command. Try /list or /explain TICKER."


def poll(conn: sqlite3.Connection | None = None) -> None:  # pragma: no cover - network loop
    """Long-poll getUpdates and dispatch commands. Ctrl-C to stop."""
    if httpx is None:
        raise RuntimeError("httpx not installed")
    from app.db import fresh_db
    conn = conn or fresh_db()
    base = f"{TELEGRAM_API_BASE}/bot{_token()}"
    offset = None
    print("[telegram] polling for commands...")
    with httpx.Client(timeout=TELEGRAM_POLL_TIMEOUT + 10) as c:
        while True:
            params = {"timeout": TELEGRAM_POLL_TIMEOUT}
            if offset is not None:
                params["offset"] = offset
            try:
                resp = c.get(f"{base}/getUpdates", params=params)
                resp.raise_for_status()
                updates = resp.json().get("result", [])
            except Exception as exc:
                print(f"[telegram] poll error: {exc}")
                continue
            for upd in updates:
                offset = upd["update_id"] + 1
                msg = upd.get("message") or {}
                chat = msg.get("chat", {})
                chat_id = str(chat.get("id")) if chat.get("id") is not None else None
                text = msg.get("text", "")
                if not chat_id or not text.startswith("/"):
                    continue
                name = (msg.get("from") or {}).get("first_name")
                try:
                    reply = dispatch(conn, chat_id, text, name)
                except Exception as exc:
                    reply = f"Error: {exc}"
                try:
                    send_message(chat_id, html.escape(reply))
                except Exception as exc:
                    print(f"[telegram] reply failed: {exc}")


if __name__ == "__main__":  # pragma: no cover
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "poll":
        poll()
    else:
        print("usage: python -m app.alerts.telegram poll")
