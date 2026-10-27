"""Evidence normalisation -- everything from every tier becomes an Evidence row.

Single choke point so all ingestors share dedupe (by ``body_hash``), the trusted
crawler clock (``first_seen_at``), and the ``suspect_reactive`` rule. Ingestors are
idempotent because we upsert on ``body_hash``.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, time
from zoneinfo import ZoneInfo

from app.config import MARKET_TZ, SUSPECT_REACTIVE_CUTOFF

IST = ZoneInfo(MARKET_TZ)


def body_hash(headline: str | None, body_text: str | None) -> str:
    """Stable dedupe key over normalised headline+body (dedupes republished wire copy)."""
    norm = ((headline or "").strip() + "\n" + (body_text or "").strip()).lower()
    # collapse internal whitespace so trivial reformatting still dedupes
    norm = " ".join(norm.split())
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def now_ist_iso() -> str:
    return datetime.now(IST).isoformat()


@dataclass
class EvidenceItem:
    """A normalised evidence row prior to persistence."""

    tier: int
    source: str
    headline: str | None = None
    body_text: str | None = None
    url: str | None = None
    stock_id: int | None = None
    factor_id: str | None = None
    published_at: str | None = None
    first_seen_at: str | None = None          # defaults to crawler clock (now, IST)
    exchange_dissemination_at: str | None = None
    suspect_reactive: bool = False

    def compute_hash(self) -> str:
        return body_hash(self.headline, self.body_text)


def _cutoff_dt(first_seen: datetime) -> datetime:
    hh, mm = (int(x) for x in SUSPECT_REACTIVE_CUTOFF.split(":"))
    return first_seen.replace(hour=hh, minute=mm, second=0, microsecond=0)


def mark_suspect_reactive(item: EvidenceItem, move_day: str | None = None) -> None:
    """Flag a Tier-3 item first seen after the IST cutoff on a move day.

    A tier-3 item whose first_seen_at is after 09:30 IST on ``move_day`` is likely
    reactive coverage (journalists explaining the move), so it must not be trusted
    as a *cause*. Tier-1/2 are exempt (exchange/market timestamps are trusted).
    """
    if item.tier != 3 or not item.first_seen_at:
        return
    seen = datetime.fromisoformat(item.first_seen_at)
    if seen.tzinfo is None:
        seen = seen.replace(tzinfo=IST)
    seen_ist = seen.astimezone(IST)
    if move_day is not None and seen_ist.date().isoformat() != move_day:
        return
    if seen_ist >= _cutoff_dt(seen_ist):
        item.suspect_reactive = True


def upsert_evidence(conn: sqlite3.Connection, item: EvidenceItem,
                    move_day: str | None = None) -> tuple[int, bool]:
    """Insert an evidence item, deduping by body_hash. Returns (evidence_id, inserted).

    Idempotent: a repeat item with the same body_hash is not re-inserted; its existing
    id is returned with inserted=False. ``first_seen_at`` is stamped once (first crawl).
    """
    if item.first_seen_at is None:
        item.first_seen_at = now_ist_iso()
    mark_suspect_reactive(item, move_day=move_day)
    h = item.compute_hash()

    existing = conn.execute(
        "SELECT id FROM evidence WHERE body_hash=?", (h,)
    ).fetchone()
    if existing:
        return existing[0], False

    cur = conn.execute(
        """INSERT INTO evidence
             (tier, source, url, headline, body_text, body_hash, stock_id, factor_id,
              published_at, first_seen_at, exchange_dissemination_at, suspect_reactive)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            item.tier, item.source, item.url, item.headline, item.body_text, h,
            item.stock_id, item.factor_id, item.published_at, item.first_seen_at,
            item.exchange_dissemination_at, 1 if item.suspect_reactive else 0,
        ),
    )
    conn.commit()
    return cur.lastrowid, True
