# Phase 1 Coding-Agent Prompt — Stock Impact Explainer
**Ratified design: see DESIGN.md (authoritative — if this prompt and DESIGN.md conflict, DESIGN.md wins).**
**Phase 1 scope ONLY: evidence ingestion, quantitative gate, exposure/transmission map. NO reasoning agent, NO LLM attribution calls, NO UI, NO Telegram. Those are Phases 2–4.**

---

## Mission

Build the deterministic layer of a stock-move explainer for NSE/BSE equities:

1. A **price/volume tool** and **quantitative gate** that classifies each (stock, date) as NOISE / MARKET / MIXED / INVESTIGATE.
2. **Evidence ingestors** for three tiers, normalised into one schema, plus a **bundle assembler** that produces the frozen evidence bundle a future reasoning agent will consume.
3. The **exposure store**: factor registry, sector templates, company overrides, with a ratification workflow and an offline LLM-drafting pipeline for overrides.

Everything in this phase is deterministic except the offline profile-drafting pipeline (which is explicitly out of the daily loop and produces drafts only).

## Stack (fixed)

Python 3.11+, FastAPI, SQLite (via SQLAlchemy or plain sqlite3 — your call, justify in README), yfinance for prices, httpx for scraping, APScheduler for the EOD job, Claude API only inside the offline profile-drafting tool. pytest for tests. No other infra.

## Repository layout

```
app/
  config.py            # all thresholds, versioned (see §Gate)
  db/schema.sql        # tables exactly per DESIGN.md §2
  tools/prices.py      # fetch, adjust, returns, corp-action sanity
  tools/gate.py        # the quant gate, pure functions
  ingest/nse_bse.py    # Tier-1: exchange announcements
  ingest/macro.py      # Tier-2: factor series
  ingest/news.py       # Tier-3: RSS/news
  ingest/normalize.py  # everything → Evidence rows
  bundle.py            # bundle assembler (profile-filtered)
  exposure/registry.py # factor registry loader
  exposure/profiles.py # effective-profile resolution (template ⊕ ratified overrides)
  exposure/draft.py    # OFFLINE LLM drafting pipeline (drafts only, never production)
  exposure/ratify.py   # CLI: review/approve/reject draft rows
  jobs/eod.py          # scheduler entrypoint
  api.py               # thin FastAPI: health, gate result, bundle inspect
data/
  factors.yaml         # canonical factor registry (seed, see below)
  sector_templates.yaml
tests/
```

## Data model

Implement the tables exactly as specified in DESIGN.md §2 (`stock, sector, watchlist_item, factor, sector_template, exposure, evidence, daily_metric, attribution, driver`). `attribution`/`driver` tables are created now but only written with outcomes NOISE/MARKET (and gate snapshots) in this phase — ATTRIBUTED requires Phase 2.

## The quantitative gate (implement exactly)

Daily log returns on adjusted close, 60-trading-day lookback, minimum 40 (else stock is WARMING_UP; only event trigger active).

- **Gate 0 — sanity:** if |move| > 15%, check corporate-action calendar (BSE corporate actions feed) for split/bonus/dividend record date; adjust or emit DATA_ISSUE. Stale price (no trade today) → skip with DATA_ISSUE. Winsorize at ±3σ for estimation windows only — never winsorize the day being explained. For any INVESTIGATE-level move, cross-check the price against a second source; if disagreement > 1%, emit DATA_ISSUE instead of INVESTIGATE.
- **Gate 1 — noise:** σ = stdev(60d returns). If |r| < 1.0σ and no Tier-1 filing today → NOISE.
- **Gate 2 — market:** β = OLS slope vs NIFTY50 (60d), clamped to [−1.0, +3.0]; σ_idio = stdev(residuals); idio = r − β·r_idx. If |idio| < 1.0·σ_idio and |r_idx| ≥ 0.5% → MARKET.
- **Gate 3 — dispatch:** |idio| ≥ 1.5·σ_idio → INVESTIGATE. 1.0–1.5·σ_idio → MIXED. Record volume z-score (60d); it never changes the gate result.
- **Event trigger:** a Tier-1 filing fires the pipeline regardless of move size; if |r| < 1σ the outcome is EVENT_NO_MOVE.

All thresholds live in `config.py` in one versioned dataclass; every `daily_metric` row stamps `gate_inputs_json` with the exact inputs and config version used. Gate functions must be pure (inputs → result, no I/O) and unit-tested with synthetic series covering: quiet stock/quiet index, market-wide crash day, large idio move, split day, warming-up stock, stale price.

## Evidence ingestion

