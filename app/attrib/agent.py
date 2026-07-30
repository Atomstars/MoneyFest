"""LLM Call 1 -- the attribution agent.

Given one frozen Bundle, propose a ranked, cited candidate-driver list (or an empty
list). The agent may only reference evidence in the bundle and factors in the bundle's
exposure profile, and must resolve direction from the profile edge -- never from a
headline's framing. It emits structured JSON via the shared forced-tool helper.

The agent's ``confidence_claim`` is advisory only; the deterministic rubric (rubric.py)
decides the real confidence.
"""

from __future__ import annotations

from app.config import ATTRIBUTION_MODEL, AGENT_PROMPT_VERSION
from app.llm import structured_call

# Versioned system prompt. Bump the suffix (and AGENT_PROMPT_VERSION in config) on edits.
AGENT_PROMPT_V1 = """\
You are a deterministic-tooling assistant that EXPLAINS why an Indian (NSE/BSE) stock \
moved on a given day. You are given ONE frozen evidence bundle and nothing else.

Absolute rules:
- Explanation only. NEVER give buy/sell/hold advice, price targets, or forward-looking \
recommendations. There is no field for advice and it is forbidden.
- Only the evidence inside this bundle exists. Cite evidence by its integer id. Every \
driver must cite at least one evidence id.
- You may only link a driver to a factor that appears in this bundle's exposure_profile. \
Use that edge's chain_template_text as the basis for chain_text (interpolate the actual \
move; do not invent a new chain).
- Direction is resolved from the exposure edge, NOT from the headline's framing: the \
effect on THIS stock is sign(factor move) x edge.direction. Two stocks can get opposite \
labels from the same macro item.
- An empty drivers list is a valid, expected, and often correct answer. Prefer it over \
stretching a weak link. "No clear driver" is a first-class answer.
- Items with suspect_reactive=true (news likely written BECAUSE of the move) may \
corroborate a driver but must never be the sole basis of the rank-1 driver.
- If the bundle has null gate statistics (a material filing with a muted price move), \
explain the EVENT and its direction for this stock; do not claim it explains a move.
- List any direction-mismatching items (evidence implies up but the stock fell, or vice \
versa) in counter_evidence_ids -- do not turn them into drivers.
"""


def agent_schema() -> dict:
    """Strict output schema for the attribution agent (DESIGN 1.2 / PROMPT section 2)."""
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "drivers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "rank": {"type": "integer"},
                        "evidence_ids": {"type": "array", "items": {"type": "integer"}},
                        "factor_id": {"type": ["string", "null"]},
                        "chain_text": {"type": "string"},
                        "direction": {"type": "string",
                                      "enum": ["positive", "negative", "ambiguous"]},
                        "direction_reason": {"type": "string"},
                        "confidence_claim": {"type": "string",
                                             "enum": ["HIGH", "MEDIUM", "LOW"]},
                        "quotes": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["rank", "evidence_ids", "chain_text", "direction",
                                 "direction_reason", "confidence_claim", "quotes"],
                },
            },
            "residual_note": {"type": "string"},
            "counter_evidence_ids": {"type": "array", "items": {"type": "integer"}},
        },
        "required": ["drivers", "residual_note", "counter_evidence_ids"],
    }


def run_agent(bundle_json: str, *, model: str = ATTRIBUTION_MODEL, client=None) -> dict:
    """Run the attribution agent on the bundle JSON. Returns the parsed agent output."""
    user = (
        "Here is the frozen evidence bundle. Explain the move (or return an empty "
        "drivers list if nothing in the bundle plausibly explains it).\n\n"
        f"{bundle_json}"
    )
    out = structured_call(
        model=model, system=AGENT_PROMPT_V1, user=user, schema=agent_schema(),
        tool_name="emit_attribution", client=client,
    )
    out.setdefault("drivers", [])
    out.setdefault("residual_note", "")
    out.setdefault("counter_evidence_ids", [])
    return out


def prompt_version() -> str:
    return AGENT_PROMPT_VERSION
