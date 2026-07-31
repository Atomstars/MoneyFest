"""Security master: the ISIN join, search ranking, and promotion to a tracked stock.

All offline. The join is a pure function over fixture rows shaped exactly like the
real feeds, so the thing most likely to break silently -- a wrong or missing BSE scrip
code -- is testable without a network call.
"""

from __future__ import annotations

import pytest

from app.universe import (
    find_security_for_stock,
    get_security,
    merge_listings,
    promote,
    save_securities,
    search,
)

# Shaped exactly like the real feeds, including NSE's space-padded header keys.
NSE_ROWS = [
    {"SYMBOL": "TCS", "NAME OF COMPANY": "Tata Consultancy Services Limited",
     " SERIES": "EQ", " DATE OF LISTING": "25-AUG-2004", " PAID UP VALUE": "1",
     " MARKET LOT": "1", " ISIN NUMBER": "INE467B01029", " FACE VALUE": "1"},
    {"SYMBOL": "INFY", "NAME OF COMPANY": "Infosys Limited",
     " SERIES": "EQ", " DATE OF LISTING": "08-FEB-1995", " PAID UP VALUE": "5",
     " MARKET LOT": "1", " ISIN NUMBER": "INE009A01021", " FACE VALUE": "5"},
    {"SYMBOL": "NSEONLY", "NAME OF COMPANY": "NSE Only Limited",
     " SERIES": "EQ", " DATE OF LISTING": "01-JAN-2020", " PAID UP VALUE": "10",
     " MARKET LOT": "1", " ISIN NUMBER": "INE999Z01011", " FACE VALUE": "10"},
]

BSE_ROWS = [
    {"SCRIP_CD": "532540", "Scrip_Name": "Tata Consultancy Services Ltd",
     "Status": "Active", "GROUP": "A", "FACE_VALUE": "1.00",
     "ISIN_NUMBER": "INE467B01029", "INDUSTRY": "IT - Software",
     "scrip_id": "TCS", "Segment": "Equity",
     "Issuer_Name": "Tata Consultancy Services Limited", "Mktcap": "856000.00"},
    {"SCRIP_CD": "500209", "Scrip_Name": "Infosys Ltd", "Status": "Active",
     "GROUP": "A", "FACE_VALUE": "5.00", "ISIN_NUMBER": "INE009A01021",
     "INDUSTRY": "IT - Software", "scrip_id": "INFY", "Segment": "Equity",
     "Issuer_Name": "Infosys Limited", "Mktcap": "470000.00"},
    {"SCRIP_CD": "590104", "Scrip_Name": "BSE Only Fund", "Status": "Active",
     "GROUP": "B", "FACE_VALUE": "10.00", "ISIN_NUMBER": "INE888Y01019",
     "INDUSTRY": None, "scrip_id": "BSEONLY", "Segment": "Equity",
     "Issuer_Name": "BSE Only Limited", "Mktcap": "120.00"},
]


@pytest.fixture()
def universe(conn):
    save_securities(conn, merge_listings(NSE_ROWS, BSE_ROWS))
    return conn


def test_merge_joins_on_isin_not_name():
    """The whole point: a BSE scrip code is DERIVED from a matching ISIN.

    CLAUDE.md: a wrong scrip code silently attaches another company's filings to a
    stock. Matching on company name would be a guess -- 'Ltd' vs 'Limited' -- so the
    join must key on the one identifier both exchanges publish.
    """
    merged = {r["isin"]: r for r in merge_listings(NSE_ROWS, BSE_ROWS)}

    tcs = merged["INE467B01029"]
    assert tcs["symbol_nse"] == "TCS"
    assert tcs["scrip_bse"] == "532540"
    assert tcs["exchanges"] == "NSE,BSE"
    # NSE wins on name (its file is cleaner); BSE contributes what NSE lacks.
    assert tcs["name"] == "Tata Consultancy Services Limited"
    assert tcs["industry"] == "IT - Software"
    assert tcs["market_cap"] == 856000.0


