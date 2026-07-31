# Stock_Analysis — Current Status Report
**Assessed:** 2026-07-30 · Assessor: Claude Code · Method: full read of source, docs, DB, and test suite
**Updated:** 2026-07-31 — universe browser, stock detail page, NVIDIA provider (see §5)

---

## 5. 2026-07-31 — universe, fundamentals and a real stock page

Four features added. Test suite went **140 → 193 passing**. The engine and its
invariants were not touched; everything here sits beside the pipeline, not inside it.

### 5.1 Security master — the app is no longer limited to a hand-seeded watchlist

`security` table + `app/universe.py` + `scripts/sync_universe.py`. **5,056 active
listings** (NSE 2,389 · BSE 4,928 · 2,260 dual-listed), joined on **ISIN**.

The join is a safety improvement, not just a feature. `data/bse_scrip_map.yaml` is
hand-maintained precisely because a wrong scrip code silently attaches another
company's filings to a stock. A code derived from a matching ISIN cannot be wrong that
way. `sync_universe --check` verifies the yaml against the join — **all six existing
entries agree**, which is the first independent confirmation those codes were right.

`promote()` leaves `sector_id` NULL by design: BSE's industry string is not this
project's sector vocabulary, and mapping it would attach signed `core`-strength edges
on a string match (§7.2's unsurvivable error).

### 5.2 Stock detail page with fundamentals, shareholding and price windows

Route `/stock/:id`, four tabs. `app/marketdata/` supplies it, and is **display-only by
construction** — none of it reaches the gate or the bundle, because it carries no tier,
no dissemination timestamp, and nothing the verifier could check.

| Block | Source | State |
|---|---|---|
| Delayed quote + OHLC | BSE `getScripHeaderData`, then yfinance, then our stored close | works |
| 1D/1W/1M/3M/6M/1Y/3Y/5Y returns | our own stored closes, calendar-anchored | works |
| EPS/PE/PB/ROE/OPM/NPM | BSE `ComHeadernew` (Indian accounting) | works |
| Market cap, 52w, beta, dividend yield | yfinance | works |
| Revenue/profit, annual + quarterly | yfinance income statement | works |
| Business summary, employees, listing date | yfinance + security master | works |
| Promoter vs public, 20 quarters | NSE `corporate-share-holdings-master` | works |
| **FII / DII split** | XBRL inside each filing | **not built** — see below |

Each key statistic renders its own source inline, because BSE and yfinance disagree
(TCS ROE: 59.9% BSE vs 47.7% yfinance — different consolidation) and a number you
cannot attribute is a number you cannot check.

**Quotes are delayed and labelled as such on every screen.** Real-time NSE ticks need
a licensed feed or a broker API with a logged-in session. Implying otherwise would be
exactly the quiet inaccuracy this project exists to avoid.

**The FII/DII gap is real and worth naming.** The exchange feed publishes only the
promoter/public top level. The institutional aggregate shown alongside comes from
yfinance `major_holders`, with a different as-of date, disclosed in the payload itself.
Closing this properly means fetching and parsing the XBRL attachment per quarter.

### 5.3 Backfill-on-open

Opening any of the 5,000 names warms it: one price download, then the pure gate
replayed over ~274 trading days. Measured **~9 seconds**; the UI shows a warming state
that says *why* (the gate needs 40 days before it can separate a stock move from a
market move) rather than rendering an empty page.

Verified end-to-end on two names never previously tracked. INFY backfilled to a healthy
spread — 170 NOISE, 40 WARMING_UP, 32 INVESTIGATE, 22 MIXED, 10 MARKET.

`app/onboard.py::_backfill` now delegates here, so the watchlist path and the browse
path cannot drift.

### 5.4 NVIDIA NIM as a third LLM provider

`LLM_PROVIDER=nvidia`, default model `nvidia/llama-3.3-nemotron-super-49b-v1.5`. Called
over httpx rather than adding the `openai` SDK — one JSON POST, and it is what allows
`chat_template_kwargs` to disable Nemotron's reasoning preamble (default off: it burns
budget and competes with the forced tool call for the output slot).

