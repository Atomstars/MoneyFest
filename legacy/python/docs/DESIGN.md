# Stock Impact Explainer — Design Document & Implementation Spec
**Status: DRAFT — awaiting ratification. No code, no agent prompts yet.**
**Scope: NSE/BSE equities. Explanation engine first, UI last.**

---

## 0. Design stance (restating the contract)

- No factor model. No computed impact percentages. Ever.
- A thin quantitative gate decides *whether* attribution runs at all.
- "Noise", "the market moved", and "no clear driver" are three first-class, shippable answers. Together they should cover the majority of trading days. Attribution is the exception path, not the default path.
- Impact is reasoned and cited by one agent, verified by one pass, delivered as a ranked candidate list.
- Direction is always computed against the company's exposure profile, never inherited from a headline.
- No advice, enforced in the agent contract.

---

## 1. Architecture

### 1.1 Components

```
┌─────────────────────────── DETERMINISTIC LAYER (no LLM) ───────────────────────────┐
│                                                                                     │
│  Price/Volume Tool ──► Quant Gate ──► gate_result                                   │
│  (yfinance .NS/.BO)    (σ, β, idio)   {NOISE | MARKET | MIXED | INVESTIGATE}        │
│                                                                                     │
│  Evidence Ingestors (per source, normalised to one Evidence schema):                │
│    T1: NSE/BSE corporate announcements & filings scraper                            │
│    T2: Macro series (Brent, USDINR, NIFTY/sector indices, repo rate, 10Y G-sec)     │
│    T3: News/RSS (business press), analyst-note headlines                            │
│                                                                                     │
│  Bundle Assembler: for (stock, date) builds the evidence bundle, FILTERED —         │
│    tier-1/3 items tagged to this stock + tier-2 items whose factor_id appears       │
│    in this stock's exposure profile. Nothing else enters the bundle.                │
│                                                                                     │
│  Exposure Store: sector templates + company profiles (see §3)                       │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                        │  (only if gate_result = INVESTIGATE/MIXED)
                                        ▼
┌──────────────────────────── REASONING LAYER (exactly 2 LLM calls) ──────────────────┐
│  Call 1 — Attribution Agent: (idio move, bundle, exposure profile) →                │
│           ranked candidate drivers, structured JSON, every claim carries            │
│           evidence_ids and a chain rendered from the exposure profile.              │
│  Call 2 — Verifier: checks every claim against the bundle & profile (see §6).       │
│           Strips uncited/unsupported claims. May demote to "no clear driver".       │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
          Renderer (deterministic templates for NOISE / MARKET / NO_DRIVER;
          verified JSON → plain language for attributed cases) → Alert (Telegram/web push)
```

### 1.2 The exact agent boundary

Tools never reason; the agent never fetches. The agent receives one frozen input object and returns one JSON object. It cannot browse, cannot query, cannot see any evidence outside the assembled bundle. This is what makes "Red Sea → TCS" structurally impossible: a macro item only reaches the agent's context if the Bundle Assembler matched its `factor_id` to the stock's exposure profile — the filter is code, not a prompt instruction.

Agent input: `{stock, date, move%, idio%, beta, index_move%, vol_zscore, exposure_profile, evidence[]}`.
Agent output: `{drivers: [{rank, evidence_ids[], factor_id|null, chain_text, direction, direction_reason, confidence_claim, quotes[]}], residual_note}`.

Confidence is *claimed* by the agent but *decided* by the rubric engine (§5) — a deterministic function over the claim's fields. The agent's claim is advisory only.

### 1.3 Trigger model

Two triggers per watchlist stock, evaluated after market close (v1 is EOD, not intraday):
1. **Move trigger:** gate fires INVESTIGATE or MIXED.
2. **Event trigger:** a tier-1 filing arrives regardless of move. If move < 1σ, output shape is "Material event, muted price reaction" — direction and chain still produced, no move-attribution claimed.

### 1.4 Stack (one deviation)

Python + FastAPI + SQLite + Claude API as specified. Deviation: use `yfinance` for prices but do **not** rely on it for corporate announcements — scrape NSE/BSE announcement feeds directly (they are the Tier-1 backbone and yfinance doesn't carry them). Telegram for alerts in v1 (web push needs the UI that doesn't exist yet). APScheduler for the EOD job; no queue infra needed at this scale.

---

## 2. Data model (SQLite)