One normalised `evidence` row per item: tier, source, url, headline, body_text, body_hash (dedupe key), stock_id nullable, factor_id nullable, published_at, first_seen_at (YOUR crawler clock — trusted over the publisher's), exchange_dissemination_at for Tier-1.

- **Tier-1:** NSE and BSE corporate announcement feeds. Map announcements to stocks by scrip code/symbol. Capture the exchange's dissemination timestamp.
- **Tier-2:** daily series for every `kind=series` factor in the registry: Brent, USDINR, NIFTY50, sector indices, RBI repo (event-based), India 10Y. Each daily observation whose move ≥ that factor's own 60d 1σ becomes an evidence row tagged with the factor_id.
- **Tier-3:** a small set of business-news RSS feeds. Tag stock mentions (name/symbol match) and factor mentions (registry keyword lists). Any Tier-3 item first seen after 09:30 IST on the day of a move is flagged `suspect_reactive=true` (schema: add this boolean to evidence).

Ingestors must be idempotent (body_hash dedupe) and individually runnable from CLI.

## Bundle assembler (the Constraint-6 enforcement point)

`build_bundle(stock_id, date) -> Bundle` admits ONLY:
- Tier-1/Tier-3 evidence tagged to this stock, first seen in [prev trading day 15:30 IST, today 23:59 IST], and
- Tier-2 evidence whose factor_id exists in this stock's **ratified-effective** exposure profile.

Nothing else. This filter is the structural guarantee that unlinked macro events can never reach the future reasoning agent. Write a test that proves it: a "RED_SEA_FREIGHT" evidence item must not appear in a TCS bundle when TCS has no such exposure edge.

The Bundle is a frozen, serialisable object: `{stock, date, move, idio, beta, index_move, vol_z, gate_result, exposure_profile, evidence[]}` — exactly the future agent input in DESIGN.md §1.2.

## Exposure store

- `data/factors.yaml`: seed ~30 factors. Include at minimum: CRUDE_BRENT, USDINR, NIFTY50, RBI_REPO, IN_10Y, US_FED, GOLD, STEEL_HRC, COAL, IT_DEMAND_US, MONSOON, GST_POLICY, UNION_BUDGET, EXPORT_POLICY, FREIGHT_RATES, CHINA_DEMAND, EV_POLICY, TELECOM_TARIFF, DEFENCE_ORDERS, PSU_DIVESTMENT. Each: id, name, kind (series|event), series_source, keywords, unit, description.
- `data/sector_templates.yaml`: seed templates for at least: IT_SERVICES, BANKS_PRIVATE, BANKS_PSU, NBFC, PAINTS, OMC, UPSTREAM_OIL, AUTOS, TYRES, PHARMA, FMCG, METALS_STEEL, CEMENT, REALTY, AVIATION, POWER, DEFENCE, TELECOM. Each edge: factor_id, channel (enum: input_cost, output_price, revenue_currency, cost_currency, funding_cost, demand_driver, regulatory, supply_chain, competitive), pnl_line, direction (+1/−1/COND with condition_note), strength (core|secondary), chain_template_text. Use the worked examples in DESIGN.md §3.1 as the pattern. These seeds are first drafts for human review — mark the YAML header accordingly.
- **Effective profile resolution:** sector template rows overlaid by `status=ratified` company override rows; company row wins on factor_id collision. `status=draft` rows are NEVER included — test this.
- **Drafting pipeline (`exposure/draft.py`, offline CLI):** given a stock and a filing text file (annual report extract), call Claude with a fixed JSON schema to propose override rows restricted to the closed factor vocabulary and channel enum. Output rows land as `status=draft` with `provenance=llm_draft` and `source_citation`. It must be impossible for this tool to write `status=ratified`.
- **Ratification CLI (`exposure/ratify.py`):** list drafts, show diff vs current effective profile, approve/reject/edit row-by-one, stamp `last_reviewed_at`.

## EOD job

APScheduler job (weekdays ~18:30 IST): refresh prices for all watchlist stocks → run ingestors → run gate per stock → write `daily_metric` → for NOISE/MARKET/EVENT_NO_MOVE write `attribution` rows with deterministic rendered text (templates in DESIGN.md §4 output phrasing) → for INVESTIGATE/MIXED, build and persist the bundle (Phase 2 will consume it; store as JSON in the attribution row with outcome=PENDING_ATTRIBUTION).

## API (thin, internal)

`GET /health` · `GET /stocks/{id}/gate?date=` · `GET /stocks/{id}/bundle?date=` · `GET /stocks/{id}/profile` (effective, with provenance per edge) · `POST /watchlist` / `DELETE /watchlist/{id}`. No auth in Phase 1 (localhost).

## Hard rules

- No factor model, no computed impact percentages, no ML anywhere.
- No LLM calls in the daily loop. The only LLM code is `exposure/draft.py`, offline.
- No buy/sell/hold language in any rendered template.
- Deterministic outputs: same inputs + same config version ⇒ byte-identical results.
- Every rendered explanation for MARKET must state the index move and the stock's typical sensitivity in plain language, no jargon ("beta" may appear parenthetically only).

## Acceptance criteria

1. `pytest` green; gate unit tests cover the six synthetic scenarios above; bundle-filter test proves Constraint 6.
2. Run against 5 real stocks (e.g. TCS, ASIANPAINT, ONGC, HDFCBANK, MARUTI) over the last 90 days: gate classifies every day; spot-check that a known market-wide down day yields MARKET for high-beta names.
3. Drafting pipeline produces schema-valid draft rows from a sample annual-report extract; drafts provably excluded from effective profiles until ratified.
4. EOD job runs end-to-end on the watchlist and persists metrics, evidence, and pending bundles.
5. README documents setup, config thresholds, how to run each ingestor, and known data-quality caveats (yfinance NSE limitations per DESIGN.md §7.3).

Do not start Phase 2. When Phase 1 acceptance passes, stop and report.
