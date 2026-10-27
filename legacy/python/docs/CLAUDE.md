# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

**Moneyfest** — a stock-move *explanation* engine for NSE/BSE equities, with a portfolio
layer on top. It answers "why did this stock move today?" and, most days, honestly answers
"it didn't, meaningfully."

`DESIGN.md` is the authoritative spec. `STATUS_REPORT.md` is the current honest inventory of
what works, what is broken, and what was deliberately left out — **read it before assuming
anything about project state.**

### What it deliberately does NOT do

These are ratified design decisions, not gaps. Do not "helpfully" add them:

- **No ML, no factor model, no price prediction.** `DESIGN.md` §0: *"No factor model. No
  computed impact percentages. Ever."* §3.4 explicitly evaluates and rejects LLM-derived
  exposure profiles.
- **No advice.** No buy/sell/hold, price targets, or forward-looking recommendations
  anywhere. Enforced in code (`_FORBIDDEN` in `app/render.py` raises on advice-like words;
  the verifier treats advice as a strip-level violation), not by convention.
- **NOISE / MARKET / NO_DRIVER are first-class answers.** "Nothing to explain" is the
  product working. If `NO_DRIVER` frequency trends to zero, the rubric bar is too low.

## Commands

```bash
# Setup (Windows paths; .venv/bin on POSIX)
python -m venv .venv && .venv/Scripts/activate
pip install -r requirements.txt

python -m scripts.bootstrap        # create DB, seed factors/templates, watchlist 5 stocks
```

```bash
pytest -q                          # full offline suite (~140 tests). LLM tests excluded.
pytest tests/test_gate.py -q       # one file
pytest tests/test_prices.py::test_beta_survives_missing_index_dates -q   # one test
pytest -m llm -s tests/test_golden.py                                    # live LLM golden set
```

`pytest.ini` sets `addopts = -m "not llm"` — LLM tests **never** run in a plain `pytest`,
because they cost real quota. Run them deliberately.

```bash
python -m app.jobs.eod             # the daily loop (one-shot)
ATTRIBUTION_ENABLED=true python -m app.jobs.eod   # ...including the reasoning layer
python -m app.api                  # FastAPI on 127.0.0.1:8000
python -m app.ingest.nse_bse       # ingestors run standalone, idempotent via body_hash
python -m app.ingest.nse_bse --verify-scrip 500325   # confirm a BSE code before mapping it
```

```bash
cd frontend && npm run dev         # Vite on :5173, proxies API routes to :8000
npm run build                      # tsc -b && vite build
npx tsc --noEmit                   # typecheck only
```

Both servers must run for the UI to work. The Vite proxy list lives in
`frontend/vite.config.ts` — **new backend route prefixes must be added there** or the UI
gets a 502.

## Architecture

Two layers with a hard boundary between them.

```
DETERMINISTIC (no LLM, always runs)
  prices.py -> gate.py -> NOISE | MARKET | MIXED | INVESTIGATE | EVENT_NO_MOVE
                                 | WARMING_UP | DATA_ISSUE
  ingest/{nse_bse,macro,news}.py -> normalize.py -> evidence rows
  bundle.py  -> frozen, filtered evidence bundle   (Constraint 6, see below)
  exposure/  -> effective profile = sector templates (+) ratified company overrides
        |
        |  only if gate = INVESTIGATE / MIXED  (written as outcome=PENDING_ATTRIBUTION)
        v
REASONING (exactly 2 LLM calls, only when ATTRIBUTION_ENABLED)
  attrib/agent.py   -> candidate drivers JSON
  attrib/verify.py  -> deterministic checks, then LLM entailment verifier
  attrib/rubric.py  -> HIGH/MEDIUM/LOW (pure; the agent's own claim is overruled)
  render.py         -> plain language -> ATTRIBUTED | NO_DRIVER
```

### The invariants that matter

Breaking any of these silently breaks the product's core promise.

1. **Constraint 6 — the bundle filter is code, not a prompt.** `build_bundle` admits only
   Tier-1/3 evidence tagged to *this* stock in the time window, plus Tier-2 evidence whose
   `factor_id` is in this stock's **ratified-effective** profile. This is what makes
   "Red Sea → TCS" structurally impossible. Proven in `tests/test_bundle.py`.

2. **Draft exposure rows never reach production.** `effective_profile` filters
   `status='draft'`. `app/exposure/draft.py` (the offline LLM drafter) hard-codes
   `status='draft'` on insert — there is no code path that lets it write `ratified`. Only
   `app/exposure/ratify.py` promotes.