```
stock            (id, ticker_nse, ticker_bse, name, sector_id, listing_meta)
sector           (id, name, template_version)
watchlist_item   (id, user_id, stock_id, qty NULLABLE, added_at)

factor           (id, name, kind {series|event}, series_source NULLABLE,
                  keywords[], tier, unit, description)
                  -- canonical registry: CRUDE_BRENT, USDINR, RBI_REPO, NIFTY50,
                  -- US_10Y, STEEL_HRC, IT_DEMAND_US, MONSOON, GST_POLICY, ...

sector_template  (id, sector_id, factor_id, channel, pnl_line, direction {-1,+1,COND},
                  condition_note, strength {core|secondary}, chain_template_text)

exposure         (id, stock_id, factor_id, channel, pnl_line, direction, condition_note,
                  strength, rationale, provenance {template|curator|llm_draft},
                  source_citation, status {draft|ratified}, last_reviewed_at)
                  -- effective profile = sector_template rows ⊕ ratified company overrides

evidence         (id, tier {1,2,3}, source, url, headline, body_text, body_hash,
                  stock_id NULLABLE, factor_id NULLABLE,
                  published_at, first_seen_at, exchange_dissemination_at NULLABLE)
                  -- body_hash dedupes republished wire copy

daily_metric     (stock_id, date, ret, index_ret, sigma60, beta60, sigma_idio,
                  idio_ret, vol_zscore, gate_result, gate_inputs_json)

attribution      (id, stock_id, date, trigger {move|event}, gate_snapshot_json,
                  outcome {NOISE|MARKET|MIXED|ATTRIBUTED|NO_DRIVER|EVENT_NO_MOVE},
                  rendered_text, created_at, model_version, verifier_log_json)

driver           (id, attribution_id, rank, factor_id NULLABLE, evidence_ids[],
                  chain_text, direction, confidence {HIGH|MEDIUM|LOW},
                  agent_confidence_claim, verifier_status {passed|stripped|demoted})
```

Notes: `gate_inputs_json` freezes σ/β/returns used, so every output is reproducible. Stripped drivers are kept (not deleted) for audit. `qty` on watchlist enables later portfolio-level rollups without schema change.

---

## 3. Exposure & transmission-chain design (the hard part)

### 3.1 Objects

Three layers, from stable to specific:

**(a) Factor Registry** — a small, closed, hand-written vocabulary (~30–50 factors). Each factor is either a *series* (crude, USDINR, repo, indices — fetched daily) or an *event class* (budget/GST announcements, export bans, monsoon updates — matched by keyword tagger on ingested news). Closed vocabulary is the point: the agent can only ever reference a factor that exists here.

**(b) Sector templates** — hand-curated once per sector (~30 sectors covers most of NSE by market cap). Each row is a pre-authored transmission edge:

```
factor=CRUDE_BRENT, sector=PAINTS:
  channel=input_cost, pnl_line=gross_margin, direction=-1, strength=core,
  chain="Crude {dir} → monomer/solvent input costs {dir} → gross margin {inv} → {impact}"

factor=USDINR, sector=IT_SERVICES:
  channel=revenue_currency, pnl_line=revenue, direction=+1 (INR depreciation), strength=core,
  chain="INR depreciation → USD revenues convert to more INR → margin tailwind → positive"

factor=RBI_REPO, sector=BANKS_PRIVATE:
  channel=funding_cost, pnl_line=nim, direction=COND,
  condition_note="Hike: near-term NIM expansion if assets reprice faster than deposits;
                  sustained hikes: credit-growth drag", strength=core, chain=...
```

**(c) Company overrides** — per-stock rows that add, remove, or flip template edges (ONGC flips CRUDE_BRENT to +1 with channel=output_price; an IT firm that's 90% hedged demotes USDINR to secondary; an OMC gets the COND pricing-regime note).

Effective profile at bundle-assembly time = template rows for the stock's sector, overlaid by ratified company rows (company row wins on `(factor_id)` collision).

### 3.2 Chain semantics

A chain is `factor move → channel → P&L line → direction`, rendered as one plain-language sentence with the factor's actual move interpolated. Chains are **qualitative**: no coefficients, no magnitude. The schema reserves a nullable `magnitude_note` column on `exposure` for the future annual-report-mining project (Constraint 6's "slot it in later") — unused in v1, so adding magnitudes later is a data enrichment, not a schema or engine change.

`direction=COND` edges are legal but capped: any driver built on a conditional edge can never be rated HIGH (see §5), and the condition_note must appear in the rendered explanation.

### 3.3 Direction resolution (Constraint 7)

Direction is computed as: `sign(factor move) × exposure.direction`, resolved per stock at render time. The headline's own framing is discarded — a tier-2/3 item contributes only its factor identification, magnitude, and timestamp. Two stocks in one watchlist can and will receive opposite labels from the same evidence item.

### 3.4 The forced decision: hand-curated vs LLM-derived profiles

