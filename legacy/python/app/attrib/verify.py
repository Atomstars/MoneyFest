"""Self-verification (DESIGN.md 6): deterministic checks + a narrow LLM verifier.

The deterministic checks run first and are pure (no LLM) -- each returns a strip reason
or None. The LLM verifier (Call 2, cheaper model) then entails each surviving claim
against only its cited evidence. Every strip is logged; the log is the hallucination
metric.
"""

from __future__ import annotations

from app.config import VERIFIER_MODEL
from app.attrib.rubric import (
    IST, MARKET_CLOSE, text_move_sign, edge_dir_int, direction_sign, _parse_dt, _sign,
)
from app.render import _FORBIDDEN
from app.llm import structured_call

from datetime import datetime


def _today_close(bundle: dict) -> datetime:
    d = datetime.fromisoformat(bundle["date"]).date()
    return datetime.combine(d, MARKET_CLOSE, tzinfo=IST)


# --- Deterministic checks (each -> strip reason or None) -------------------

def check_evidence_ids_exist(driver, bundle) -> str | None:
    ids = {e["id"] for e in bundle.get("evidence", [])}
    if not driver.get("evidence_ids"):
        return "driver cites no evidence"
    for i in driver["evidence_ids"]:
        if i not in ids:
            return f"evidence id {i} not in bundle"
    return None


def check_factor_in_profile(driver, bundle) -> str | None:
    fid = driver.get("factor_id")
    if fid is None:
        return None
    profile_ids = {e["factor_id"] for e in bundle.get("exposure_profile", [])}
    if fid not in profile_ids:
        return f"factor {fid} not in exposure profile"
    return None


def check_direction(driver, bundle) -> str | None:
    fid = driver.get("factor_id")
    if fid is None:
        return None  # tier-1 stock items resolve direction from the event, not a factor
    edge = next((e for e in bundle.get("exposure_profile", []) if e["factor_id"] == fid), None)
    if edge is None or edge["direction"] in ("COND",):
        return None  # COND edges are capped later, not sign-checked
    ev_by_id = {e["id"]: e for e in bundle.get("evidence", [])}
    move_sign = 0
    for i in driver.get("evidence_ids", []):
        e = ev_by_id.get(i, {})
        if e.get("factor_id") == fid:
            move_sign = text_move_sign((e.get("headline") or "") + " " + (e.get("body_text") or ""))
            if move_sign:
                break
    if move_sign == 0:
        return None  # can't recompute; rubric will cap this on tier
    resolved = move_sign * (edge_dir_int(edge["direction"]) or 0)
    claimed = direction_sign(driver.get("direction", "ambiguous"))
    if claimed != 0 and resolved != 0 and claimed != resolved:
        return "claimed direction contradicts sign(factor move) x edge.direction"
    return None


def check_quotes(driver, bundle) -> str | None:
    ev_by_id = {e["id"]: e for e in bundle.get("evidence", [])}
    bodies = []
    for i in driver.get("evidence_ids", []):
        e = ev_by_id.get(i, {})
        bodies.append((e.get("body_text") or "") + "\n" + (e.get("headline") or ""))
    hay = "\n".join(bodies)
    for q in driver.get("quotes", []):
        if q and q not in hay:
            return f"quote not a verbatim substring of cited evidence: {q[:40]!r}"
    return None


def check_temporal(driver, bundle) -> str | None:
    close = _today_close(bundle)
    ev_by_id = {e["id"]: e for e in bundle.get("evidence", [])}
    seens = []
    for i in driver.get("evidence_ids", []):
        e = ev_by_id.get(i, {})
        dt = _parse_dt(e.get("first_seen_at"))
        if dt is not None:
            seens.append(dt)
    if seens and all(dt > close for dt in seens):
        return "all cited evidence first seen after today's close; cannot explain the move"
    return None


def check_advice(driver) -> str | None:
    text = " ".join([driver.get("chain_text", ""), driver.get("direction_reason", "")]).lower()
    for w in _FORBIDDEN:
        if w in text:
            return f"advice-like language ({w!r}) in driver text"
    return None


DETERMINISTIC_CHECKS = [
    ("evidence_ids", check_evidence_ids_exist),
    ("factor_in_profile", check_factor_in_profile),
    ("direction", check_direction),
    ("quotes", check_quotes),
    ("temporal", check_temporal),
]


def deterministic_verify(agent_out: dict, bundle: dict) -> tuple[list[dict], list[dict], str]:
    """Run the code checks. Returns (surviving_drivers, strip_logs, residual_note)."""
    survivors, logs = [], []
    for d in agent_out.get("drivers", []):
        stripped = False
        for stage, fn in DETERMINISTIC_CHECKS:
            reason = fn(d, bundle)
            if reason:
                logs.append({"stage": f"det:{stage}", "rank": d.get("rank"), "reason": reason})
                stripped = True
                break
        if stripped:
            continue
        advice = check_advice(d)
        if advice:
            logs.append({"stage": "det:advice", "rank": d.get("rank"), "reason": advice})
            continue
        survivors.append(d)

    # Advice in residual_note -> blank it (not a strip).
    residual = agent_out.get("residual_note", "") or ""
    if any(w in residual.lower() for w in _FORBIDDEN):
        logs.append({"stage": "det:advice", "rank": None, "reason": "advice in residual_note; blanked"})
        residual = ""
    return survivors, logs, residual


