"""Tier-3 ingestor: business-news RSS.

Fetches a small curated set of RSS feeds, tags each item with any watchlist stock it
mentions (name/symbol match) and any registry factor it mentions (keyword match), and
flags items first seen after 09:30 IST on a move day as ``suspect_reactive`` (they are
likely coverage OF the move, not a cause -- the feedback-loop failure in DESIGN.md #7).

The tagging logic is pure and unit-tested without network access.

Runnable standalone:  python -m app.ingest.news
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime

from app.config import NEWS_RSS_FEEDS
from app.exposure.registry import factor_keywords
from app.ingest.normalize import EvidenceItem, upsert_evidence, now_ist_iso

try:
    import feedparser
except Exception:  # pragma: no cover
    feedparser = None


def _stock_name_map(conn: sqlite3.Connection) -> dict[int, list[str]]:
    """stock_id -> list of lowercase match tokens (name + NSE symbol)."""
    out: dict[int, list[str]] = {}
    for r in conn.execute(
        """SELECT DISTINCT s.id, s.name, s.ticker_nse
           FROM stock s JOIN watchlist_item w ON w.stock_id = s.id"""
    ).fetchall():
        tokens = []
        if r["name"]:
            tokens.append(r["name"].lower())
        if r["ticker_nse"]:
            tokens.append(r["ticker_nse"].lower())
        out[r["id"]] = tokens
    return out


def _match(text: str, token: str) -> bool:
    """Word-boundary, case-insensitive containment for a token/phrase."""
    return re.search(r"\b" + re.escape(token) + r"\b", text) is not None


def tag_item(headline: str, body: str,
             stock_tokens: dict[int, list[str]],
             kw: dict[str, list[str]]) -> tuple[list[int], list[str]]:
    """Return (matched_stock_ids, matched_factor_ids) for one news item. Pure."""
    text = f"{headline or ''} {body or ''}".lower()
    stocks = [sid for sid, toks in stock_tokens.items() if any(_match(text, t) for t in toks)]
    factors = [fid for fid, kws in kw.items() if any(_match(text, k.lower()) for k in kws)]
    return stocks, factors


def ingest_feeds(conn: sqlite3.Connection, move_day: str | None = None,
                 feeds: list[str] | None = None) -> int:
    """Ingest RSS feeds, tagging stocks and factors. Returns rows inserted.

    ``move_day`` (ISO date) enables the suspect-reactive check for that day; defaults
    to today's IST date.
    """
    if feedparser is None:  # pragma: no cover
        raise RuntimeError("feedparser not installed; cannot fetch RSS")
    if move_day is None:
        move_day = now_ist_iso()[:10]

    stock_tokens = _stock_name_map(conn)
    kw = factor_keywords(conn)
    inserted = 0

    for url in (feeds or NEWS_RSS_FEEDS):
        try:
            parsed = feedparser.parse(url)
        except Exception as exc:  # pragma: no cover - network variance
            print(f"[news] parse failed for {url}: {exc}")
            continue
        for entry in parsed.get("entries", []):
            headline = entry.get("title", "")
            body = entry.get("summary", "") or entry.get("description", "")
            published = entry.get("published", "") or entry.get("updated", "")
            stocks, factors = tag_item(headline, body, stock_tokens, kw)
            if not stocks and not factors:
                continue
            # Emit one evidence row per (stock or factor) tag so bundle filtering is clean.
            targets: list[tuple[int | None, str | None]] = []
            targets += [(sid, None) for sid in stocks]
            targets += [(None, fid) for fid in factors]
            for stock_id, factor_id in targets:
                item = EvidenceItem(
                    tier=3, source=_domain(url), headline=headline, body_text=body,
                    url=entry.get("link"), stock_id=stock_id, factor_id=factor_id,
                    published_at=published, first_seen_at=now_ist_iso(),
                )
                _, ins = upsert_evidence(conn, item, move_day=move_day)
                inserted += int(ins)
    return inserted


def _domain(url: str) -> str:
    m = re.search(r"https?://([^/]+)/", url + "/")
    return m.group(1) if m else url


def ingest_all(conn: sqlite3.Connection, move_day: str | None = None) -> int:
    return ingest_feeds(conn, move_day=move_day)


if __name__ == "__main__":  # pragma: no cover
    from app.db import fresh_db
    c = fresh_db()
    print(f"[news] inserted {ingest_all(c)} news evidence rows")
