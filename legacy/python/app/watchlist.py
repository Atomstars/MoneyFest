"""Watchlist + stock helpers shared by the API and the EOD job."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_sector(conn: sqlite3.Connection, sector_name: str) -> int:
    cur = conn.execute(
        """INSERT INTO sector (name) VALUES (?)
           ON CONFLICT(name) DO UPDATE SET name=excluded.name
           RETURNING id""",
        (sector_name,),
    )
    sid = cur.fetchone()[0]
    conn.commit()
    return sid


def upsert_stock(
    conn: sqlite3.Connection,
    *,
    name: str,
    ticker_nse: str | None,
    ticker_bse: str | None,
    sector_name: str | None,
    listing_meta: dict | None = None,
) -> int:
    """Insert or update a stock; returns its id."""
    sector_id = ensure_sector(conn, sector_name) if sector_name else None
    cur = conn.execute(
        """INSERT INTO stock (ticker_nse, ticker_bse, name, sector_id, listing_meta)
           VALUES (?,?,?,?,?)
           ON CONFLICT(ticker_nse, ticker_bse) DO UPDATE SET
             name=excluded.name, sector_id=excluded.sector_id,
             listing_meta=excluded.listing_meta
           RETURNING id""",
        (ticker_nse, ticker_bse, name, sector_id,
         json.dumps(listing_meta) if listing_meta else None),
    )
    stock_id = cur.fetchone()[0]
    conn.commit()
    return stock_id


def add_to_watchlist(conn: sqlite3.Connection, stock_id: int,
                     user_id: str = "default", qty: float | None = None) -> int:
    cur = conn.execute(
        """INSERT INTO watchlist_item (user_id, stock_id, qty, added_at)
           VALUES (?,?,?,?)
           ON CONFLICT(user_id, stock_id) DO UPDATE SET qty=excluded.qty
           RETURNING id""",
        (user_id, stock_id, qty, _now()),
    )
    wid = cur.fetchone()[0]
    conn.commit()
    return wid


def remove_from_watchlist(conn: sqlite3.Connection, watchlist_id: int) -> None:
    conn.execute("DELETE FROM watchlist_item WHERE id=?", (watchlist_id,))
    conn.commit()


def watchlist_stocks(conn: sqlite3.Connection, user_id: str = "default") -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT s.* FROM stock s
           JOIN watchlist_item w ON w.stock_id = s.id
           WHERE w.user_id = ?""",
        (user_id,),
    ).fetchall()


def all_watchlisted_stocks(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Distinct stocks watchlisted by ANY user -- the set the EOD job must process."""
    return conn.execute(
        """SELECT DISTINCT s.* FROM stock s
           JOIN watchlist_item w ON w.stock_id = s.id"""
    ).fetchall()
