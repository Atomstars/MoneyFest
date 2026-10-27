# Phase 3 Coding-Agent Prompt — Watchlist, Triggers, Delivery
**Authoritative design: DESIGN.md. Phases 1–2 exist and their tests pass — extend, do not restructure.**
**Phase 3 scope ONLY: watchlist/portfolio persistence, update triggers, scheduling hardening, Telegram delivery. NO UI (Phase 4). No changes to gate, rubric, or verifier logic.**

---

## 0. Pre-flight

1. Confirm the full test suite passes before starting; do not proceed on red.
2. Note for later (do NOT fix now, just add a `# TODO(phase-3.5)` and a failing-xfail test): `rubric.text_move_sign` infers factor-move direction from headline keywords. For `kind=series` factors the actual signed daily return is known — Tier-2 evidence rows should carry a numeric `move_sign`/`move_pct` field so direction checks don't depend on text. Log it as a follow-up; it touches the frozen bundle schema, so it needs its own migration pass.

## 1. What Phase 3 builds

```
Telegram bot (user I/O)                 EOD scheduler (hardened)
  /add /remove /list /explain  ─────►  watchlist + stock onboarding
                                          │
                                    run_eod() → attribution (Phase 2)
                                          │
                                    alert selector + dedupe
                                          │
                                    Telegram delivery + alert log
```

New modules: `app/users.py`, `app/onboard.py`, `app/alerts/selector.py`, `app/alerts/telegram.py`, `app/jobs/calendar.py`. Extend `app/api.py` and `app/jobs/eod.py`.

## 2. Users & watchlist persistence

- `user` table: `(id, telegram_chat_id UNIQUE, display_name, created_at, prefs_json)`. Single-tenant in practice but keep user_id plumbing (already on `watchlist_item`).
- `prefs_json` (defaults in config): `min_alert_level` (`ALL` | `EXPLAINED_ONLY` | `HIGH_ONLY`), `quiet_market_days` (bool — suppress MARKET-outcome alerts), `daily_digest` (bool).
- Watchlist API already exists; add per-user scoping and a `qty` field passthrough (schema already has it). No portfolio math beyond storing qty.

## 3. Stock onboarding (`onboard.py`)

`add_stock(conn, user_id, ticker)` must, in order:
1. Resolve ticker → NSE/BSE symbols and company name (yfinance lookup; fail with a clear message if unresolvable).
2. Assign sector: match against the `sector` table via a hand-maintained `data/sector_map.yaml` (ticker → sector_id). Unmapped tickers get `sector_id=NULL` and a WARNING that only the event trigger will produce rich output (empty exposure profile ⇒ no Tier-2 evidence admitted — that is correct behaviour, not a bug).
3. Warm the price history (200d fetch) so the gate isn't WARMING_UP longer than necessary; write daily_metric backfill rows with gate results (backfill uses the same pure gate — free regression data).
4. Print a reminder to run the exposure drafting + ratification flow (`app.exposure.draft` / `ratify`) — do NOT auto-run the LLM drafter here.

## 4. Trigger & alert selection (`alerts/selector.py`)

Pure function `select_alerts(conn, run_date) -> list[Alert]` over the day's attribution rows for watchlisted stocks:

- Alert-worthy outcomes: `ATTRIBUTED`, `NO_DRIVER`, `EVENT_NO_MOVE` always; `MARKET` only if user pref allows; `NOISE` never (digest-only); `DATA_ISSUE` → admin log, not user alert.
- Respect `min_alert_level`: `HIGH_ONLY` sends ATTRIBUTED only when the top driver is HIGH.
- **Dedupe:** `alert` table `(id, user_id, stock_id, date, attribution_id, outcome, sent_at, delivery_status, UNIQUE(user_id, attribution_id))`. A rerun of the EOD job must never double-send — selection excludes already-sent rows, and send marks the row before the network call (at-most-once beats duplicates for this product).
- Message body = `attribution.rendered_text` verbatim + one metadata line (stock, date, move%). Never re-render or summarise — the verified text is the product.
- Append the fixed disclaimer line from config (`"Explanation only — not investment advice."`) at delivery time, not stored.

## 5. Telegram delivery (`alerts/telegram.py`)

- Raw Bot API via httpx (no heavy framework): `sendMessage` with `parse_mode=HTML`, chunk at 4096 chars.
- Bot token from env `TELEGRAM_BOT_TOKEN`. Never log the token.
- Inbound commands via long-polling worker (`python -m app.alerts.telegram poll`):
  - `/start` → register user (chat_id) with default prefs
  - `/add TICKER`, `/remove TICKER`, `/list`
  - `/explain TICKER` → latest attribution row's rendered_text for that stock (any outcome — NOISE answers too; "nothing to explain" is a feature)
  - `/prefs level=...` etc. (simple key=value parsing)
- All command handlers are thin wrappers over `users.py` / `onboard.py` / DB reads; no business logic in the bot layer.
- Delivery failures: mark `delivery_status='failed'` with error text; a retry sweep at the end of the run retries failures once. Leave permanently failed rows visible in `GET /alerts`.

## 6. Scheduler hardening (`jobs/calendar.py` + eod changes)

- **Trading calendar:** maintain `data/nse_holidays.yaml` (year-keyed list, seeded with the current year's published NSE holiday list — mark the file as maintained-by-hand). Skip the EOD run on weekends and listed holidays; log the skip.
- **Idempotency:** the whole EOD run must be safely re-runnable for the same date (upserts already exist; alert dedupe per §4 completes it). Add `run_log` table `(date, started_at, finished_at, summary_json)` — one row per run attempt.
- **Partial-failure isolation:** one stock's exception must not abort the run (exists — keep) and must land in `run_log.summary_json`.
- **Retry:** if the price fetch for the index fails, retry twice with backoff, then abort the run with a clear run_log entry (nothing sensible can be computed without the index).
- Wire attribution + alert send into the job: gate pass → `run_pending()` (behind `ATTRIBUTION_ENABLED`) → `select_alerts()` → send.

## 7. API additions (still internal/localhost)

`GET /alerts?date=` · `GET /runs` (run_log) · `POST /run_eod` (manual trigger, admin) · `GET /users/{id}/prefs` / `PUT` same. Keep no-auth but bind 127.0.0.1 explicitly.

## 8. Hard rules

- No LLM calls anywhere in this phase's code.
- Rendered text is delivered verbatim; the bot layer may not rewrite, truncate (except 4096 chunking), or embellish it.
- No buy/sell/hold anywhere, including bot replies and the disclaimer line.
- All new tunables in `config.py`; bump version.
- Secrets only via env; nothing secret in the DB or logs.

## 9. Acceptance criteria

1. `pytest` green including new tests: alert selection matrix (outcome × pref level), dedupe-on-rerun (run selector twice, second returns empty), holiday skip, onboarding of an unmapped-sector ticker (warns, event-trigger-only), chunking at 4096.
2. Live smoke test (manual, documented in README): `/start`, `/add TCS`, run `POST /run_eod` against a seeded day, receive the alert in Telegram, rerun `/run_eod`, confirm no duplicate.
3. `/explain TCS` returns the latest rendered text including NOISE days.
4. `run_log` shows one row per attempt with per-stock summaries.
5. README updated: bot setup (BotFather), env vars, holiday-file maintenance, operational runbook (what to check when a run fails).

Stop after acceptance. Phase 4 (UI) is a separate prompt — do not scaffold any frontend.
