# Global stocks, research and portfolio planning

MoneyFest now has dedicated `/us-stocks`, `/stock-research` and `/portfolio-lab` screens.

## Listings and data

US ordinary shares and ADRs are loaded from Nasdaq Trader's `nasdaqlisted.txt` and `otherlisted.txt` symbol directories. ETF and test flags are excluded, along with recognized warrants, preferreds, units and rights. This is best-effort coverage, not a promise of broker eligibility or a complete worldwide security master. Nasdaq documents the fields at https://www.nasdaqtrader.com/trader.aspx?id=symboldirdefs.

US records use a `.US` internal ticker namespace so names such as `V` cannot collide with Indian listings. `symbol` retains the exchange symbol, and `provider_symbol` maps share classes such as `BRK.B` to `BRK-B` for Yahoo. The catalog sync runs with the existing market job and keeps prior data after failures. It currently upserts listings; removal of delisted securities is not automated.

Prices come from Yahoo Finance's best-effort daily chart endpoint. USD responses must declare USD, and INR responses must declare INR. Current-day US bars are withheld before 16:30 America/New_York; Indian bars are withheld before 16:00 Asia/Kolkata. Time zones handle daylight saving. These are saved closing bars, not real-time quotes or adjusted total returns.

US company headlines use Google News RSS with the US locale, the existing relevance filter, seven-day window, deduplication and conservative wording sentiment. Six initial US companies are refreshed in the background; other stocks refresh when viewed in the research screen, tracked, saved in a plan or explicitly refreshed. Requests are cached for 15 minutes. The US news tab shows saved US headlines across the catalog. An empty feed never fabricates stories.

## Currency boundaries

The holdings dashboard has INR and USD views. `/me/portfolio`, `/me/portfolio/allocation` and `/me/portfolio/history` accept `currency=INR|USD` and default to INR. Values from different currencies are never added together. There is no FX conversion. Historical values continue to use current quantities at historical closes, rather than transaction-based performance. A holding without the selected currency's latest closing snapshot is excluded from priced totals and reported as unpriced.

## Stock research and trade mechanism

`GET /stocks/{id}/research` returns saved closes, the last-close day change, 20- and 50-session simple moving averages, recent linked headlines and provider status. An uptrend requires close > SMA20 > SMA50; a downtrend requires the reverse. Other arrangements are mixed. Fewer than 50 observations produce an insufficient-data result. Trends describe past data and are not forecasts.

The trade calculator is a hypothetical long-position calculation: whole shares = floor(risk budget / (entry − stop)); reward/risk = (target − entry) / (entry − stop). Inputs require 0 < stop < entry < target and positive risk budget. It excludes fees, taxes, FX, gaps and slippage. No broker connection or order execution is provided. Order-type explanations link to Investor.gov.

## Portfolio builder and coach

Each account has one server-saved hypothetical draft, separate from recorded holdings. A plan stores a currency, budget, risk preference, 1–40 year horizon and up to 30 distinct catalog stocks. Weights must be positive, total at most 100%, and match the plan currency. Unallocated budget remains visible. Saving another currency replaces the draft; the UI discloses this. Market switches retain separate selections in memory for the current editing session; the account still has one server-saved draft.

The allocation review checks single-name concentration against a simple 25% threshold, shows unallocated budget, and highlights horizon, asset-class and currency considerations. Sector metadata is incomplete; these checks cannot establish diversification or rank expected returns.

The allocation studio provides range and numeric weight editing, session-only weight locks, equal-weight or proportional balancing, undo/redo, and comparison with the last saved draft. Balancing works in basis points and distributes rounding remainders across companies; locked weights stay unchanged. Importing holdings uses recorded cost proportions and leaves actual holdings untouched. Whole-share estimates use saved closes, round down, and exclude fees, taxes and FX.

The downside calculator applies the chosen decline uniformly to the stock allocation while leaving planned cash unchanged. This is a hypothetical budget scenario, not a model of market probabilities or future returns. An overallocated or invalid draft cannot be saved or reviewed.

Typography is self-hosted IBM Plex Sans and IBM Plex Mono, distributed with their license in `frontend/public/fonts/IBM-Plex-LICENSE.txt`. No external font service is called by the app.

The Portfolio agent saves the exact current draft before answering. Without `GEMINI_API_KEY`, it uses `POST /me/portfolio-plan/review`, explicitly labeled as a rules-based coach. Its responses use the saved plan and a small set of question topics, not a language model. It does not rank stocks or claim an optimal portfolio. With a configured Gemini connection, the existing AI endpoint receives owner-scoped plan identities and weights plus saved linked news. Other assistants remain optional AI features. AI provider calls were not validated without a credential.

## Validation

Backend tests cover catalog filtering, US closing-time handling, currency isolation, trend calculations, owner separation, plan validation, CSRF and the rules coach. Browser tests cover US news, research, invalid trade inputs, allocation editing, persistence, coach answers and mobile overflow, alongside the existing app suite.

Run backend tests before starting the fixture browser server, because the tests clear the dedicated `moneyfest_test` database. Run browser checks against `scripts/start-app.ps1 -SkipBuild -TestDatabase -ApiPort 8081 -WebPort 5175`, with `E2E_URL=http://127.0.0.1:5175`. Do not point fixture-dependent browser tests at the personal workspace database.
