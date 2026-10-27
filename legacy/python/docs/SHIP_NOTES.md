# Ship Notes — Stock Impact Explainer

> **Superseded in part.** This documents the original four-phase build. For current state
> — including the portfolio layer, the Moneyfest frontend, the Groq provider switch, and
> the critical gate/Tier-1 fixes made on 2026-07-31 — read **`STATUS_REPORT.md`** and
> **`HANDOFF.md`**. The *paper-run checklist* at the bottom of this file is still the
> right process and has **not** been completed.

The four-phase build is complete. This document is the honest inventory: what exists, what
it deliberately does not do, the known ways it can be wrong, and a paper-run checklist to
work through **before trusting any output**.

---

## What exists

| Layer | Modules | State |
|---|---|---|
| **Quant gate** (deterministic) | `app/tools/gate.py`, `prices.py` | Pure-Python gate: NOISE / MARKET / MIXED / INVESTIGATE / EVENT_NO_MOVE / WARMING_UP / DATA_ISSUE. Config-versioned, reproducible. |
| **Evidence + bundle** | `app/ingest/*`, `app/bundle.py` | Tier-1/2/3 ingestors, `body_hash` dedupe, Constraint-6 bundle filter (ratified-effective profile only). |
| **Exposure store** | `app/exposure/*`, `data/*.yaml` | Closed factor vocabulary, sector templates, draft→ratify override workflow (incl. `SUPPRESS`). |
| **Reasoning** (2 LLM calls) | `app/attrib/*`, `app/llm.py` | Attribution agent → deterministic checks → verifier → pure rubric → ATTRIBUTED / NO_DRIVER. Behind `ATTRIBUTION_ENABLED`. |
| **Delivery + ops** | `app/users.py`, `onboard.py`, `alerts/*`, `jobs/*` | Telegram bot, at-most-once alerts, trading-calendar skip, `run_log`, hardened EOD. |
| **Web UI** | `app/web/*`, `app/api.py` | Dashboard, stock detail, exposure/ratification, ops trust dashboard. Token-gated, localhost. |

**140 tests pass** as of 2026-07-31 (LLM tests excluded by default; 1 xfail = the phase-3.5
follow-up). The engine has been run against real NSE data end-to-end; the gate classifies
every day and the pipeline produces verified, cited explanations or an honest NO_DRIVER.

⚠️ Two rows above were materially wrong when written: **Tier-1 ingested zero rows** for the
entire life of the project, and the gate's **beta was meaningless** due to misaligned
return series. Both are fixed — see `STATUS_REPORT.md` §2.1 and §2.9.

---

## Deliberate non-goals (by design, not omission)

- **No factor model, no computed impact percentages, no ML.** Impact is reasoned and
  cited, never a coefficient. No number the system shows is invented — each comes from a
  DB column or a cited evidence item.
- **No advice.** No buy/sell/hold, price targets, or forward-looking recommendations
  anywhere — gate, rubric, agent schema, renderer, bot, or UI. Enforced by assertions and
  scans, not just convention.
- **NOISE / MARKET / NO_DRIVER are first-class answers.** "Nothing to explain" is the
  product working. Most trading days should land here.
- **Direction is per-stock.** Resolved from the exposure edge (`sign(factor move) ×
  edge.direction`), never inherited from a headline. Two stocks get opposite labels from
  the same macro item.

---

## Known limitations (read before trusting output)

### Carried forward from DESIGN §7 (the three ways this fails in production)

1. **Timestamps lie → causality can invert.** Indian wires republish and news sites rewrite
   `published_at`; a story written *because of* a move can look like its cause. Mitigations
   in place: `first_seen_at` (our crawler clock) is trusted over the publisher's;
   `exchange_dissemination_at` preferred for Tier-1; Tier-3 items first seen after 09:30 IST
   on a move day are flagged `suspect_reactive` and can't lead a driver; the verifier checks
   temporal ordering. **Residual risk:** a reactive item mis-timestamped before the cutoff
   can still slip in as corroboration.
2. **A stale/wrong exposure edge flips a direction label — the one error the product can't
   survive.** Mitigations: the ratification gate (drafts never reach production), `SUPPRESS`
   overrides, `last_reviewed_at`. **Residual risk:** a ratified edge that has since gone
   stale (a company changed its hedging or fuel mix) keeps asserting the old direction until
   someone re-reviews it. The quarterly sign-vs-realized-comovement audit from DESIGN §3.4 is
   **not yet built** — schedule it manually.
