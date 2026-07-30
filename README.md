# Moneyfest — Stock Impact Explainer

A stock-move **explanation** engine for NSE/BSE equities, with a portfolio layer on top.

Every broker tells you a stock fell 4%. Moneyfest tells you *why* — traced to a filing, a
macro move, or an honest "no clear driver". Every claim is cited. Nothing is invented.

- **`DESIGN.md`** — the authoritative spec. Start here for *why* anything is the way it is.
- **`STATUS_REPORT.md`** — the honest current inventory: what works, what's broken, what's
  unvalidated. **Trust this over any other doc when they disagree.**
- **`HANDOFF.md`** — pick-up-and-continue guide for a new session.
- **`CLAUDE.md`** — architecture + invariants for coding agents.

---

## What it does, and deliberately does not

The engine classifies every `(stock, date)` and only reasons about the interesting ones:

| Outcome | Meaning |
|---|---|
| `NOISE` | Moved within its normal daily range. Nothing to explain. |
| `MARKET` | The whole market moved; this stock followed it. |
| `MIXED` | Mostly market, with a smaller stock-specific residual. |
| `INVESTIGATE` | Moved more than the market explains → run attribution. |
| `EVENT_NO_MOVE` | Material filing, muted price reaction. |
| `WARMING_UP` | Under 40 trading days of history; only the event trigger is active. |
| `DATA_ISSUE` | Price data looked unreliable; nothing concluded. |

**Non-goals — ratified decisions, not gaps:**

- **No ML, no factor model, no price prediction.** `DESIGN.md` §0: *"No factor model. No
  computed impact percentages. Ever."*
- **No advice.** No buy/sell/hold, targets, or forward-looking recommendations anywhere —
  enforced by assertions and scans (`_FORBIDDEN` in `app/render.py`), not convention.
- **`NOISE` / `MARKET` / `NO_DRIVER` are first-class answers.** Most trading days land there.
  If `NO_DRIVER` frequency trends to zero, the rubric bar is too low.
- **Direction is per-stock**, resolved as `sign(factor move) × edge.direction` from the
  exposure profile — never inherited from a headline. Two stocks get opposite labels from the
  same macro item.

---

## Setup

```bash
python -m venv .venv
.venv/Scripts/activate            # Windows;  source .venv/bin/activate on POSIX
pip install -r requirements.txt
python -m scripts.bootstrap       # create DB, seed factors/templates, watchlist 5 stocks
```

`tzdata` is required on Windows (no system IANA zone database). The quantitative gate
(`app/tools/gate.py`) is pure standard library, so gate tests run even without the
networked deps.

DB path defaults to `stock_explainer.db`; override with `STOCK_EXPLAINER_DB`.

### Run it

Two processes. Backend:

```bash
python -m app.api
```

Frontend:

```bash
cd frontend && npm install && npm run dev
```

Open <http://localhost:5173>. Vite proxies API routes to `127.0.0.1:8000`, so the browser
sees one origin. **New backend route prefixes must be added to `proxied` in
`frontend/vite.config.ts`** or the UI gets a 502.

### The daily loop

```bash
python -m app.jobs.eod                             # deterministic pass only
ATTRIBUTION_ENABLED=true python -m app.jobs.eod    # ...plus the reasoning layer
```

Refreshes prices, runs ingestors, runs the gate per stock, writes `daily_metric` (with a
frozen `gate_inputs_json`) and an `attribution` row. `INVESTIGATE`/`MIXED` days persist a
frozen bundle as `outcome=PENDING_ATTRIBUTION` for the reasoning layer.
`app.jobs.eod.build_scheduler()` gives an APScheduler job (weekdays ~18:30 IST).

### Ingestors (standalone, idempotent via `body_hash`)

```bash
python -m app.ingest.nse_bse                  # Tier-1: NSE + BSE announcements
python -m app.ingest.macro                    # Tier-2: macro factor series
python -m app.ingest.news                     # Tier-3: business-news RSS
python -m app.ingest.nse_bse --verify-scrip 500325   # confirm a BSE code before mapping
```

### Exposure workflow

```bash
python -m app.exposure.draft --stock TCS --filing extract.txt   # LLM drafts (draft only)
python -m app.exposure.ratify --stock TCS                       # human ratifies
python -m app.exposure.ratify --stock TCS --list
```

---

## Testing

```bash
pytest -q                                       # 140 tests, offline, no quota cost
pytest tests/test_gate.py -q                    # one file
pytest tests/test_prices.py::test_beta_survives_missing_index_dates -q
pytest -m llm -s tests/test_golden.py           # live LLM golden set (costs quota)
```

`pytest.ini` sets `addopts = -m "not llm"` — LLM tests never run in a plain `pytest`.

