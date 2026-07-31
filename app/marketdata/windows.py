"""Trailing return windows over the stored close series -- the Groww-style
"1D / 1W / 1M / 3M / 1Y" strip.

Pure arithmetic on a list of ``(date, close)`` pairs. No I/O, no network, so this is
directly unit-testable and cannot fail at request time.

Two decisions that matter more than they look:

**Windows are calendar-anchored, not row-counted.** "1M" means "versus the last close
at or before the same date one month ago", not "30 rows back". Row counting silently
lies whenever the series has gaps -- holidays, a suspended scrip, a partial backfill --
and this series has all three.

**A window with no basis returns ``None``, never 0.** A freshly backfilled stock has no
close from a year ago; reporting that as a 0% one-year return would be a fabricated
number, and the whole product is built on not doing that. The UI renders these as a
dash.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

# label -> days back. Calendar days, deliberately: users think in calendar time.
WINDOWS: dict[str, int] = {
    "1D": 1,
    "1W": 7,
    "1M": 30,
    "3M": 91,
    "6M": 182,
    "1Y": 365,
    "3Y": 1095,
    "5Y": 1826,
}


def _parse(d: str) -> date | None:
    try:
        return date.fromisoformat(d)
    except (ValueError, TypeError):
        return None


def _finite(x: object) -> float | None:
    """Guard every close. yfinance emits NaN for opened-but-unsettled sessions, and
    NaN passes every ``> 0`` check because all NaN comparisons are False (CLAUDE.md)."""
    try:
        f = float(x)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def return_windows(series: list[tuple[str, float]],
                   as_of: str | None = None) -> dict[str, dict | None]:
    """Percentage change over each window in :data:`WINDOWS`.

    ``series`` is ``(iso_date, close)`` pairs in any order; it is sorted here.
    Returns ``{label: {"pct", "from_date", "from_close", "to_date", "to_close"}}``,
    with ``None`` for any window lacking a basis close.
    """
    clean: list[tuple[date, float]] = []
    for raw_date, raw_close in series:
        d, c = _parse(raw_date), _finite(raw_close)
        if d is not None and c is not None and c > 0:
            clean.append((d, c))
    clean.sort()
    if not clean:
        return {label: None for label in WINDOWS}

    end = _parse(as_of) if as_of else None
    if end is not None:
        clean = [(d, c) for d, c in clean if d <= end]
        if not clean:
            return {label: None for label in WINDOWS}
    to_date, to_close = clean[-1]

    out: dict[str, dict | None] = {}
    for label, days in WINDOWS.items():
        cutoff = to_date - timedelta(days=days)
        # Last close at or before the cutoff. The exact anniversary is usually a
        # weekend or a holiday, so "at or before" is the only workable rule.
        basis = None
        for d, c in reversed(clean):
            if d <= cutoff:
                basis = (d, c)
                break
        if basis is None or basis[1] <= 0 or basis[0] == to_date:
            out[label] = None
            continue
        from_date, from_close = basis
        out[label] = {
            "pct": (to_close - from_close) / from_close,
            "from_date": from_date.isoformat(),
            "from_close": from_close,
            "to_date": to_date.isoformat(),
            "to_close": to_close,
        }
    return out


def series_stats(series: list[tuple[str, float]]) -> dict:
    """52-week high/low and the position of the latest close within that band.

    Computed from *our own stored closes* rather than taken from yfinance, so the
    number is consistent with the chart drawn right next to it. It is therefore only
    as complete as the backfill: a stock with three months of history reports the
    high/low of those three months, and ``covers_days`` says so.
    """
    clean = sorted(
        (d, c) for d, c in ((_parse(a), _finite(b)) for a, b in series)
        if d is not None and c is not None and c > 0
    )
    if not clean:
        return {"high_52w": None, "low_52w": None, "band_position": None,
                "covers_days": 0}

    to_date = clean[-1][0]
    window = [(d, c) for d, c in clean if d > to_date - timedelta(days=365)]
    if not window:
        window = clean
    closes = [c for _, c in window]
    high, low, last = max(closes), min(closes), window[-1][1]
    return {
        "high_52w": high,
        "low_52w": low,
        # 0 = at the low, 1 = at the high. None when the band is flat.
        "band_position": ((last - low) / (high - low)) if high > low else None,
        "covers_days": (window[-1][0] - window[0][0]).days,
    }