# --- LLM Call 2 -- narrow entailment verifier ------------------------------

def _verifier_schema() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "verdict": {"type": "string", "enum": ["pass", "fail"]},
            "reason": {"type": "string"},
        },
        "required": ["verdict", "reason"],
    }


VERIFIER_SYSTEM = """\
You are a strict verifier in a system that separates FACTS from the CAUSAL CHAIN.

Understand the architecture before judging:
* The cited EVIDENCE supplies only the factual premise -- that a factor moved, or that \
an event was filed. That is all evidence is ever expected to establish.
* The EXPOSURE EDGE is a separate, human-curated statement of how that factor \
transmits to this company. Its chain_template_text is the approved wording. The \
evidence is NOT expected to contain, restate, or prove the causal chain.

Answer two questions and nothing else:
(a) Do the cited evidence items support the driver's factual premise -- i.e. that this \
factor moved (in the stated direction, if stated) or this event occurred?
(b) Is chain_text a faithful instantiation of the exposure edge's chain_template_text, \
with placeholders filled in and NO new causal links, factors, or magnitudes invented \
beyond that template?

Do NOT fail (a) merely because the evidence does not spell out the downstream P&L \
effect -- that comes from the edge, by design, and its absence from the evidence is \
expected and correct.

Fail if: the evidence does not support the factual premise; the direction contradicts \
the evidence; chain_text invents causal steps absent from the template; or the driver \
cites evidence about a different factor or company.

Return verdict=pass only if BOTH (a) and (b) hold. Do not rewrite anything.
"""


def llm_verify_driver(driver: dict, cited_evidence: list[dict], *,
                      exposure_edge: dict | None = None,
                      model: str = VERIFIER_MODEL, client=None) -> dict:
    """Entail one driver against ONLY its cited evidence and its exposure edge.

    ``exposure_edge`` is required for criterion (b) to be checkable at all -- without
    the edge's ``chain_template_text`` the verifier has nothing to compare chain_text
    against, and collapses (b) into (a), demanding that the evidence prove the whole
    causal chain. That is architecturally wrong: the chain comes from the curated
    profile, not the evidence.
    """
    ev_text = "\n\n".join(
        f"[evidence {e['id']} | tier {e['tier']} | {e.get('source')}]\n"
        f"{e.get('headline','')}\n{e.get('body_text','')}"
        for e in cited_evidence
    )
    import json as _json
    if exposure_edge is not None:
        edge_text = (
            f"factor_id: {exposure_edge.get('factor_id')}\n"
            f"chain_template_text: {exposure_edge.get('chain_template_text')}\n"
            f"channel: {exposure_edge.get('channel')}  "
            f"direction: {exposure_edge.get('direction')}  "
            f"strength: {exposure_edge.get('strength')}"
        )
    else:
        edge_text = ("(none -- this driver cites no factor edge, e.g. a Tier-1 company "
                     "event. Judge (b) as satisfied and assess (a) only.)")
    user = (
        "Driver claim:\n" + _json.dumps(driver, ensure_ascii=False) +
        "\n\nExposure edge (the approved causal chain for this factor):\n" + edge_text +
        "\n\nCited evidence (the ONLY evidence you may use for the factual premise):\n"
        + ev_text
    )
    return structured_call(
        model=model, system=VERIFIER_SYSTEM, user=user, schema=_verifier_schema(),
        tool_name="emit_verdict", client=client, max_tokens=1024,
    )


def llm_verify(survivors: list[dict], bundle: dict, *, model: str = VERIFIER_MODEL,
               client=None) -> tuple[list[dict], list[dict]]:
    """Run the LLM verifier per surviving driver. Returns (kept, strip_logs)."""
    ev_by_id = {e["id"]: e for e in bundle.get("evidence", [])}
    edges_by_factor = {e["factor_id"]: e for e in bundle.get("exposure_profile", [])}
    kept, logs = [], []
    for d in survivors:
        cited = [ev_by_id[i] for i in d.get("evidence_ids", []) if i in ev_by_id]
        edge = edges_by_factor.get(d.get("factor_id"))
        verdict = llm_verify_driver(d, cited, exposure_edge=edge,
                                    model=model, client=client)
        if verdict.get("verdict") == "pass":
            kept.append(d)
        else:
            logs.append({"stage": "llm", "rank": d.get("rank"),
                         "reason": verdict.get("reason", "verifier failed")})
    return kept, logs
