# Handoff

Pick-up guide for a new session. Written 2026-07-31.

**Read order:** this file → `STATUS_REPORT.md` (honest inventory) → `DESIGN.md` (why) →
`CLAUDE.md` (invariants). `README.md` is the operating manual.

---

## Where the project actually is

The project was described as shelved and broken. It was not — the engine worked; two
critical layers had simply never been switched on, and one silent bug was corrupting the
deterministic core.

| Layer | State |
|---|---|
| Quant gate | ✅ Working. 828 metric rows, 6 stocks, 2025-12-26 → 2026-07-29 |
| Tier-1 evidence (NSE + BSE filings) | ✅ Fixed this session — was 0 rows for the project's whole life, now 42 |
| Tier-2 / Tier-3 evidence | ✅ Working (773 evidence rows total) |
| Exposure store | ⚠️ Sector templates only (48 edges). **0 ratified company overrides** |
| Reasoning layer (2 LLM calls) | ⚠️ Runs end-to-end on Groq, but **unvalidated** — see below |
| Portfolio layer | ✅ New this session. 6 holdings, valuation/P&L/allocation/history |
| Frontend (Moneyfest) | ✅ New this session. 4 routes, builds clean, dark+light+mobile |
| Telegram delivery | ⚠️ Code complete, never exercised against a live bot |

**140 tests pass** offline (`pytest -q`), 1 xfail (the logged phase-3.5 TODO).

Current gate distribution over decidable days: 74% NOISE, 10% INVESTIGATE, 9% MARKET,
5% MIXED. That shape is healthy — if everything lands in INVESTIGATE, thresholds are wrong.

---

## THE BLOCKER — read before touching the reasoning layer

**The verifier fix is written but NOT validated.** Do not treat attribution output as
trustworthy until this clears.

What happened: the golden set scored **15% top-driver hit rate against a 60% bar**, with
**10/10 NO_DRIVER honesty**. Diagnosis found a real pre-existing bug — `VERIFIER_SYSTEM`
asks the model *"does chain_text faithfully instantiate the cited exposure edge's
template?"* but `llm_verify_driver` **never passed it the edge**. That check was
unanswerable, so the model folded it into the entailment check and demanded the evidence
prove the whole causal chain:

> *"The cited evidence does not entail CRUDE_BRENT rose 3% → channel → pnl negative. It only
> states that CRUDE_BRENT rose 3%."*

Evidence stating exactly the factor move is the system **working as designed** —
`DESIGN.md` §3.2 puts the chain in the curated profile, not the evidence. It was being
scored as failure, stripping 13 of 20 cases.

The fix passes the exposure edge into the verifier and splits the two questions explicitly.
It is a **correctness fix** (it enables a check that was previously impossible), not a
loosening to move a number.

### To validate

```bash
pytest -m llm -s tests/test_golden.py
```

Pass criteria: hit rate ≥ 60% **and** NO_DRIVER honesty still 10/10. **If honesty drops,
the change is bad — revert it.** Honesty is the load-bearing safety property; a system that
says "I don't know" is fine, one that invents drivers is not.

Blocked on quota when last attempted: Groq free tier is **100k tokens/day, rolling** (not a
midnight reset), and a 30-case run eats most of it. Quotas are **per model** — confirmed
`openai/gpt-oss-120b`, `llama-3.1-8b-instant` and `openai/gpt-oss-20b` each have their own
budget. If `llama-3.3-70b-versatile` is capped, you can run against another model, but then
**ship the model you validated** — update `_MODEL_DEFAULTS` in `app/config.py` to match.

Before any long LLM run, kill orphan Python processes — `timeout N <cmd>` kills the shell
wrapper, not the Python child, and survivors keep eating the shared token budget:

```powershell
Get-Process python | Where-Object { $_.Id -notin @(<api-pid>, <vite-pid>) } | Stop-Process -Force
```

---

## What was fixed this session (and why it mattered)

1. **Gate beta was meaningless.** `build_gate_inputs` aligned the index to the stock's dates
   with an all-or-nothing check; if *any* date was missing it fell back to the index's own
   **unaligned** series. yfinance gives `RELIANCE.NS` 4 dates `^NSEI` lacks over 138 days, so
   this fired constantly. Average beta was 0.005–0.025 for six large caps (should be ~1);
   `idio` collapsed to `ret`, so the MARKET branch almost never fired. Fixed by pairing on
   the date intersection. **MARKET went 2.4% → 9.0% — 38 days had been misclassified as
   stock-specific when they were market moves.** Regression tests in `tests/test_prices.py`
   (verified to fail against the old logic: beta 0.245 where truth is 1.5).