**Golden set** (`tests/golden/dataset.py`): 20 bundles that should attribute, 10 that should
honestly return `NO_DRIVER`. The live run reports top-driver hit rate, `NO_DRIVER` honesty
(asserts ≥ 8/10) and per-stage strip rate. Run it after any prompt or model change.

---

## The quantitative gate

Daily **log** returns on adjusted close, 60-trading-day lookback (min 40). All thresholds
live in one versioned dataclass, `GateConfig` in `app/config.py`, stamped as
`config_version` into every metric row.

| Threshold | Default | Meaning |
|---|---|---|
| `lookback` / `min_lookback` | 60 / 40 | estimation window; below min → `WARMING_UP` |
| `sanity_move_threshold` | 0.15 | `\|move\| > 15%` triggers a corporate-action check |
| `winsor_sigma` | 3.0 | winsorize **estimation windows only** |
| `noise_sigma_mult` | 1.0 | `\|r\| < 1.0σ` and no Tier-1 event → `NOISE` |
| `beta_clamp_low/high` | −1.0 / +3.0 | OLS β vs NIFTY50 clamped to this band |
| `market_idio_sigma_mult` | 1.0 | `\|idio\| < 1.0·σ_idio` … |
| `market_index_min_move` | 0.005 | … **and** `\|r_index\| ≥ 0.5%` → `MARKET` |
| `investigate_idio_sigma_mult` | 1.5 | `\|idio\| ≥ 1.5·σ_idio` → `INVESTIGATE` |
| `vol_z_material` | 2.0 | volume z-score is context only — never changes the gate |

Gate functions are **pure**. Corporate-action lookups, staleness and second-source checks
live in `app/tools/prices.py` and are passed in as conclusions (`data_issue`, `tier1_event`).

**Bump `GATE_CONFIG_VERSION` whenever a threshold changes** — never mutate a published config
in place. Determinism guarantee: same inputs + same `config_version` ⇒ byte-identical results.

---

## Constraint 6 — the bundle filter

`build_bundle` admits **only**:

- Tier-1/Tier-3 evidence tagged to this stock, first seen in
  `[prev trading day 15:30 IST, today 23:59 IST]`, **and**
- Tier-2 evidence whose `factor_id` is in this stock's **ratified-effective** profile.

Nothing else. This filter is code, not a prompt instruction — it is the structural guarantee
that an unlinked macro event (e.g. "Red Sea" → TCS) can never reach a stock with no such
exposure edge. Proven in `tests/test_bundle.py`.

---

## Exposure store

- `data/factors.yaml` — the **closed** factor vocabulary (30 factors). The agent can only
  reference a factor listed here.
- `data/sector_templates.yaml` — hand-curated transmission edges (18 sectors, 48 edges).
- `data/sector_map.yaml` — ticker → sector. Unmapped tickers get an empty profile
  (event-trigger only), which is correct-but-generic behaviour.
- `data/bse_scrip_map.yaml` — ticker → BSE scrip code, **each verified**. A wrong code
  attaches another company's filings to a stock.
- **Effective profile** = sector-template edges ⊕ `status='ratified'` company overrides
  (company row wins on `factor_id`; `direction=SUPPRESS` removes an edge). `draft` rows are
  never included — enforced in `effective_profile`, proven in `tests/test_profiles.py`.
- `app/exposure/draft.py` writes `status='draft'` hard-coded; it is structurally impossible
  for it to write `ratified`. Only `app/exposure/ratify.py` promotes.

> ⚠️ Seed `factors.yaml` and `sector_templates.yaml` are **first drafts for human review**.
> Direction signs and strengths need a curation pass before output is relied on.

---

## The reasoning layer

Consumes `PENDING_ATTRIBUTION` rows (each with a frozen `bundle_json`). **Exactly two LLM
calls per bundle**, both through `app/llm.py` using forced tool-use.

```
PENDING_ATTRIBUTION (frozen bundle)
  -> attrib/agent.py    (LLM 1)  candidate drivers JSON
  -> attrib/verify.py   deterministic checks (pure)      strip / keep
  -> attrib/verify.py   (LLM 2) entailment verifier      strip / keep
  -> attrib/rubric.py   (pure, DESIGN §5)                HIGH / MEDIUM / LOW
  -> render.py                                           ATTRIBUTED | NO_DRIVER
```

The daily loop imports no LLM code unless `ATTRIBUTION_ENABLED=true`. Every stripped claim
is appended to `attribution.verifier_log_json` — the hallucination metric, surfaced at
`GET /metrics/strips`.

### LLM provider

`app/llm.py` is the only place any LLM SDK is called. `LLM_PROVIDER` selects `groq`
(default, free tier) or `anthropic` — an env var, no code change.