**Why this matters beyond having another option:** §2.10's verifier fix is *still
unvalidated* because Groq's 100k tokens/day ceiling kept killing the golden run.
NVIDIA's budget is materially larger, which makes that validation practical again.

> ⚠️ **The live NVIDIA path is untested.** No API key was available in this session, so
> only the guards, request shape, response parsing and rate-limit behaviour are covered
> (12 unit tests). Run `LLM_PROVIDER=nvidia python -m app.llm --check` first — a
> reasoning model that chats instead of emitting a forced tool call is useless here and
> that check catches it in one call. Then re-run the golden set: the §2.10 fix still
> needs ≥60% top-driver hit rate with **NO_DRIVER honesty at 10/10**.

### 5.5 Home rebuilt, density fixed, NVIDIA live (2026-07-31, second pass)

First pass shipped the features but kept the old visual language; feedback was blunt
and correct — UI 3/10, UX 1/10, "a kid could make it".

**Home is now portfolio-first**, four stacked sections: portfolio hero (value, day
change, total returns, invested) → holdings list → index strip → today's movers.
Holdings are hairline-separated rows showing current value, cost basis and change,
with **no charts and no outcome chips** — both were noise competing with the numbers.

**Density.** Root font 16px → 15px, body 14px, card padding cut. The old build fit
about six rows on a laptop; broker apps sit at 13–14px because the value is seeing the
whole position at once.

**Motion** (`components/motion.tsx`): count-up on the portfolio total, sweeping
shimmer skeletons, staggered row entrance, flash-on-change, a live dot that blinks
three times and stops. Rule: an animation must communicate something. `useCountUp`
skips its tween below a 2% delta so quote refreshes don't leave the total in motion.

**New market data**: `/market/indices` (NIFTY 50, SENSEX, BANK NIFTY, NIFTY IT) and
`/market/movers` (top gainers/losers across the 60 largest by market cap).

**NVIDIA is live and verified.** Key supplied, `nvidia/nemotron-3-ultra-550b-a55b`
returning correct forced tool calls against the live endpoint. Two corrections to the
first pass: the model is Nemotron 3 Ultra 550B (not Llama Nemotron Super 49B), and the
thinking flag is `enable_thinking`, not `thinking` — the wrong key is silently ignored,
so it would have looked like it worked while doing nothing. Now the default provider.

> Still outstanding: the §2.10 verifier fix has **not** been re-validated. NVIDIA
> removes the quota obstacle, so run `pytest -m llm -s tests/test_golden.py` and hold
> the bar — ≥60% top-driver hit rate with NO_DRIVER honesty at 10/10.

### 5.6 Two more real bugs, both surfaced by the new features

**Portfolio day change was 0.00% for every position.** `positions()` computed the
previous-close baseline against the portfolio's *global* as-of date rather than the
date each position was actually priced at. Harmless while every stock shared one
calendar; the moment on-demand backfill made some stocks current and others days
behind, the "previous" close resolved to the very same row as the current one and
every day change collapsed to zero. Positions now carry `priced_on`, and the UI badges
a row whose price is older than the rest of the portfolio.

**Chart y-axis was unreadable on stock prices.** `compactMoney` rounded thousands to
`₹3k`, so a TCS chart spanning ₹2,700–₹2,950 labelled all four gridlines "₹3k".
Thousands now print in full.

### 5.7 A real bug found and fixed on the way

`LineChart` memoised its gradient id *after* its empty-data early return, so hook count
changed between renders. Invisible until a chart could go from empty to populated in
place — which is precisely what a stock warming up its history does. It crashed the
whole route via React Router's error boundary. Pre-existing; fixed.

---

## 0. Headline: the project is not what it was described as

Your description of this repo and what is actually in it disagree on almost every point.
This is not a criticism — it matters because it changes what "fixing" means.