2. **Tier-1 ingest, 0 rows for the project's entire life.** Three bugs: wrong BSE endpoint
   (`AnnGetData` returns an HTML page with a *200*), missing `Referer` header, and both
   feeds queried unscoped (NSE's bare endpoint returns only the latest ~20 announcements
   exchange-wide). Plus `_fetch_json` swallowed every failure — a Tier-1 outage looked
   identical to "nothing was filed". Now per-symbol with date windows, failures raised.
   **Without Tier-1, HIGH confidence is structurally unreachable** (the rubric requires
   tier 1) and the event trigger can never fire.

3. **NaN closes.** yfinance returns bars with `close = NaN` for an unsettled session. NaN
   passes every `price <= 0` guard, so `log(nan/prev)` = nan and the gate emitted a bogus
   `MIXED` off all-NaN statistics.

4. **Groq 429 handling parked the process for hours.** The retry honoured the server's
   `retry-after` verbatim; a *daily* quota returns hours, so `time.sleep()` waited until
   tomorrow. Presented as a hang (alive, zero CPU, no output). Now capped at 60s with a
   fail-fast message.

5. **`pytest` silently burned LLM quota** once a provider key was set. `pytest.ini` now
   excludes `llm` tests by default.

---

## Next steps, in order

1. **Validate the verifier fix** (above). Everything about attribution trust depends on it.
2. **Ratify exposure overrides.** `exposure` is empty, so every stock runs on a generic
   sector template. `python -m app.exposure.draft --stock TCS --filing <extract>` then
   `python -m app.exposure.ratify --stock TCS`. This is what makes attribution *specific*.
3. **Decide RELIANCE's sector.** It is `sector_id = NULL` (absent from `sector_map.yaml`).
   It is a conglomerate — O2C refining, Jio telecom, retail. Mapping it to `UPSTREAM_OIL`
   asserts `CRUDE_BRENT → +1, core` ("crude up is good"), which is the wrong sign for a net
   crude consumer, and a wrong core-strength direction label is the one error `DESIGN.md`
   §7.2 says the product cannot survive. **Recommendation: leave unmapped, write curated
   company overrides instead.** Unmapped is conservative and correct; generic-but-silent
   beats specific-but-wrong.
4. **Expand the watchlist** to ~20 names across ≥6 sectors (`SHIP_NOTES.md` paper-run plan).
   Currently 6, and 258 of 828 metric-days are still `WARMING_UP`.
5. **Wire settings to the backend.** The UI's alert-level / quiet-market / digest toggles are
   local-only; `GET|PUT /users/{id}/prefs` already exists.
6. **Add/edit holdings from the UI.** `PUT /portfolio/holding` exists; there is no UI for it,
   so the current 6 positions were seeded from a script.
7. **Second price source** — `SHIP_NOTES.md` calls this the highest-value hardening item.
   The BSE `getScripHeaderData` endpoint returns a live LTP and is a candidate.

---

## Known-not-done (deliberate, not forgotten)

- **Auth is a seatbelt.** Shared `WEB_TOKEN` + localhost. The UI sign-in screen
  authenticates nothing and says so on the card. Real auth is a separate pass.
- **Portfolio history is a valuation, not a record.** It applies *today's* quantities to past
  closes; there is no transaction ledger. Labelled as such in the UI.
- **Seed YAMLs are first-draft curation.** `factors.yaml` and `sector_templates.yaml` say so
  in their headers — direction signs need a human pass.
- **Holiday file is hand-maintained.** `data/nse_holidays.yaml` is seeded for 2026 with
  indicative dates; verify against the official NSE list and add 2027.
- **Phase-3.5 TODO.** `rubric.text_move_sign` infers factor direction from headline keywords
  instead of the numeric return already known at ingest. Touches the frozen bundle schema, so
  it needs its own migration pass. Marked by a strict xfail in `tests/test_phase35_todo.py`.
- **Quarterly exposure sign-vs-realised-comovement audit** (`DESIGN.md` §3.4) not built.

---

## Environment

| Var | Purpose |
|---|---|
| `GROQ_API_KEY` | LLM provider (free tier). Set as a Windows user env var. |
| `LLM_PROVIDER` | `groq` (default) or `anthropic` |
| `ATTRIBUTION_ENABLED` | `false` by default — master switch for the reasoning layer |
| `STOCK_EXPLAINER_DB` | DB path override (tests point at a temp file) |
| `WEB_TOKEN` | UI seatbelt; unset ⇒ explicit dev-open mode with a warning |
| `TELEGRAM_BOT_TOKEN` | Telegram delivery; never stored, never logged |

`stock_explainer.db` is gitignored — a fresh clone runs `python -m scripts.bootstrap`, then
`python -m app.jobs.eod` to populate.

---

*Explanation only — not investment advice.*
