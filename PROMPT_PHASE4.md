# Phase 4 Coding-Agent Prompt — The UI
**Authoritative design: DESIGN.md. Phases 1–3 exist and pass — the engine is proven. The UI renders what the engine produced; it computes nothing and rewrites nothing.**
**Scope: web UI + the read APIs it needs + minimal auth. No changes to gate/rubric/verifier/alert logic.**

---

## 0. Principles (the UI restates the product's honesty)

- The rendered explanation text from the engine is displayed **verbatim**. The UI may layout, badge, and link — never rephrase, summarise, or truncate meaningfully.
- NOISE, MARKET, and NO_DRIVER days get equal visual dignity with ATTRIBUTED days. A calm "nothing to explain" screen is the product working, not an empty state to apologise for.
- Every driver shows its evidence citations (source, timestamp, outbound link), its chain sentence, and its confidence badge with the rubric reason. Nothing uncited is ever shown.
- No price charts with prediction overlays, no green/red "signals," no advice anywhere. The move number and direction label are the only colored elements.
- Disclaimer footer on every page (config `DISCLAIMER`).

## 1. Stack

Server-rendered: **FastAPI + Jinja2 templates + htmx** for interactivity, one hand-written CSS file (no Tailwind build step, no npm, no SPA framework). Justification: single-user/localhost product, zero build pipeline, the backend already exists. Deviation from this requires a written reason in the README.

New: `app/web/` (routes), `app/web/templates/`, `app/web/static/style.css`. Mount on the existing FastAPI app under `/ui`. JSON endpoints stay under the existing paths.

## 2. Auth

Single shared token: `WEB_TOKEN` env var. Login page sets a signed cookie (itsdangerous or hmac, stdlib fine); all `/ui` and mutating API routes require it. Localhost binding stays; this is a seatbelt, not a fortress. No user registration UI (users are created via Telegram `/start`).

## 3. Pages

**3.1 Dashboard `/ui`** — the watchlist, one card per stock, for the latest run date (date picker to go back):
- Ticker, name, day's move %, outcome chip (NOISE / MARKET / ATTRIBUTED / NO_DRIVER / EVENT_NO_MOVE / DATA_ISSUE / PENDING).
- One-line teaser: first sentence of rendered_text.
- Sort: eventful outcomes first, then |move| desc. Add-stock box (calls existing onboarding; shows the unmapped-sector warning inline if raised).

**3.2 Stock detail `/ui/stock/{id}`** — the core screen:
- Header: name, tickers, sector, day's move, gate numbers in a quiet expandable ("How we decided": σ, β, index move, idio move, thresholds — plain-language labels, raw numbers secondary).
- The full rendered explanation, verbatim.
- For ATTRIBUTED: driver cards in rank order — direction pill (positive/negative/ambiguous *for this stock*), confidence badge + rubric reason, chain sentence, evidence list (source, first-seen timestamp IST, outbound link, tier label, `suspect_reactive` shown as "published after the move started" tag). Counter-evidence in a visually distinct "on the other hand" block.
- History strip: last 30 trading days as outcome chips linking to that day's view (`/ui/stock/{id}?date=`).

**3.3 Exposure profile `/ui/stock/{id}/profile`** — transparency screen:
- Effective profile as a table: factor, channel, P&L line, direction, strength, provenance (template / curator / llm_draft badge), condition notes, last reviewed.
- Pending drafts (status=draft) in a separate section with Approve / Reject buttons wired to the ratification logic — this replaces the CLI for day-to-day use (CLI stays). Approving stamps last_reviewed_at; the UI must show the draft's source_citation before the approve button is enabled (click-to-reveal).

**3.4 Ops `/ui/ops`** — the trust dashboard:
- run_log table (date, duration, per-stock summary, failures highlighted).
- Strip-rate metrics from verifier logs (by stage, trending) — the hallucination meter, rendered prominently with a plain explanation of what it means.
- Outcome distribution over time (NOISE/MARKET/ATTRIBUTED/NO_DRIVER counts, simple CSS bar chart — no JS chart lib). Callout if NO_DRIVER frequency hits zero over the trailing 30 eventful days ("rubric bar may be too low" warning per DESIGN §7).
- Alert delivery log with failed sends.
- Buttons: manual EOD run, retry failed alerts (both POST to existing endpoints, htmx confirm).

## 4. API additions (JSON, reused by the UI via htmx where convenient)

`GET /stocks/{id}/history?days=30` (outcome chips) · `GET /stocks/{id}/attribution?date=` (full detail incl. drivers + evidence join) · `POST /exposure/{id}/ratify` / `POST /exposure/{id}/reject` (wrap ratify.py logic; require auth token) · `GET /metrics/outcomes?days=90`. All read endpoints must not mutate; ratify endpoints must be the ONLY mutation paths added.

## 5. Hard rules

- No LLM calls. No new computation of any financial quantity — every number displayed must come from an existing DB column.
- `render._FORBIDDEN` scan as a template test: no template or static string contains advice language.
- Timestamps displayed in IST with the zone label.
- Templates escape everything (Jinja2 autoescape on); evidence URLs are the only outbound links, marked `rel="noopener noreferrer"`.
- Works without JavaScript for reading (htmx enhances; plain GET renders still function).

## 6. Acceptance criteria

1. `pytest` green including: auth required on all /ui and mutating routes; ratify-via-UI promotes a draft and it appears in the effective profile; reject removes it; forbidden-language template scan; dashboard renders all seven outcome states from a seeded DB fixture.
2. Manual walkthrough documented in README with screenshots: seeded DB → dashboard → stock detail for an ATTRIBUTED day showing citations and confidence reasons → NO_DRIVER day → profile ratification flow → ops page showing strip metrics.
3. Lighthouse-style sanity: pages under 100KB excluding evidence text, no external CDN dependencies (htmx vendored into static/).
4. README updated: how to set WEB_TOKEN, run the server, and the "reading the ops page" guide (what strip rate and NO_DRIVER frequency should look like when healthy).

This completes the four-phase build. Stop after acceptance and produce a final SHIP_NOTES.md: what exists, known limitations (carry forward DESIGN §7 + the phase-3.5 TODO), and a suggested 2-week paper-run checklist before trusting outputs.
