"""Attribution pipeline -- wires the two LLM calls and the deterministic layers.

PENDING_ATTRIBUTION row (frozen bundle_json)
  -> agent (LLM 1)  -> deterministic verify -> LLM verify (LLM 2)
  -> rubric (pure)  -> render -> persist (attribution.outcome, driver rows, verifier log)

Exactly two LLM calls per bundle. The rubric, deterministic checks, and rendering are
pure. Clients are injectable so tests can drive the flow without network.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from app.config import ATTRIBUTION_MODEL, VERIFIER_MODEL
from app.attrib.agent import run_agent, prompt_version
from app.attrib.verify import deterministic_verify, llm_verify
from app.attrib.rubric import score_driver, CONF_ORDER
from app.render import render_attributed, render_no_driver


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def model_version(agent_model: str, verifier_model: str) -> str:
    return f"agent={agent_model};verifier={verifier_model};prompt={prompt_version()}"


def _min_tier(driver: dict, bundle: dict) -> int:
    ev_by_id = {e["id"]: e for e in bundle.get("evidence", [])}
    tiers = [ev_by_id[i]["tier"] for i in driver.get("evidence_ids", []) if i in ev_by_id]
    return min(tiers) if tiers else 9


def process_bundle(bundle: dict, stock_name: str, *,
                   agent_model: str = ATTRIBUTION_MODEL,
                   verifier_model: str = VERIFIER_MODEL,
                   agent_client=None, verifier_client=None,
                   agent_out: dict | None = None) -> dict:
    """Run the full reasoning pipeline on one bundle dict.

    ``agent_out`` may be supplied to skip LLM Call 1 (used by deterministic tests).
    Returns a result dict: {outcome, rendered_text, drivers, verifier_log}.
    """
    bundle_json = json.dumps(bundle, sort_keys=True, ensure_ascii=False)

    # LLM Call 1 -- attribution.
    if agent_out is None:
        agent_out = run_agent(bundle_json, model=agent_model, client=agent_client)

    verifier_log: list[dict] = []

    # Deterministic checks.
    survivors, det_logs, residual = deterministic_verify(agent_out, bundle)
    verifier_log += det_logs

    # LLM Call 2 -- entailment verifier (skipped only when nothing survived).
    if survivors:
        survivors, llm_logs = llm_verify(survivors, bundle, model=verifier_model,
                                         client=verifier_client)
        verifier_log += llm_logs

    # Rubric -- confidence per survivor; direction-mismatch demotions become counters.
    ev_by_id = {e["id"]: e for e in bundle.get("evidence", [])}
    scored: list[dict] = []
    demoted_counter_ids: list[int] = list(agent_out.get("counter_evidence_ids", []))
    for d in survivors:
        level, reason, needs_cond = score_driver(
            d, bundle, counter_evidence_ids=agent_out.get("counter_evidence_ids"))
        if level is None:
            verifier_log.append({"stage": "rubric", "rank": d.get("rank"), "reason": reason})
            demoted_counter_ids += [i for i in d.get("evidence_ids", []) if i in ev_by_id]
            continue
        cited = [ev_by_id[i] for i in d.get("evidence_ids", []) if i in ev_by_id]
        edge = next((e for e in bundle.get("exposure_profile", [])
                     if e["factor_id"] == d.get("factor_id")), None)
        scored.append({
            "confidence": level,
            "confidence_reason": reason,
            "needs_condition": needs_cond,
            "condition_note": (edge or {}).get("condition_note"),
            "chain_text": d.get("chain_text", ""),
            "direction": d.get("direction", "ambiguous"),
            "direction_reason": d.get("direction_reason", ""),
            "factor_id": d.get("factor_id"),
            "agent_confidence_claim": d.get("confidence_claim"),
            "evidence_ids": d.get("evidence_ids", []),
            "cited": cited,
            "agent_rank": d.get("rank", 999),
            "_min_tier": _min_tier(d, bundle),
        })

    # Re-rank survivors: rubric level desc, then tier asc, then agent rank.
    scored.sort(key=lambda s: (-CONF_ORDER[s["confidence"]], s["_min_tier"], s["agent_rank"]))

    if not scored:
        return {
            "outcome": "NO_DRIVER",
            "rendered_text": render_no_driver(stock_name, bundle),
            "drivers": [],
            "verifier_log": verifier_log,
        }

    counter_evidence = [ev_by_id[i] for i in dict.fromkeys(demoted_counter_ids)
                        if i in ev_by_id]
    return {
        "outcome": "ATTRIBUTED",
        "rendered_text": render_attributed(stock_name, bundle, scored, residual,
                                           counter_evidence),
        "drivers": scored,
        "verifier_log": verifier_log,
    }


def _persist(conn: sqlite3.Connection, attribution_id: int, result: dict,
             agent_model: str, verifier_model: str) -> None:
    conn.execute(
        """UPDATE attribution
           SET outcome=?, rendered_text=?, model_version=?, verifier_log_json=?
           WHERE id=?""",
        (result["outcome"], result["rendered_text"],
         model_version(agent_model, verifier_model),
         json.dumps(result["verifier_log"], sort_keys=True), attribution_id),
    )
    # Replace any prior driver rows for this attribution.
    conn.execute("DELETE FROM driver WHERE attribution_id=?", (attribution_id,))
    for rank, d in enumerate(result["drivers"], start=1):
        conn.execute(
            """INSERT INTO driver
                 (attribution_id, rank, factor_id, evidence_ids, chain_text, direction,
                  confidence, confidence_reason, agent_confidence_claim, verifier_status)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (attribution_id, rank, d.get("factor_id"),
             json.dumps(d.get("evidence_ids", [])), d.get("chain_text"),
             d.get("direction"), d["confidence"], d.get("confidence_reason"),
             d.get("agent_confidence_claim"), "passed"),
        )
    conn.commit()


def run_pending(conn: sqlite3.Connection, *,
                agent_model: str = ATTRIBUTION_MODEL,
                verifier_model: str = VERIFIER_MODEL,
                agent_client=None, verifier_client=None) -> list[dict]:
    """Process every PENDING_ATTRIBUTION row. Returns per-row summaries."""
    rows = conn.execute(
        """SELECT a.id, a.stock_id, a.date, a.bundle_json, s.name AS stock_name
           FROM attribution a JOIN stock s ON s.id = a.stock_id
           WHERE a.outcome = 'PENDING_ATTRIBUTION' AND a.bundle_json IS NOT NULL"""
    ).fetchall()
    summaries = []
    for r in rows:
        bundle = json.loads(r["bundle_json"])
        result = process_bundle(
            bundle, r["stock_name"], agent_model=agent_model,
            verifier_model=verifier_model, agent_client=agent_client,
            verifier_client=verifier_client,
        )
        _persist(conn, r["id"], result, agent_model, verifier_model)
        summaries.append({"stock_id": r["stock_id"], "date": r["date"],
                          "outcome": result["outcome"],
                          "drivers": len(result["drivers"]),
                          "strips": len(result["verifier_log"])})
    return summaries