| You described | What the repo actually contains |
|---|---|
| "Portfolio analysis" | **No portfolio layer exists.** There is a watchlist. `watchlist_item.qty` exists as a nullable column but is never read or written anywhere. No holdings, no P&L, no allocation, no returns. |
| "Predictions written in machine learning" | **There is no ML and never was.** `DESIGN.md` §0 opens with: *"No factor model. No computed impact percentages. Ever."* `requirements.txt` line 1 reads *"No ML, no factor-model libraries."* No numpy-based modelling, no sklearn, no training, no prediction of any kind. |
| "The code is completely scrapped / not working" | **128 tests pass**, 1 skipped (needs an API key), 1 known xfail. The engine has been run end-to-end against real NSE data and produced correct output. |
| "There are no preexisting files" | **70+ source files**, a 20,600-byte design doc, 4 phase specs, a 22,400-byte README, 8,000-byte ship notes, and a 450 KB SQLite DB with real market data. |
| "The UI interface is not created" | **This one is true-ish.** A UI exists (5 templates, 13 routes) but it is deliberately minimal — 150 lines of CSS, no charts, no color. Nothing like Groww/Upstox. |

### What this project actually is

A **Stock Impact Explainer** for NSE/BSE equities. Its entire job is to answer one question:
*"Why did this stock move today?"* — and, most of the time, to answer *"it didn't, meaningfully."*

Architecture (from `DESIGN.md`):

```
Deterministic layer (no LLM)
  yfinance prices → Quant Gate → NOISE | MARKET | MIXED | INVESTIGATE | EVENT_NO_MOVE | WARMING_UP | DATA_ISSUE
  Evidence ingest (T1 exchange filings / T2 macro series / T3 news RSS) → Bundle Assembler
  Exposure store (sector templates + human-ratified company overrides)
        │  only if gate = INVESTIGATE or MIXED
        ▼
Reasoning layer (exactly 2 LLM calls)
  Attribution agent → deterministic checks → LLM verifier → rubric → ATTRIBUTED | NO_DRIVER
        ▼
  Renderer → Telegram alert / web page
```

The design is explicitly **anti-prediction and anti-advice**, enforced in code, not just convention:
no buy/sell/hold, no price targets, no forward-looking statements anywhere in the agent schema,
rubric, renderer, bot, or UI.

---

## 1. What genuinely works (verified, not assumed)

| Component | Evidence it works |
|---|---|
| **Quant gate** (`app/tools/gate.py`, 228 lines, pure stdlib) | 140 `daily_metric` rows classified over 2025-12-26 → 2026-07-10. Distribution is healthy: 73 NOISE, 40 WARMING_UP, 15 INVESTIGATE, 9 MIXED, 3 MARKET. Config-versioned (`gate-v1.1.0`), every row stamps its inputs so results are reproducible. |
| **Tier-2 macro ingest** | 336 evidence rows (Brent, USDINR, indices, rates). |
| **Tier-3 news RSS ingest** | 25 evidence rows from Moneycontrol / Business Standard / Mint / ET. |
| **Factor registry + sector templates** | 30 factors, 18 sectors, 48 pre-authored transmission edges. Hand-curated as designed. |
| **EOD job** (`app/jobs/eod.py`) | 3 `run_log` entries. Correctly skipped a weekend, correctly resolved effective trading date, ran ingestors and gate for all 6 stocks. |
| **Web UI + API** | 13 UI routes, 18 API routes, 5 Jinja templates, token-gated, htmx vendored (no CDN/npm). |
| **Test suite** | `128 passed, 1 skipped, 1 xfailed` in 41s. Includes 29 golden test cases. |

**The engine is not broken. It runs.**

---

## 2. What is actually wrong — the real gap list

These are the things that are genuinely incomplete or non-functional.

### 2.1 CRITICAL — Tier-1 evidence: zero rows ingested — **FIXED 2026-07-30**

```
before:  tier 1 → 0     tier 2 → 336     tier 3 → 25
after:   tier 1 → 39 (NSE 18 + BSE 21), all 6 stocks covered
```

Tier-1 (NSE/BSE corporate announcements) is called **"the Tier-1 backbone"** in `DESIGN.md` §1.4.
It had never produced a single row, which made HIGH confidence structurally unreachable (the §5
rubric requires `tier = 1` for HIGH) and meant the event trigger could never fire.

Three real bugs, all in `app/ingest/nse_bse.py` / `app/config.py`:

1. **Wrong BSE endpoint.** `AnnGetData` returns the HTML landing page with a **200**; the working
   endpoint is `AnnSubCategoryGetData`.
2. **Missing `Referer`.** `api.bseindia.com` serves JSON only to requests that look like they came
   from the site. Without it: HTML, 200, parsed as "no announcements".
3. **Both feeds were queried unscoped.** NSE's unparameterised endpoint returns only the latest ~20
   announcements *exchange-wide*, so a watchlist stock almost never appears. Both are now queried
   **per symbol with an explicit date window**.

Compounding all three: `_fetch_json` swallowed every failure and returned 0, so a total Tier-1
outage was indistinguishable from "nothing was filed". Failures are now raised and reported.

> **Two corrections to my first draft of this report.** (a) I wrote that NSE returns 403 — wrong. I
> had probed the *homepage*, not the API; the announcements API returns 200 and works fine after a
> cookie warm-up. (b) I wrote that no stock had a `ticker_bse` — also wrong; five of six already
> did. Only RELIANCE was missing one. Neither was the actual cause.

Scrip codes now live in `data/bse_scrip_map.yaml`, each **verified** against BSE's own company name
(`python -m app.ingest.nse_bse --verify-scrip 500325`) — a wrong code would silently attach another
company's filings to a stock.

### 2.2 CRITICAL — `exposure` table: zero rows

No company override has ever been drafted or ratified. Every stock runs on generic sector template
only. The LLM drafting pipeline (`app/exposure/draft.py`) and the ratification UI
(`/ui/stock/{id}/profile`) have never had anything to process. `DESIGN.md` §3.4 treats
human-ratified company overrides as the mechanism that makes attribution specific rather than generic.

### 2.3 CRITICAL — `driver` table: zero rows. The reasoning layer has never run.
**Now runs live on a free provider (2026-07-30); quality bar not yet met — see §2.10.**

Originally: `ATTRIBUTION_ENABLED` defaulted to `false`, no API key was set, and the second half of
the product had produced nothing.

**Provider switched from Anthropic to Groq (free tier)** — there is no budget for paid API calls.
`app/llm.py` was already the single chokepoint for every LLM call, so this was contained to that
one file plus config:

- `LLM_PROVIDER` env var selects `"groq"` (default) or `"anthropic"`. Switching back is an env
  change, no code edit.
- Groq is OpenAI-compatible: forced structured output uses
  `tool_choice={"type":"function","function":{"name":...}}` and arguments arrive as a JSON
  *string* (Anthropic returns a parsed `tool_use.input`). Both paths are implemented.
- Model defaults per provider live in `_MODEL_DEFAULTS`; on Groq both the agent and the verifier
  use `llama-3.3-70b-versatile`.
- **Test-injection contract preserved**: passing `client=` still uses the Anthropic-shaped path,
  because every test double in `tests/conftest.py` mimics that shape. All 132 offline tests pass
  unchanged.

**Free-tier constraints that required real code changes** (12,000 tokens/minute, 30 req/min):
- `max_tokens` default cut from `16000` → `2048`. Groq counts *reserved* `max_completion_tokens`
  against the TPM budget, so an oversized ceiling throttles throughput directly — at 4096 reserved
  only ~2 calls/minute fit. The first live call failed with HTTP 413 purely because of this.
- Added 429 retry with backoff honouring the server's `retry-after` header.

Live end-to-end run confirmed working: the full EOD job executed both LLM calls through Groq and
persisted results. Notably the deterministic safety net did its job on the first real run — the
agent proposed a factor (`CAPACITY_EXPANSION`) that isn't in MARUTI's exposure profile, and
`check_factor_in_profile` stripped it before it could reach a user.

**Free-tier quota ceilings (important for anyone running this):**

| Limit | Free-tier value | Behaviour |
|---|---|---|
| Tokens / minute (TPM) | 12,000 | Transient. Worth waiting out; retried automatically. |
| Requests / minute | 30 | Transient. |
| **Tokens / day (TPD)** | **100,000** | **Hard stop until daily reset.** |

The TPD ceiling is the real constraint: a single 30-case golden run costs a large fraction of the
daily budget, so the golden set can realistically be run about **once per day** on the free tier.