3. **Price-data quality breaks the gate itself.** yfinance NSE data has missed corporate
   actions, stale quotes, and bad prints. Mitigations: Gate-0 corporate-action check,
   staleness → DATA_ISSUE. **Residual risk:** the second-source cross-check degrades to
   "not checked" because yfinance `.BO` symbols don't resolve for many BSE scrip codes — so
   a bad print that survives the corp-action check is not currently caught by a second
   source. A reliable second price feed is the highest-value hardening item.

*Honourable mention (watch the ops page):* on any big-move day, Tier-3 media almost always
contains a direction-matching story, so LOW-confidence attribution can drift toward "always
finds something." **If NO_DRIVER frequency trends to zero, the rubric bar is too low** — the
ops page raises this callout automatically.

### phase-3.5 TODO (logged, not fixed)

`rubric.text_move_sign` infers a factor's move direction from **headline keywords**. For
`kind=series` factors the signed daily return is known at ingest time. Tier-2 evidence rows
should carry a numeric `move_sign`/`move_pct` so direction checks don't depend on text
(a macro headline phrased without "rose/fell" yields an indeterminate sign and the check
silently skips). This touches the **frozen bundle schema**, so it needs its own migration
pass. Marked by `tests/test_phase35_todo.py` (strict xfail) and a `TODO(phase-3.5)` in
`rubric.py`.

### Other operational caveats

- **LLM cost & non-determinism.** The reasoning layer is the only non-deterministic part.
  ~2 calls per *eventful* stock-day; NOISE/MARKET days cost nothing. The golden set
  (`tests/test_golden.py`, needs a key) is the regression harness — run it after any prompt
  or model change and watch NO_DRIVER honesty (target ≥ 8/10).
- **Holiday file is hand-maintained.** `data/nse_holidays.yaml` is seeded for 2026 with some
  indicative dates — **verify against the official NSE list and add 2027 before year-end.**
- **Sector map is hand-maintained.** Unmapped tickers onboard with an empty exposure profile
  (event-trigger-only) — correct behaviour, but add them to `data/sector_map.yaml` for rich
  Tier-2 attribution.
- **Auth is a seatbelt.** Single shared `WEB_TOKEN` + localhost binding. Not multi-user
  auth, not hardened for public exposure.
- **Seed YAMLs are first-draft curation.** `data/factors.yaml` and
  `data/sector_templates.yaml` headers say so — direction signs need a human pass.

---

## Suggested 2-week paper-run checklist (before trusting outputs)

Run the system live but **treat every output as a hypothesis to check**, not a conclusion.

**Week 1 — deterministic layer trust**
- [ ] Bootstrap a ~20-stock watchlist across ≥ 6 sectors; run the EOD job daily.
- [ ] Each day, confirm the gate distribution looks sane: the large majority NOISE/MARKET,
      a handful INVESTIGATE/MIXED. If everything is INVESTIGATE, the thresholds are wrong.
- [ ] Spot-check 5 MARKET days on high-beta names against a known market-wide move.
- [ ] Manually verify 3 DATA_ISSUE days were real data problems (corp action / stale print),
      not false positives.
- [ ] Ratify exposure overrides for your watchlist via `/ui/stock/{id}/profile`; confirm each
      draft's citation actually supports the edge before approving.

**Week 2 — reasoning layer trust (enable `ATTRIBUTION_ENABLED`)**
- [ ] For every ATTRIBUTED day, open the evidence links and confirm the cited item says what
      the driver claims — and that the **direction is right for that specific stock**.
- [ ] Track the ops **strip rate**: a healthy trickle is good; zero strips over many
      ATTRIBUTED days warrants a verifier spot-check.
- [ ] Track **NO_DRIVER frequency**: it must not be ~zero. Watch the ops callout.
- [ ] Run the golden set (`pytest -m llm -s tests/test_golden.py`) and record the top-driver
      hit rate and NO_DRIVER honesty; re-run after any prompt/model change.
- [ ] Keep a manual log of every wrong direction label — that is the one error to hunt. If
      you find one, `SUPPRESS` or re-ratify the edge and note why.

**Gate to "trust":** direction labels have been right on every ATTRIBUTED day you checked,
NO_DRIVER fires honestly, and you've caught zero silent data-quality failures for a full
week. Until then, the outputs are a research assistant's notes, not answers.

---

*Explanation only — not investment advice.*
