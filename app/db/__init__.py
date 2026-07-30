"""SQLite access helpers.

We use plain ``sqlite3`` (no ORM). Justification lives in the README: the schema
is small, fixed, and authoritative in ``schema.sql``; determinism and auditability
matter more than developer ergonomics, and an ORM would add a translation layer
between the ratified schema and the code with no offsetting benefit at this scale.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.config import DB_PATH

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def connect(db_path: str | None = None) -> sqlite3.Connection:
    """Open a connection with sane defaults (row factory + FK enforcement)."""
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# Columns added to existing tables after the initial schema shipped. schema.sql uses
# CREATE TABLE IF NOT EXISTS, so it never alters a table that already exists -- an
# already-populated DB would silently miss these. Each entry is (table, column, decl).
_ADDED_COLUMNS = [
    ("daily_metric", "close", "REAL"),
    ("daily_metric", "volume", "REAL"),
]


def _migrate(conn: sqlite3.Connection) -> None:
    """Additively bring an existing DB up to the current schema. Idempotent."""
    for table, column, decl in _ADDED_COLUMNS:
        cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if cols and column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
    conn.commit()


def init_db(conn: sqlite3.Connection) -> None:
    """Create all tables (idempotent) from the authoritative schema.sql, then migrate."""
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()
    _migrate(conn)


def fresh_db(db_path: str | None = None) -> sqlite3.Connection:
    """Connect and ensure the schema exists. Convenience for CLIs and tests."""
    conn = connect(db_path)
    init_db(conn)
    return conn
