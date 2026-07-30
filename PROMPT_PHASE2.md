# Phase 2 Coding-Agent Prompt — Reasoning Agent, Rubric Engine, Verifier
**Authoritative design: DESIGN.md §1.2, §5, §6. Phase 1 code exists and its tests pass — do not restructure it; extend it.**
**Phase 2 scope ONLY: attribution agent + deterministic confidence rubric + self-verification + rendering of ATTRIBUTED/NO_DRIVER. NO watchlist/trigger changes (Phase 3), NO UI (Phase 4).**

---

## 0. Pre-flight fixes to Phase 1 (do these first)

1. **Widen the Tier-2 bundle window** (`app/bundle.py`): Tier-2 evidence is currently admitted only when `substr(first_seen_at,1,10) = date`. Overnight macro (US Fed decisions, crude moves after IST close) lands on the prior calendar day and is silently dropped. Change Tier-2 admission to the same time window as Tier-1/3: first_seen in [prev trading day 15:30 IST, today 23:59 IST] AND factor_id in the ratified-effective profile. Update `tests/test_bundle.py` accordingly (add a case: Fed decision first seen T-1 22:30 IST must be admitted).
2. **Edge suppression** (`app/exposure/profiles.py` + schema): DESIGN §3.1 says company overrides can add, flip, or REMOVE a template edge; removal is currently impossible. Add `direction = "SUPPRESS"` as a valid override value: a ratified SUPPRESS row deletes that factor's edge from the effective profile (and therefore from the bundle filter). Enforce in `effective_profile()`, accept it in the draft schema enum and ratify CLI, add a test.
3. **Fix the Anthropic call in `app/exposure/draft.py`:** the current `output_config`/`thinking` parameters may not match the installed SDK. Verify against the installed `anthropic` package and use its supported structured-output mechanism (tool-use with `input_schema`, or the SDK's current JSON-schema output option). This same client pattern will be reused below, so get it right once in a shared helper `app/llm.py`.

## 1. What Phase 2 builds

Consume the `attribution` rows Phase 1 leaves at `outcome=PENDING_ATTRIBUTION` (frozen `bundle_json`) and produce verified, ranked, cited driver lists — or an honest NO_DRIVER.

```
PENDING_ATTRIBUTION row
  └─► agent.py  (LLM Call 1: attribution)         → candidate drivers JSON
        └─► verify.py deterministic checks        → strip/keep
              └─► verify.py LLM Call 2 (verifier) → strip/keep
                    └─► rubric.py (pure)          → HIGH/MEDIUM/LOW per survivor
                          └─► render.py extension → plain-language output
                                └─► DB: attribution.outcome = ATTRIBUTED | NO_DRIVER,
                                    driver rows, verifier_log_json
```

New modules: `app/llm.py`, `app/attrib/agent.py`, `app/attrib/rubric.py`, `app/attrib/verify.py`, `app/attrib/pipeline.py`. Wire `pipeline.run_pending(conn)` into `jobs/eod.py` after the deterministic pass, behind a config flag `ATTRIBUTION_ENABLED` (default False until acceptance passes).

## 2. LLM Call 1 — the attribution agent (`agent.py`)

- Model: config constant, default `claude-opus-4-8` for attribution. One call per pending bundle.
- Input: the Bundle JSON verbatim (it already contains gate numbers, exposure profile with chain templates, and filtered evidence). Handle null gate stats (WARMING_UP event-trigger bundles) — the agent then explains the event, not the move.
- Output: strict JSON schema (structured output via `app/llm.py`):

```json
{"drivers": [{
    "rank": 1,
    "evidence_ids": [int, ...],          // must cite ≥1
    "factor_id": "CRUDE_BRENT" | null,   // null only for Tier-1 stock-specific items
    "chain_text": str,                    // MUST be rendered from the profile edge's
                                          // chain_template_text for factor-based drivers
    "direction": "positive"|"negative"|"ambiguous",
    "direction_reason": str,
    "confidence_claim": "HIGH"|"MEDIUM"|"LOW",
    "quotes": [str, ...]                  // verbatim substrings of cited evidence bodies
  }],
 "residual_note": str,                    // what remains unexplained, if anything
 "counter_evidence_ids": [int, ...]       // direction-mismatching items, listed not asserted
}
```

- System prompt requirements (write it, keep it in `agent.py` as a versioned constant `AGENT_PROMPT_V1`):
  - Explanation only; NO buy/sell/hold, price targets, or forward-looking advice — the schema has no field for it and the prompt forbids it anyway.
  - Only evidence in the bundle exists. Only factors in the exposure_profile may be linked, using their chain templates.
  - Direction must be resolved via the profile edge (sign of factor move × edge direction), never from headline framing.
  - An empty `drivers` list is a valid, expected answer. Prefer it over stretching.
  - `suspect_reactive=true` items may corroborate but never lead (rank 1 must not rest solely on them).

## 3. Rubric engine (`rubric.py`) — pure functions, no LLM

Implement DESIGN §5 exactly as a deterministic decision table over a driver's verified fields:

- **HIGH:** all of — cited evidence includes tier=1 with `exchange_dissemination_at` in [prev close 15:30 IST, today 15:30 IST]; event class direction-unambiguous (classify from headline via a small keyword map: results, order win, regulatory approval/rejection, management change, ratings action — keep the map in config); resolved direction matches sign(idio); no tier-1/2 counter-evidence in bundle.
- **MEDIUM:** tier=2 core-strength ratified edge, chain from that edge, factor's own move ≥ its 1σ (the Tier-2 evidence row already implies this by construction — assert it), direction matches sign(idio). Tier-1 with loose timing (first seen T-1 evening) also lands here.
- **LOW:** tier-3 only; or timestamp outside same-day; or COND edge; or contested direction; or secondary-strength edge.
- **Caps:** MIXED gate outcome ⇒ ≤ MEDIUM. COND edge ⇒ ≤ MEDIUM and condition_note must be rendered. Direction mismatch ⇒ not a driver at all (demote to counter-evidence).
- Nothing clears LOW ⇒ NO_DRIVER.
- Unit-test every row and cap with synthetic drivers.

The agent's `confidence_claim` is stored in `driver.agent_confidence_claim` and otherwise ignored.

## 4. Verifier (`verify.py`)

**Deterministic checks (code, run first):**
1. Every `evidence_ids` entry exists in the bundle → else strip.
2. `factor_id` (when non-null) exists in the bundle's exposure_profile → else strip.
3. Direction recomputation: for factor drivers, `sign(factor move) × edge.direction` must equal claimed direction (COND edges skip this, capped later) → else strip.
4. Every `quotes[]` string is a verbatim substring of a cited evidence `body_text` or `headline` → else strip.
5. Temporal ordering: a driver whose only evidence was first seen after today's close cannot explain today's move → strip.
6. Advice scan: `render._FORBIDDEN` words in any agent text → strip that driver; if in `residual_note`, blank it.

**LLM Call 2 (cheaper model, default `claude-sonnet-5`):** for each surviving driver, given ONLY the driver JSON + full text of its cited evidence: (a) does the evidence entail the claim? (b) does chain_text faithfully instantiate the cited edge's template? Returns `{driver_rank: "pass"|"fail", reason}` per driver, strict schema, no rewriting. Fail ⇒ strip.

**Post:** re-rank survivors (stable order: rubric level desc, then tier asc, then agent rank). Zero survivors ⇒ outcome NO_DRIVER. Every strip appended to `attribution.verifier_log_json` as `{stage, rank, reason}` — this log is the hallucination-rate metric; add `GET /metrics/strips` to the API returning counts by stage/reason.

## 5. Rendering (extend `app/render.py`)

- **ATTRIBUTED:** for each driver (max 3 rendered): one plain-language paragraph — what happened (evidence, source + timestamp + link), the chain sentence, the direction *for this stock*, and the confidence word with a one-line reason ("High confidence: company filing, same day, direction matches"). Then `residual_note` if non-empty, then counter-evidence as "Worth noting on the other side: …".
- **NO_DRIVER:** DESIGN §5 NONE template verbatim (large idio move, σ multiple, the three "not visible to this tool" possibilities).
- Same `_FORBIDDEN` guard applies; add a test that a rendered ATTRIBUTED text containing any forbidden word raises.

## 6. Hard rules

- Exactly 2 LLM calls per pending bundle, both through `app/llm.py`, both with structured output, both stamped into `attribution.model_version` (e.g. `"agent=claude-opus-4-8;verifier=claude-sonnet-5;prompt=v1"`).
- The daily loop still runs with `ATTRIBUTION_ENABLED=false` and zero LLM imports (keep the local-import pattern).
- Deterministic layers (rubric, checks, rendering) remain pure and byte-reproducible.
- No new thresholds outside `config.py`; bump config version.

## 7. Acceptance criteria

1. `pytest` green, including: rubric table tests, all six deterministic verifier checks (each with a case that strips), bundle Tier-2 window fix test, SUPPRESS test, forbidden-language test.
2. **Golden set:** create `tests/golden/` with ~20 hand-constructed bundles with known correct answers (results day, crude spike vs paints co, Fed overnight, market day misrouted, pure-noise-with-tier3-chatter, etc.) and 10 bundles with NO valid driver. Run the full pipeline (real LLM calls, marked `@pytest.mark.llm`, skipped in CI without a key). Report: top-driver hit rate on the 20, NO_DRIVER honesty on the 10 (target: ≥8/10 come back NO_DRIVER — if the agent "finds something" more than twice, tighten the prompt, not the rubric).
3. Strip-rate report printed after the golden run (per stage).
4. End-to-end: `run_eod` with `ATTRIBUTION_ENABLED=true` on a seeded DB processes a PENDING_ATTRIBUTION row into ATTRIBUTED or NO_DRIVER with driver rows and verifier log persisted.
5. README updated: pipeline diagram, model config, golden-set instructions, cost note (~2 calls per eventful stock-day).

Stop after acceptance. Phase 3 (watchlist triggers/alerts) is a separate prompt.
