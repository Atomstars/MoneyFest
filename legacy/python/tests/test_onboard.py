"""Onboarding sector resolution (no network)."""

from __future__ import annotations

from app.onboard import resolve_sector


def test_mapped_ticker_resolves_to_sector():
    assert resolve_sector("TCS") == "IT_SERVICES"
    assert resolve_sector("ongc") == "UPSTREAM_OIL"   # case-insensitive
    assert resolve_sector("HDFCBANK") == "BANKS_PRIVATE"


def test_unmapped_ticker_returns_none():
    assert resolve_sector("SOMEWEIRDTICKER") is None