*Bug introduced and fixed in the same session:* the first version of the 429 handler honoured the
server's `retry-after` verbatim. A TPM limit returns a few seconds, but a **daily** limit returns
hours — so `time.sleep()` parked the process until the next day. It presented as a hang (process
alive, CPU frozen, no API requests, no output) and cost a diagnostic detour. Now capped by
`GROQ_RETRY_MAX_WAIT_SECONDS`: anything above 60s fails fast with an actionable message instead of
sleeping. Also added a bounded HTTP timeout and disabled the SDK's own retry layer so the daily
loop can never block indefinitely.

*Process-hygiene note:* `timeout N <cmd>` kills the shell wrapper, not the Python child. Two
earlier golden runs survived their timeouts and kept competing for the same token budget, which
made a later run look stalled. Kill orphans before re-running.

### 2.10 HIGH — the LLM verifier was structurally unable to do its second job

Found while validating the Groq switch against the golden set (`SHIP_NOTES.md` prescribes exactly
this after any model change). **This is a pre-existing bug in the codebase, not a Groq artefact** —
it applies to any model; a stronger model merely papered over it.

`VERIFIER_SYSTEM` asks the verifier two questions:

> (a) does the cited evidence entail the claim?
> (b) does `chain_text` faithfully instantiate **the cited exposure edge's template**?

But `llm_verify_driver` passed the model only the *driver* and its *cited evidence* — **never the
exposure edge**. Criterion (b) was therefore unanswerable from the inputs given. Observed
consequence: the model collapses (b) into (a) and starts demanding that the evidence prove the
entire causal chain, including the downstream P&L effect.

That is architecturally backwards. Per `DESIGN.md` §3.2 the chain comes from the human-curated
exposure profile; the evidence's only job is to establish the factual premise (the factor moved).
A verbatim strip reason from the run:

> *"The cited evidence does not entail the claim that CRUDE_BRENT rose 3% → channel → pnl negative.
> It only states that CRUDE_BRENT rose 3% on 2026-07-10."*

The evidence stating exactly the factor move is the system **working as designed** — and it was
being counted as a verification failure. On the first golden run this stripped 13 of 20
attributable cases at the `llm` stage, collapsing top-driver hit rate to 15% (bar: 60%).

Fix: pass the exposure edge into the verifier and rewrite `VERIFIER_SYSTEM` to state the
facts-vs-chain split explicitly. This is a **correctness fix, not a loosening** — the verifier can
now actually perform check (b), which it previously could not. The safety metric is the guard:
**NO_DRIVER honesty must stay at 10/10**; if it drops, the change is bad and must be reverted.

> ⚠️ **The fix is NOT yet validated.** The daily token quota was exhausted before the post-fix
> golden run could complete, so the only measured numbers remain the **pre-fix** ones
> (15% hit rate, 10/10 NO_DRIVER honesty, 13 `llm`-stage strips). Re-run
> `pytest -m llm -s tests/test_golden.py` after the quota resets, and treat the reasoning layer
> as unvalidated until it clears the 60% bar with honesty still at 10/10.

### 2.4 HIGH — RELIANCE has no sector, and one row sits in `PENDING_ATTRIBUTION`

`stock.id=6` (RELIANCE) has `sector_id = NULL` — it is missing from `data/sector_map.yaml`, so it
runs with an empty exposure profile and an empty Tier-2 bundle.

*Correction to my first draft:* I attributed the stranded `PENDING_ATTRIBUTION` row to the NULL
sector. That was wrong — `PENDING_ATTRIBUTION` is a legitimate intermediate state consumed by
`run_pending()`, which only executes when `ATTRIBUTION_ENABLED` is true. The row is waiting on the
disabled reasoning layer (§2.3), not on the sector. It is handled gracefully everywhere
(`alerts/selector.py` never alerts on it; `web/data.py` renders it).

