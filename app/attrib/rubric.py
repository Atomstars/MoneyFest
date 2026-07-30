"""Confidence rubric -- deterministic decision table (DESIGN.md 5).

Pure functions over a driver's verified fields plus the bundle. The agent's own
confidence_claim is ignored here; this module decides HIGH / MEDIUM / LOW, or demotes a
direction-mismatching item to counter-evidence (returns None).

No LLM, no I/O. Byte-reproducible.
"""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

from app.config import MARKET_TZ, EVENT_KEYWORDS

IST = ZoneInfo(MARKET_TZ)
MARKET_CLOSE = time(15, 30)

CONF_ORDER = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
_ORDER_CONF = {v: k for k, v in CONF_ORDER.items()}

_UP_WORDS = ("rose", "gain", "jump", "surge", "higher", "climb", "up ", "rally",
             "beat", "wins", "won", "approv", "upgrade")
_DOWN_WORDS = ("fell", "drop", "decline", "slump", "lower", "weaken", "slid", "down ",
               "miss", "reject", "downgrade", "cut", "loss")


# --- small pure helpers ----------------------------------------------------

def direction_sign(direction: str) -> int:
    return {"positive": 1, "negative": -1, "ambiguous": 0}.get(direction, 0)


def edge_dir_int(direction: str) -> int | None:
    """+1/-1 -> int; COND/SUPPRESS -> None (not sign-resolvable here)."""
    return {"+1": 1, "-1": -1}.get(str(direction))


def text_move_sign(text: str | None) -> int:
    """Infer a move/event direction sign from evidence text. 0 if indeterminate.

    TODO(phase-3.5): for kind=series factors the SIGNED daily return is known at
    ingest time. Tier-2 evidence rows should carry numeric move_sign/move_pct fields so
    direction checks don't depend on headline keywords. This touches the frozen bundle
    schema, so it needs its own migration pass (see tests/test_phase35_todo.py).
    """
    if not text:
        return 0
    t = f" {text.lower()} "
    up = any(w in t for w in _UP_WORDS)
    down = any(w in t for w in _DOWN_WORDS)
    if up and not down:
        return 1
    if down and not up:
        return -1
    return 0


def classify_event(text: str | None) -> str | None:
    """Return the recognised event class for a Tier-1 item, or None if not unambiguous."""
    if not text:
        return None
    t = text.lower()
    for klass, kws in EVENT_KEYWORDS.items():
        if any(k in t for k in kws):
            return klass
    return None


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return dt.astimezone(IST)


def _high_window(bundle: dict) -> tuple[datetime, datetime]:
    """[prev close 15:30 IST, today 15:30 IST] -- the same-day HIGH timing gate."""
    date = datetime.fromisoformat(bundle["date"]).date()
    prev = bundle.get("prev_trading_day")
    from datetime import timedelta
    prev_d = datetime.fromisoformat(prev).date() if prev else date - timedelta(days=1)
    return (datetime.combine(prev_d, MARKET_CLOSE, tzinfo=IST),
            datetime.combine(date, MARKET_CLOSE, tzinfo=IST))


def _sign(x) -> int:
    if x is None or x == 0:
        return 0
    return 1 if x > 0 else -1


# --- the rubric ------------------------------------------------------------

