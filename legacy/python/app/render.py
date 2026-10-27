"""Deterministic renderers for the non-attributed outcomes.

Phase 1 renders NOISE, MARKET and EVENT_NO_MOVE (and DATA_ISSUE). ATTRIBUTED /
NO_DRIVER text is produced by the Phase-2 agent and is out of scope here.

Hard rules enforced by construction:
  * No buy / sell / hold language anywhere.
  * MARKET states the index move and the stock's typical sensitivity in plain
    language; the word "beta" may appear only parenthetically.
  * Same inputs => byte-identical text (pure string formatting, fixed rounding).
"""

from __future__ import annotations

from app.tools.gate import GateResult

# Guard: none of these words may appear in rendered output.
_FORBIDDEN = ("buy", "sell", "hold", "accumulate", "book profit", "target price")


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{abs(x) * 100:.2f}%"


def _dir_word(x: float | None) -> str:
    if x is None:
        return "moved"
    return "rose" if x >= 0 else "fell"


def _sensitivity_phrase(beta: float | None) -> str:
    """Plain-language sensitivity; 'beta' only parenthetically."""
    if beta is None:
        return "tends to move with the market"
    if beta >= 1.15:
        rel = f"tends to move a bit more than the market (about {beta:.1f}x)"
    elif beta <= 0.85:
        rel = f"tends to move a bit less than the market (about {beta:.1f}x)"
    else:
        rel = f"tends to move roughly in line with the market (about {beta:.1f}x)"
    return rel


def render_noise(stock_name: str, g: GateResult) -> str:
    normal = (g.sigma60 or 0.0)
    return (
        f"{stock_name} {_dir_word(g.ret)} {_pct(g.ret)}, within its normal daily "
        f"range of about +/-{_pct(normal)}. Nothing to explain."
    )


def render_market(stock_name: str, g: GateResult) -> str:
    return (
        f"{stock_name} {_dir_word(g.ret)} {_pct(g.ret)}; the index {_dir_word(g.index_ret)} "
        f"{_pct(g.index_ret)} and this stock {_sensitivity_phrase(g.beta60)}. "
        f"Today looks like a market day, not a {stock_name}-specific day."
    )


def render_event_no_move(stock_name: str, g: GateResult) -> str:
    return (
        f"{stock_name} had a material filing today, but the price reaction was muted "
        f"({_dir_word(g.ret)} {_pct(g.ret)}, within its normal daily range). "
        f"Noting the event; no move to attribute."
    )


def render_data_issue(stock_name: str, g: GateResult) -> str:
    return (
        f"{stock_name}: data-quality check failed ({g.reason}). "
        f"Holding off on any explanation until the price data is confirmed."
    )


def render(stock_name: str, g: GateResult) -> str:
    """Dispatch to the right template and assert the no-advice rule."""
    fn = {
        "NOISE": render_noise,
        "MARKET": render_market,
        "EVENT_NO_MOVE": render_event_no_move,
        "DATA_ISSUE": render_data_issue,
    }.get(g.outcome)
    if fn is None:
        # INVESTIGATE / MIXED / WARMING_UP have no deterministic prose in Phase 1.
        text = f"{stock_name}: {g.outcome} (pending Phase-2 attribution)."
    else:
        text = fn(stock_name, g)
    _assert_no_advice(text)
    return text


def _assert_no_advice(text: str) -> None:
    low = text.lower()
    for w in _FORBIDDEN:
        if w in low:
            raise AssertionError(f"advice-like word {w!r} in rendered text: {text!r}")


# --- Phase 2: ATTRIBUTED / NO_DRIVER ---------------------------------------

_DIR_PHRASE = {
    "positive": "reads as positive for",
    "negative": "reads as negative for",
    "ambiguous": "has a mixed read for",
}


def _confidence_line(level: str, reason: str) -> str:
    return f"{level.capitalize()} confidence: {reason}."


def _driver_paragraph(stock_name: str, d: dict) -> str:
    """One plain-language paragraph for a scored+verified driver."""
    cited = d.get("cited", [])
    lead = cited[0] if cited else {}
    src = lead.get("source", "source")
    ts = lead.get("exchange_dissemination_at") or lead.get("first_seen_at") or ""
    url = lead.get("url")
    headline = (lead.get("headline") or "").strip()

    what = f"{headline} ({src}"
    if ts:
        what += f", {ts}"
    what += ")"
    if url:
        what += f" [{url}]"

    parts = [what + ".", d.get("chain_text", "").strip(),
             f"For {stock_name}, this {_DIR_PHRASE.get(d.get('direction','ambiguous'))} the stock."]
    if d.get("needs_condition") and d.get("condition_note"):
        parts.append(f"Condition: {d['condition_note']}")
    parts.append(_confidence_line(d["confidence"], d.get("confidence_reason", "")))
    return " ".join(p for p in parts if p)


def render_attributed(stock_name: str, bundle: dict, drivers: list[dict],
                      residual_note: str = "", counter_evidence: list[dict] | None = None,
                      max_drivers: int | None = None) -> str:
    """Render the ATTRIBUTED explanation (ranked drivers + residual + counter-context)."""
    from app.config import MAX_RENDERED_DRIVERS
    limit = max_drivers or MAX_RENDERED_DRIVERS
    move = _pct(bundle.get("move"))
    idio = _pct(bundle.get("idio"))
    header = (f"{stock_name} {_dir_word(bundle.get('move'))} {move} "
              f"(idiosyncratic component {idio}). Most likely drivers:")
    blocks = [header]
    for i, d in enumerate(drivers[:limit], start=1):
        blocks.append(f"{i}. " + _driver_paragraph(stock_name, d))
    if residual_note.strip():
        blocks.append(f"Still unexplained: {residual_note.strip()}")
    for c in (counter_evidence or []):
        h = (c.get("headline") or "").strip()
        if h:
            blocks.append(f"Worth noting on the other side: {h} ({c.get('source','')}).")
    text = "\n\n".join(blocks)
    _assert_no_advice(text)
    return text


def render_no_driver(stock_name: str, bundle: dict) -> str:
    """DESIGN 5 NONE template: honest 'no attributable driver found'."""
    idio = _pct(bundle.get("idio"))
    sigma_idio = bundle.get("sigma_idio")
    mult = ""
    if sigma_idio and bundle.get("idio") is not None and sigma_idio > 0:
        mult = f", {abs(bundle['idio']) / sigma_idio:.1f} sigma"
    text = (
        f"{stock_name} had a large idiosyncratic move ({idio}{mult}). "
        f"No attributable driver was found in filings, macro data, or news. "
        f"Possible causes not visible to this tool: block deals, institutional flows, "
        f"or unpublished information."
    )
    _assert_no_advice(text)
    return text
