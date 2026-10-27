"""User registration and preference persistence."""

from __future__ import annotations

import pytest

from app.users import register_user, user_by_chat, get_prefs, set_prefs
from app.config import DEFAULT_PREFS


def test_register_is_idempotent(conn):
    uid1 = register_user(conn, "12345", "Akash")
    uid2 = register_user(conn, "12345", "Akash")
    assert uid1 == uid2
    assert user_by_chat(conn, "12345")["display_name"] == "Akash"


def test_default_prefs(conn):
    uid = register_user(conn, "1")
    assert get_prefs(conn, uid) == DEFAULT_PREFS


def test_set_prefs_validates_and_merges(conn):
    uid = register_user(conn, "1")
    prefs = set_prefs(conn, uid, {"min_alert_level": "high_only", "quiet_market_days": "true"})
    assert prefs["min_alert_level"] == "HIGH_ONLY"
    assert prefs["quiet_market_days"] is True
    assert prefs["daily_digest"] is False  # untouched default


def test_set_prefs_rejects_bad_level(conn):
    uid = register_user(conn, "1")
    with pytest.raises(ValueError):
        set_prefs(conn, uid, {"min_alert_level": "SOMETIMES"})