**RELIANCE's sector is a genuine judgment call, not a lookup.** It is a conglomerate — O2C
refining/petchem, Jio telecom, and retail. Mapping it to `UPSTREAM_OIL` would assert
`CRUDE_BRENT → +1, output_price, core` — *"crude up is good for this stock"* — at **core** strength.
For a net crude *consumer* that is the wrong sign, and a wrong direction label at core strength is
exactly the failure `DESIGN.md` §7.2 calls the one error the product cannot survive. Mapping it to
`OMC` is closer (crude is `COND`, input_cost) but still asserts a fuel-marketing-margin edge that
overstates a small part of the business.

**Recommendation: leave RELIANCE unmapped and give it curated company overrides instead.** This is
what `DESIGN.md` §3.4 designed the override layer for. Unmapped is the conservative, correct state
in the meantime — generic-but-silent beats specific-but-wrong.

### 2.5 HIGH — Data is 3 weeks stale — **FIXED 2026-07-30**

Last EOD run was **2026-07-11**, leaving ~13 trading days missing. All six stocks have been
backfilled to **2026-07-30**; `daily_metric` went from 140 rows to 834. Nothing is scheduled
yet, though — the APScheduler job only runs while a process is up, so this will go stale again.

### 2.9 CRITICAL — the gate's beta was meaningless (found while validating the catch-up)

**This was the most serious defect in the project** — worse than the Tier-1 gap, because it
silently corrupted the deterministic core that decides whether attribution runs at all.

`build_gate_inputs` aligned the index window to the stock's trading dates, but only via an
all-or-nothing check: if *any* stock date was missing from the index series, it fell back to
`index_series.returns()`, the index's **own, unaligned** series. `classify` then regressed stock
day *i* against index day *i* of a shorter array — pairing different calendar days.

It fires constantly in practice: yfinance returns **4 trading dates for `RELIANCE.NS` that `^NSEI`
does not have** over a 138-day window. Nothing raised; `classify`'s docstring simply assumes
*"aligned historical estimation windows"* and the caller quietly broke that contract.

Measured effect of the fix (pair on the **intersection** of dates instead):

| | before | after |
|---|---|---|
| Average beta, 6 large caps | 0.005 – 0.025 | 0.76 – 1.34 |
| Beta range (HDFCBANK) | [−0.75, +0.87] | [0.87, 1.54] |
| `sigma_idio / sigma60` | ≈ 0.99 | 0.66 – 0.83 |
| **MARKET** classification | 14 days (2.4%) | **52 days (9.0%)** |
| MIXED | 64 (11.0%) | 33 (5.7%) |
| INVESTIGATE | 72 (12.4%) | 60 (10.4%) |

A beta of ~0.02 for TCS or HDFCBANK against NIFTY 50 is not credible; ~1.1 is. Because beta was
≈ 0, `idio = ret − β·index_ret` collapsed to `ret`, so **the market component was never removed**
and the MARKET branch almost never fired.

The practical consequence: **38 trading days were misclassified as stock-specific when they were
market moves.** Under a live reasoning layer each would have burned two LLM calls hunting for a
company-specific driver that did not exist — and any explanation produced would have been
confidently wrong about the most basic question the product asks, *"was this the market or this
stock?"*

Verified against the old code path: it returns **beta 0.245 where the true beta is 1.5**, with
`sigma_idio/sigma60 = 0.988`. Covered now by `tests/test_prices.py` (4 tests, confirmed to fail
against the old logic). No pre-existing test caught this.

### 2.6 MEDIUM — Watchlist too small to validate anything

6 stocks, ~6.5 months of history, 40 of 140 metric-days still `WARMING_UP`.
`SHIP_NOTES.md` prescribes ~20 stocks across ≥6 sectors for the paper run. Also: 0 alerts have ever
been sent, so the Telegram delivery path is untested against a live bot.

### 2.7 MEDIUM — Known, already-logged debt

- **Second price source is effectively absent.** `DESIGN.md` §7.3 mitigates bad price prints with a
  cross-check; `SHIP_NOTES.md` admits it degrades to "not checked" because yfinance `.BO` symbols
  don't resolve. Called out as *"the highest-value hardening item."*
- **Phase-3.5 TODO.** `rubric.text_move_sign` infers factor direction from headline keywords instead
  of the numeric daily return that's already known at ingest. Marked by a strict xfail test.