**Option A — hand-curated:** accurate, auditable, and the sector layer makes it tractable (~30 templates × ~8 edges). Fails at the company-override long tail (2,000+ listed companies, business mixes change every year) and at freshness.

**Option B — LLM-derived from filings:** scales and stays fresh, but errors are *silent and land exactly on the product's core promise* — a wrong direction sign produces a confidently wrong "this is negative for your stock". Drift is undetectable without ground truth, and you'd be QA-ing an unbounded generator.

**Recommendation: layered hybrid, curation-gated.**
- Sector templates: **hand-curated, always.** Small, stable, high-leverage — this is where 80% of transmission knowledge lives, and it's a bounded one-time effort.
- Company overrides: **LLM-drafted, human-ratified.** When a stock is first added to any watchlist, a one-off pipeline reads its latest annual report / recent filings and proposes override rows *in the fixed schema against the closed factor vocabulary* — the LLM fills a form, it doesn't invent factors or channels. Every draft carries a source citation and sits at `status=draft`. **Draft rows are never used in production output.** Until you ratify them, the stock runs on sector template alone (correct-but-generic beats specific-but-wrong).

Why this wins: demand-driven volume (you curate only what someone actually watches — a retail watchlist product touches dozens of names, not thousands), the ratification step converts the LLM from a truth source into a research assistant, and the closed vocabulary + fixed schema make each ratification a 2-minute review, not an open-ended audit. Drift handling: re-draft on each new annual report, diff against ratified rows, surface changes for re-ratification; plus a quarterly audit that flags any ratified edge whose sign has disagreed with realized same-day co-movement persistently (a *hint* for review, never an auto-flip — that would be a factor model sneaking back in).

This choice shapes the architecture: exposure storage needs provenance/status/citation columns (§2), bundle assembly filters on *ratified-effective* profiles only, and the profile-drafting pipeline is a separate offline tool, not part of the daily loop.

---

## 4. The quantitative gate — exact spec

All on daily log returns of adjusted close. Lookback 60 trading days (min 40 to compute; else stock is "warming up" and only the event trigger is active).

**Gate 0 — data sanity.** If |move| > 15%: check for corporate action (split/bonus/dividend record date) via corporate-action calendar; if found, adjust or suppress. If price is stale (last trade date < today) → skip, flag data issue. Winsorize returns at ±3σ *for the σ and β estimation windows only* (the day being explained is never winsorized).

**Gate 1 — noise.**
- `σ = stdev(returns, 60d)` (winsorized window)
- If `|r_today| < 1.0σ` **and** no tier-1 event today → **NOISE**. Output: "Moved X%, within its normal daily range of ±Y%. Nothing to explain." Stop.

**Gate 2 — market.**
- `β = OLS slope(r_stock ~ r_NIFTY50, 60d)`, clamped to [−1.0, +3.0]. `σ_idio = stdev(residuals, 60d)`.
- `idio = r_today − β × r_index_today`
- If `|idio| < 1.0 × σ_idio` **and** `|r_index| ≥ 0.5%` → **MARKET**. Output: "Fell X%; the index fell Z% and this stock typically moves ~β× the index. Today was a market day, not a [stock] day." Optional colour: sector index move if available. Stop.

**Gate 3 — dispatch.**
- `|idio| ≥ 1.5 × σ_idio` → **INVESTIGATE** (full attribution path).
- `1.0σ_idio ≤ |idio| < 1.5σ_idio` → **MIXED**: output the market component as the primary explanation and run attribution on the residual with confidence capped at MEDIUM.
- Volume z-score (60d) recorded and passed to the agent: `vol_z ≥ 2` is corroborating context for materiality; it never changes the gate result by itself.

All thresholds (1.0σ, 1.5σ, 0.5%, clamp bounds, 60d) live in one config table, versioned, and are stamped into `gate_inputs_json` per output.

---

## 5. Confidence rubric — deterministic decision table

Computed by code from the (verified) driver's fields. The agent's own claim is logged but overruled.

| Level | ALL conditions required |
|---|---|
| **HIGH** | Evidence tier = 1 · `exchange_dissemination_at` within [prev close, today close] · event class is direction-unambiguous (results beat/miss, order win ≥ disclosed size, regulatory approval/rejection, mgmt change, ratings action) · resolved direction matches sign(idio) · no contradicting tier-1/2 item in bundle |
| **MEDIUM** | Evidence tier = 2 · factor edge exists in *ratified-effective* profile with `strength=core` · chain rendered from that edge (not free-text) · factor's own move that day ≥ its 60d 1σ · resolved direction matches sign(idio). Also: tier-1 with loose timing (T-1 late evening) drops here. |
| **LOW** | Tier-3 only · or timestamp outside the same-day window · or `direction=COND` edge · or direction conflict between bundle items · or strength=secondary edge |
| **NONE** | No driver clears LOW → outcome = **NO_DRIVER**: "Large idiosyncratic move (X%, Yσ). No attributable driver found in filings, macro data, or news. Possible causes not visible to this tool: block deals, institutional flows, unpublished information." |