def score_driver(driver: dict, bundle: dict, counter_evidence_ids: list[int] | None = None):
    """Return (level, reason, needs_condition) or (None, reason, False) to demote.

    ``needs_condition`` signals a COND edge whose condition_note must be rendered.
    """
    counter_evidence_ids = counter_evidence_ids or []
    ev_by_id = {e["id"]: e for e in bundle.get("evidence", [])}
    cited = [ev_by_id[i] for i in driver.get("evidence_ids", []) if i in ev_by_id]
    if not cited:
        return None, "no cited evidence in bundle", False

    profile = {e["factor_id"]: e for e in bundle.get("exposure_profile", [])}
    idio_sign = _sign(bundle.get("idio"))
    factor_id = driver.get("factor_id")
    edge = profile.get(factor_id) if factor_id else None
    is_cond = bool(edge and edge["direction"] == "COND")

    # Resolved effect-on-stock sign.
    if factor_id and edge and not is_cond:
        move_sign = 0
        for e in cited:
            if e.get("factor_id") == factor_id:
                move_sign = text_move_sign((e.get("headline") or "") + " " + (e.get("body_text") or ""))
                if move_sign:
                    break
        resolved_sign = move_sign * (edge_dir_int(edge["direction"]) or 0)
    else:
        resolved_sign = direction_sign(driver.get("direction", "ambiguous"))

    # Direction-mismatch cap: contradicts the actual idio move => not a driver.
    if idio_sign != 0 and resolved_sign != 0 and resolved_sign != idio_sign:
        return None, "resolved direction contradicts idiosyncratic move", False

    direction_matches = (idio_sign == 0) or (resolved_sign == idio_sign)

    tiers = {e["tier"] for e in cited}
    open_dt, close_dt = _high_window(bundle)

    # --- HIGH ---------------------------------------------------------------
    tier1_unambiguous_intime = False
    for e in cited:
        if e["tier"] != 1:
            continue
        diss = _parse_dt(e.get("exchange_dissemination_at") or e.get("first_seen_at"))
        if diss is None or not (open_dt <= diss <= close_dt):
            continue
        if classify_event((e.get("headline") or "") + " " + (e.get("body_text") or "")):
            tier1_unambiguous_intime = True
            break
    counter_tier12 = any(
        ev_by_id.get(cid, {}).get("tier") in (1, 2) for cid in counter_evidence_ids
    )

    level = None
    reason = ""
    if tier1_unambiguous_intime and direction_matches and not counter_tier12:
        level, reason = "HIGH", "Tier-1 filing, same day, direction-unambiguous event, matches move"

    # --- MEDIUM -------------------------------------------------------------
    if level is None:
        medium_factor = (
            factor_id and edge and not is_cond
            and edge.get("strength") == "core"
            and 2 in tiers and direction_matches
        )
        # Tier-1 with loose timing: a cited filing whose dissemination falls OUTSIDE
        # the tight same-day HIGH window (e.g. a T-1 late-evening filing).
        def _loose(e):
            diss = _parse_dt(e.get("exchange_dissemination_at") or e.get("first_seen_at"))
            return diss is None or not (open_dt <= diss <= close_dt)
        tier1_loose = any(e["tier"] == 1 and _loose(e) for e in cited)
        if medium_factor:
            level, reason = "MEDIUM", "Tier-2 core edge, factor move >= 1 sigma, direction matches"
        elif tier1_loose:
            level, reason = "MEDIUM", "Tier-1 filing with loose (T-1 evening) timing"

    # --- LOW (floor) --------------------------------------------------------
    if level is None:
        if tiers == {3}:
            reason = "Tier-3 news only"
        elif is_cond:
            reason = "conditional (COND) exposure edge"
        elif edge and edge.get("strength") == "secondary":
            reason = "secondary-strength edge"
        else:
            reason = "insufficient corroboration for MEDIUM"
        level = "LOW"

    # --- caps ---------------------------------------------------------------
    if bundle.get("gate_result") == "MIXED":
        level = _cap(level, "MEDIUM")
        reason += "; capped at MEDIUM (MIXED gate)"
    needs_condition = False
    if is_cond:
        level = _cap(level, "MEDIUM")
        needs_condition = True
        reason += "; COND edge (condition_note rendered)"

    return level, reason, needs_condition


def _cap(level: str, ceiling: str) -> str:
    return level if CONF_ORDER[level] <= CONF_ORDER[ceiling] else ceiling


def rank_key(scored: dict) -> tuple:
    """Stable re-rank: rubric level desc, then tier asc, then agent rank asc."""
    return (-CONF_ORDER[scored["confidence"]], scored["_min_tier"], scored["agent_rank"])