- **Quarterly exposure-sign audit** (`DESIGN.md` §3.4) is not built.
- **Holiday file** hand-seeded for 2026 with indicative dates; unverified, no 2027.

### 2.8 The UI — and why it looks nothing like Groww

The UI is not missing; it is *deliberately austere*, and that decision is written into the code.
From `app/web/static/style.css` line 2:

> *"Deliberately calm. Color is reserved for the move number and the direction pill; everything else
> (including outcome chips) is neutral. No green/red 'signals'."*

What exists: dashboard cards, a stock detail page with a "How we decided" table, a driver list with
cited evidence links, an exposure-ratification page, and an ops trust dashboard. 150 lines of CSS,
no charts, no price graphs, no portfolio view, no mobile layout.

**This is a direct conflict with what you asked for.** Groww/Upstox/Angel One are portfolio-first,
chart-dense, and colour-coded green/red by design. This app was intentionally built to look like
the opposite of that, because its authors judged that broker-app visual language implies trading
signals the engine refuses to give.

---

## 3. The decision you actually have to make

There is a genuine fork here, and it is not a technical one.

**What you want** (portfolio analysis, ML predictions, broker-style UI) and **what exists**
(an explanation-only engine, explicitly and repeatedly designed to do none of those things) are
different products that happen to share a database.

Three honest paths:

### Path A — Finish and polish the explainer
Fix §2.1–2.6, then build a genuinely good UI *for what it does*.
- Gets you a working, trustworthy product in the shortest time. Most of the hard work is done.
- Does **not** give you portfolio P&L or predictions.

### Path B — Add a portfolio layer on top (additive)
Holdings, cost basis, P&L, allocation, day-change — with "why did this move?" as a detail tab.
- `watchlist_item.qty` already exists for exactly this; `DESIGN.md` §2 notes it *"enables later
  portfolio-level rollups without schema change."* The design anticipated this.
- The explainer becomes the feature that makes your portfolio app different from Groww, rather than
  a worse copy of it.
- Still no ML predictions.

### Path C — Build prediction / ML
This directly reverses the project's founding contract. `DESIGN.md` §3.4 explicitly evaluates and
**rejects** the equivalent (Option B, LLM-derived profiles) on the grounds that *"errors are silent
and land exactly on the product's core promise."* §0 rules out factor models outright.
- Doable, but it is a new project sharing a price pipeline — not a continuation of this one.
- Worth saying plainly: a retail-grade ML price predictor is very unlikely to be profitable, and the
  existing codebase is architected to prevent exactly this.

### My recommendation
**B, then A.** Build the portfolio layer (it's additive, the schema already accommodates it, and it's
what you actually asked for), build one good UI that serves both, and fix the engine gaps in §2.1–2.5
in parallel. Do not start from scratch — you would be throwing away a working quant gate, 48 curated
transmission edges, a verified reasoning pipeline, and 128 passing tests.

**Do not** rebuild from zero. Nothing in this codebase is scrapped.

---

## 4. If we proceed — suggested order

1. **Unstick the engine** (hours): map RELIANCE in `sector_map.yaml`, re-run EOD to catch up 13 days,
   resolve the stranded `PENDING_ATTRIBUTION` row.
2. **Fix Tier-1 ingest** (§2.1) — populate `ticker_bse`, fix the NSE session handshake, make fetch
   failures loud instead of silent. Without this the product cannot reach HIGH confidence.
3. **Turn the reasoning layer on** — set `ANTHROPIC_API_KEY` + `ATTRIBUTION_ENABLED=true`, run the
   live golden set, confirm NO_DRIVER honesty ≥ 8/10 before trusting anything.
4. **Draft + ratify exposure overrides** for the watchlist (§2.2).
5. **Expand watchlist** to ~20 names across ≥6 sectors.
6. **Portfolio layer** — holdings/qty/cost basis, P&L, allocation.
7. **New UI** — designed once, covering both portfolio and explanation.

---

*Nothing in this repo is broken beyond repair. The engine works; the evidence backbone and the
reasoning layer have simply never been switched on, and the product you described is a different
product from the one that was built.*