def test_merge_keeps_single_listed_names_on_both_sides():
    merged = {r["isin"]: r for r in merge_listings(NSE_ROWS, BSE_ROWS)}

    nse_only = merged["INE999Z01011"]
    assert nse_only["exchanges"] == "NSE"
    assert nse_only["scrip_bse"] is None

    bse_only = merged["INE888Y01019"]
    assert bse_only["exchanges"] == "BSE"
    assert bse_only["symbol_nse"] is None
    assert bse_only["scrip_bse"] == "590104"


def test_merge_normalises_padded_cells_and_dates():
    tcs = {r["isin"]: r for r in merge_listings(NSE_ROWS, [])}["INE467B01029"]
    assert tcs["series"] == "EQ"            # NSE pads its header keys AND its cells
    assert tcs["listing_date"] == "2004-08-25"   # 25-AUG-2004 -> ISO
    assert tcs["face_value"] == 1.0


def test_merge_drops_rows_without_an_isin():
    """An unjoinable half-record is worse than an absent one."""
    rows = merge_listings(
        [{"SYMBOL": "NOISIN", "NAME OF COMPANY": "No ISIN Ltd", " ISIN NUMBER": ""}],
        [{"SCRIP_CD": "1", "Scrip_Name": "Also None", "ISIN_NUMBER": None}],
    )
    assert rows == []


def test_save_is_idempotent(conn):
    rows = merge_listings(NSE_ROWS, BSE_ROWS)
    first = save_securities(conn, rows)
    second = save_securities(conn, rows)
    assert first["total"] == second["total"] == 4
    assert second["added"] == 0


def test_exact_ticker_match_ranks_first(universe):
    """Typing TCS must not return three companies whose NAMES contain 'tcs' first."""
    results = search(universe, "TCS")
    assert results[0]["symbol_nse"] == "TCS"
    assert results[0]["rank"] == 0


def test_search_by_bse_scrip_code(universe):
    results = search(universe, "532540")
    assert results[0]["symbol_nse"] == "TCS"


def test_search_by_company_name(universe):
    results = search(universe, "infosys")
    assert results[0]["symbol_nse"] == "INFY"


def test_search_exchange_filter(universe):
    assert {r["symbol_nse"] for r in search(universe, "limited", exchange="NSE")} \
        >= {"TCS", "INFY", "NSEONLY"}
    bse = search(universe, "limited", exchange="BSE")
    assert "NSEONLY" not in {r["symbol_nse"] for r in bse}


def test_empty_query_returns_nothing(universe):
    assert search(universe, "") == []
    assert search(universe, "   ") == []


def test_promote_creates_a_tracked_stock(universe):
    stock_id = promote(universe, "INE467B01029")
    row = universe.execute("SELECT * FROM stock WHERE id=?", (stock_id,)).fetchone()
    assert row["ticker_nse"] == "TCS"
    assert row["ticker_bse"] == "532540"
    # Sector is deliberately NOT guessed from BSE's industry string: that would
    # attach signed, core-strength factor edges on a string match (DESIGN.md 7.2).
    assert row["sector_id"] is None
    assert get_security(universe, "INE467B01029")["stock_id"] == stock_id


def test_promote_is_idempotent(universe):
    assert promote(universe, "INE467B01029") == promote(universe, "INE467B01029")
    assert universe.execute("SELECT COUNT(*) FROM stock").fetchone()[0] == 1


def test_promote_claims_an_existing_hand_seeded_stock(universe, tcs):
    """stock's UNIQUE(ticker_nse, ticker_bse) will not catch a duplicate when either
    column is NULL, because SQLite treats NULLs in a unique index as distinct."""
    assert promote(universe, "INE467B01029") == tcs
    assert universe.execute("SELECT COUNT(*) FROM stock").fetchone()[0] == 1


def test_promote_unknown_isin_raises(universe):
    with pytest.raises(ValueError, match="unknown ISIN"):
        promote(universe, "INE000000000")


def test_find_security_for_stock_falls_back_to_ticker(universe, tcs):
    """A stock seeded before the master existed still resolves, by ticker."""
    found = find_security_for_stock(universe, tcs)
    assert found is not None
    assert found["isin"] == "INE467B01029"