| Setting | Default (groq) | Meaning |
|---|---|---|
| `LLM_PROVIDER` | `groq` | `groq` or `anthropic` |
| `ATTRIBUTION_ENABLED` | `false` | master switch for the reasoning layer |
| `ATTRIBUTION_MODEL` | `llama-3.3-70b-versatile` | LLM Call 1 |
| `VERIFIER_MODEL` | `llama-3.3-70b-versatile` | LLM Call 2 |
| `MAX_RENDERED_DRIVERS` | `3` | drivers shown in ATTRIBUTED output |

**Groq free-tier quotas are per-model**, and both surface as HTTP 429: tokens-per-minute
(12k) is transient and retried automatically; **tokens-per-day (100k) is a hard stop** whose
`retry-after` is hours. `GROQ_RETRY_MAX_WAIT_SECONDS` caps the wait so a daily-quota 429
fails fast instead of sleeping until tomorrow. A full golden run consumes a large fraction
of the daily budget — realistically a once-a-day check.

**Cost:** ~2 LLM calls per *eventful* stock-day. `NOISE`/`MARKET` days never reach the
reasoning layer, so the large majority of stock-days cost nothing.

---

## Portfolio layer

`app/portfolio.py` — arithmetic only, over two stored facts: the position you entered
(`holding.qty`, `holding.avg_cost`) and the adjusted close the gate already recorded
(`daily_metric.close`). Nothing modelled or forecast.

Valuation is **as of the last completed trading day**, not a live quote — every response
carries `as_of`. A position with no price is reported as unpriced and excluded from totals;
it is never counted as zero.

| Endpoint | Purpose |
|---|---|
| `GET /portfolio` | positions + totals + weights |
| `GET /portfolio/allocation` | sector allocation |
| `GET /portfolio/history?days=` | value over time (today's holdings at past closes) |
| `PUT /portfolio/holding` · `DELETE /portfolio/holding/{ticker}` | manage positions |
| `GET /stocks` | all tracked stocks: latest close, day change, gate outcome |
| `GET /stocks/{id}/prices?days=` | stored close series for charting |

Other endpoints: `/health`, `/stocks/{id}/gate|bundle|profile|history|attribution`,
`/watchlist`, `/metrics/strips`, `/metrics/outcomes`, `/alerts`, `/runs`, `/run_eod`,
`/users/{id}/prefs`, `/exposure/{id}/ratify|reject`.

---

## Frontend

React + Vite + Tailwind v4 in `frontend/`. Routes: `/` title page, `/home` all stocks,
`/dashboard` portfolio, `/settings`. See `frontend/README.md` for design-system rules.

Colour tokens are a **validated** data-viz palette (light and dark independently stepped).
Three light-mode categorical slots fall below 3:1 contrast, so the allocation donut's legend
is an accessibility requirement, not decoration. Green/red is used for **money only** —
outcome chips stay neutral so explanations never read as buy/sell signals.

---

## Telegram delivery

No LLM calls in this path. Rendered text is delivered *verbatim*; the bot may not rewrite,
truncate (except 4096-char chunking), or embellish it. The disclaimer is appended at
delivery time.

```bash
export TELEGRAM_BOT_TOKEN=123456:ABC...     # from @BotFather; never committed
python -m app.alerts.telegram poll
```

Commands: `/start`, `/add TCS`, `/list`, `/explain TCS`, `/remove TCS`,
`/prefs min_alert_level=HIGH_ONLY`.

---

## Data-quality caveats

- **yfinance is prices only.** It does not carry NSE/BSE filings; those are scraped directly.
- **NaN closes.** yfinance returns bars with `close = NaN` for a session that has opened but
  not settled. NaN passes every `price <= 0` guard (all NaN comparisons are False), so
  `download_prices` drops non-finite closes and `_return_on_date` guards with `isfinite`.
- **Stock and index calendars differ.** `^NSEI` is routinely missing a few of a stock's
  trading dates, so gate inputs are paired on the *intersection* of dates. A positional
  mismatch produces a meaningless beta rather than an error — see `tests/test_prices.py`.
- **Second-source cross-check is best-effort.** yfinance `.BO` symbols don't resolve for many
  BSE scrip codes; the check degrades to "not checked" and never fabricates a `DATA_ISSUE`.
  A reliable second price source is the highest-value hardening item.
- **Tier-1 failures must be loud.** "No Tier-1 evidence" is indistinguishable from "nothing
  was filed". BSE serves an HTML landing page with a *200* without a `Referer` header; NSE's
  unparameterised endpoint returns only the latest ~20 announcements exchange-wide. Both are
  queried per-symbol with a date window.
- **Auth is a seatbelt.** Single shared `WEB_TOKEN` + localhost binding. Not multi-user auth,
  not hardened for public exposure. The UI's sign-in screen is a design placeholder that
  authenticates nothing.

---

*Explanation only — not investment advice.*
