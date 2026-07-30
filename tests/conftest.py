"""Shared pytest fixtures: a temp SQLite DB seeded with the factor registry and
sector templates, plus a couple of watchlist stocks."""

from __future__ import annotations

import pytest

from types import SimpleNamespace

from app.db import fresh_db
from app.exposure.registry import seed_all
from app.watchlist import upsert_stock, add_to_watchlist


class FakeLLMClient:
    """Test double for anthropic.Anthropic. Returns a canned tool_use input.

    ``payloads`` is a list consumed in order (one per .messages.create call); if a
    single dict is given it is reused for every call.
    """

    def __init__(self, payloads):
        self._payloads = payloads
        self._i = 0
        self.calls = []

    class _Messages:
        def __init__(self, outer):
            self._outer = outer

        def create(self, **kwargs):
            o = self._outer
            o.calls.append(kwargs)
            if isinstance(o._payloads, dict):
                payload = o._payloads
            else:
                payload = o._payloads[min(o._i, len(o._payloads) - 1)]
                o._i += 1
            block = SimpleNamespace(type="tool_use", input=payload)
            return SimpleNamespace(content=[block])

    @property
    def messages(self):
        return FakeLLMClient._Messages(self)


@pytest.fixture()
def conn(tmp_path):
    db_path = str(tmp_path / "test.db")
    c = fresh_db(db_path)
    seed_all(c)
    yield c
    c.close()


@pytest.fixture()
def tcs(conn):
    """TCS on the IT_SERVICES template, added to the watchlist. Returns stock_id."""
    sid = upsert_stock(conn, name="Tata Consultancy Services",
                       ticker_nse="TCS", ticker_bse="532540",
                       sector_name="IT_SERVICES")
    add_to_watchlist(conn, sid)
    return sid


@pytest.fixture()
def fake_client():
    return FakeLLMClient


@pytest.fixture()
def ongc(conn):
    """ONGC on the UPSTREAM_OIL template. Returns stock_id."""
    sid = upsert_stock(conn, name="Oil and Natural Gas Corporation",
                       ticker_nse="ONGC", ticker_bse="500312",
                       sector_name="UPSTREAM_OIL")
    add_to_watchlist(conn, sid)
    return sid