Hard caps: MIXED outcome ⇒ ≤ MEDIUM. Conditional edge ⇒ ≤ MEDIUM and condition_note rendered. Direction mismatch (evidence implies up, stock went down) ⇒ the item may be listed only as "countervailing context", never as a driver.

---

## 6. Self-verification design

A second LLM pass plus deterministic checks, run on the attribution JSON before rendering:

**Deterministic (code):**
1. Every `evidence_id` exists in the bundle. Unknown id ⇒ strip claim.
2. Every `factor_id` exists in the stock's ratified-effective profile. Else strip. (Belt-and-braces on top of the bundle filter.)
3. Resolved direction = `sign(factor move) × exposure.direction`. Agent contradiction ⇒ strip.
4. Rubric recomputation (§5) — replaces agent's confidence claim.

**LLM verifier (Call 2), narrow contract:** for each surviving claim, given only the claim and the cited evidence bodies: (a) does the evidence actually say what the claim says (entailment, quote-check — every `quotes[]` entry must be a substring of a cited body)? (b) does the chain_text match the profile edge it cites? Answers pass/fail per claim, no rewriting. Fail ⇒ strip.

**Post-conditions:** re-rank survivors; if none survive ⇒ NO_DRIVER; every strip logged to `verifier_log_json` with reason (this log is your hallucination-rate metric from day one). The renderer refuses any sentence containing a fact not traceable to a surviving claim — templates only interpolate verified fields.

The no-advice constraint lives in **both** calls: attribution agent's output schema has no field where advice could go, and the verifier flags any imperative/recommendation language as a strip-level violation.

---

## 7. Top 3 ways this fails in production

**1. Timestamps lie, so causality inverts.** Indian wires republish, NSE filings post after-hours while the move happened intraday, and news sites rewrite `published_at` on edit. You'll confidently cite as "cause" an article written *because of* the move (journalists explaining the move become your evidence for the move — a feedback loop). Mitigations: store `first_seen_at` from your own crawler as the trusted clock; prefer `exchange_dissemination_at` for tier-1; treat any tier-3 item first seen *after* 09:30 IST on the move day as suspect-reactive and cap it at LOW; verifier checks temporal ordering explicitly.

**2. A stale or wrong exposure edge flips a direction label — the one error the product cannot survive.** Company hedges its FX, changes fuel mix, or an OMC pricing regime shifts, and the tool keeps saying "positive for you" when it's negative, at MEDIUM confidence, repeatedly. Silent, systematic, trust-destroying. Mitigations: ratification gate (§3.4), annual re-draft + diff, quarterly sign-vs-realized-comovement audit, `last_reviewed_at` staleness downgrade (edges unreviewed > 18 months lose `core` status).

**3. Price-data quality breaks the gate itself.** yfinance NSE data has missed corporate actions, stale quotes on illiquid names, and occasional bad prints — a bonus issue looks like a −50% idiosyncratic crash and everything downstream is garbage generated with full confidence. Mitigations: Gate 0 corporate-action check against a second source (BSE corporate actions feed), cross-check any INVESTIGATE-level move against a second price source before running the agent, refuse to attribute when sources disagree > 1%.

*(Honourable mention, watch for it in the verifier logs: confirmation bias at scale — on any big-move day, tier-3 media always contains a direction-matching story, so LOW-confidence attributions can drift toward "always finds something". If NO_DRIVER frequency trends toward zero, the rubric bar is too low.)*

---

## 8. Build order mapping (unchanged from brief)

- **Phase 1:** Factor registry + sector templates (curation sprint) · price tool + gate (§4) · T1/T2/T3 ingestors + bundle assembler · profile-drafting pipeline + ratification CLI.
- **Phase 2:** Attribution agent + rubric engine + verifier (§5–6). Acceptance: run against 20 hand-picked historical (stock, date) cases with known causes + 10 known no-driver days; measure strip rate and NO_DRIVER honesty before any live use.
- **Phase 3:** Watchlist persistence, EOD scheduler, Telegram delivery.
- **Phase 4:** UI.

---

**Awaiting ratification on:** (a) the layered-hybrid exposure decision (§3.4), (b) gate thresholds (§4), (c) EOD-only for v1 (no intraday), (d) Telegram-first delivery. After ratification, next artifact is the coding-agent prompt for Phase 1.