3. **Direction is resolved per stock from the exposure edge**, as
   `sign(factor move) × edge.direction` — never inherited from a headline's framing. Two
   stocks get opposite labels from the same macro item. A wrong direction label at `core`
   strength is the one error `DESIGN.md` §7.2 says the product cannot survive.

4. **The gate is pure.** `gate.classify` takes precomputed series and flags; all I/O,
   corporate-action lookups and staleness checks happen in `prices.py` and are passed in as
   *conclusions* (`data_issue`, `tier1_event`). Keep it that way — it is what makes the gate
   trivially testable and reproducible.

5. **`stock_returns` and `index_returns` passed to the gate must be aligned day-for-day.**
   `classify` regresses one on the other; a positional mismatch produces a meaningless beta
   (near zero, wildly unstable) rather than an error. `build_gate_inputs` pairs them on the
   *intersection* of trading dates because yfinance does not return identical calendars for
   a stock and `^NSEI`. Regression tests in `tests/test_prices.py`.

6. **Bump `GATE_CONFIG_VERSION` whenever a threshold in `GateConfig` changes.** Never mutate
   a published config in place — every `daily_metric` row stamps `gate_inputs_json` so that
   same inputs + same config version ⇒ byte-identical results.

### Data-quality traps (all have bitten this codebase)

- **NaN prices.** yfinance returns bars with `close = NaN` for a session that has opened but
  not settled. `NaN` passes every `price <= 0` guard (all NaN comparisons are False) and
  propagates: `log(nan/prev)` is `nan`, the gate classifies off all-NaN statistics, SQLite
  stores it as NULL. `download_prices` drops non-finite closes and `_return_on_date` guards
  with `isfinite` — keep both.
- **A missing price must never read as zero.** Unpriced positions are excluded from portfolio
  totals and reported via `unpriced_positions`, and the UI renders `—`, never `₹0`.
- **Tier-1 ingest failures must be loud.** "No Tier-1 evidence" is indistinguishable from
  "nothing was filed" — `ingest_all` reports per-source status and warns when no source is
  reachable. BSE serves an HTML landing page with a *200* if the `Referer` header is missing;
  NSE's unparameterised endpoint returns only the latest ~20 announcements exchange-wide.
  Both are queried per-symbol with a date window.
- **Never guess a BSE scrip code.** A wrong code attaches another company's filings to a
  stock. `data/bse_scrip_map.yaml` entries are verified via `--verify-scrip`.

## LLM provider

`app/llm.py` is the **only** place any LLM SDK is called. It uses forced tool-use for
structured output. `LLM_PROVIDER` selects `groq` (default, free tier) or `anthropic`;
switching is an env var, no code change.

Passing `client=` bypasses provider selection entirely and always uses the Anthropic-shaped
call path, because every test double (`tests/conftest.py::FakeLLMClient`) mimics that shape.

**Groq free-tier quotas are per-model** and both surface as HTTP 429: tokens-per-minute
(12k) is transient and worth retrying; **tokens-per-day (100k) is a hard stop** whose
`retry-after` is hours. `GROQ_RETRY_MAX_WAIT_SECONDS` caps the wait — anything longer fails
fast rather than parking the process in `time.sleep()` until tomorrow (which presents as a
hang: process alive, zero CPU, no output). A full 30-case golden run consumes a large
fraction of the daily budget, so it is realistically a once-a-day check.

## Persistence

Plain `sqlite3`, no ORM — the schema is small, fixed, and authoritative in
`app/db/schema.sql`, mapping 1:1 to `DESIGN.md` §2.

`schema.sql` uses `CREATE TABLE IF NOT EXISTS`, so it never alters an existing table. Columns
added after initial ship go in `_ADDED_COLUMNS` in `app/db/__init__.py`, which `init_db`
applies additively. Add there when adding a column, or existing databases silently miss it.

## Frontend

React + Vite + Tailwind v4 in `frontend/`, consuming the JSON API. See
`frontend/README.md` for the design-system rules.

The colour tokens in `src/index.css` are a **validated** data-viz palette (both light and
dark independently stepped, not auto-flipped) — three light-mode categorical slots fall below
3:1 contrast, so the allocation donut's legend with names and values is an accessibility
requirement, not decoration. Re-run the palette validator if you change a series colour.

Green/red is used for **money only**. Outcome chips stay deliberately neutral so the
explanation layer never reads as a buy/sell signal.

## Documentation drift

`README.md` predates the current state and is stale in places — it describes Anthropic models
as the default, an earlier test count, and pre-portfolio/pre-frontend structure. When they
disagree, trust `STATUS_REPORT.md`, then `DESIGN.md`, then the code.
