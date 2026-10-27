# Mutual funds and research

## Data

- The fund catalog and daily NAV come from the [AMFI open-ended NAV download](https://www.amfiindia.com/net-asset-value/nav-download). The server refreshes every 12 hours while running and stores dated NAV values. NAV is published after market close, never a live quote.
- Sector and macro headlines come from Google News RSS. Company headlines continue to use the stock feed. Each headline links to its publisher. Feeds refresh about every three hours for research and 15 minutes for tracked stocks, subject to provider availability.
- A sector card counts clearly positive and negative headline wording from its last 12 saved stories. It is a **news-tone signal**, not a market-return forecast. A fund category is only a label; it does not reveal current constituent holdings or sector exposure.
- Tracked fund profit/loss uses the user's entered units and average purchase NAV against the latest saved NAV. It excludes distributions, taxes, and transactions.
- Discovery compares active Direct Growth schemes with a published NAV in the last ten days. Curated categories replace raw AMFI category strings; Large Cap and Large & Mid Cap are separate. The default is descending 3-year annualised NAV return, with a 1-year absolute-return option. Ranking happens in SQL before pagination; saved holdings do not jump ahead of better returns.
- Historical anchors come from AMFI's official bulk historical NAV download. The backend checks 1-year and 3-year windows every 12 hours, with bounded retries, and atomically publishes the resulting snapshots. For each scheme, the anchor must be on or before the anniversary and within ten days of it. The one-year calculation is `(latest / anchor - 1) * 100`; the three-year CAGR is `((latest / anchor) ^ (365.25 / elapsedDays) - 1) * 100`. Snapshot dates must match that scheme's latest NAV date. Missing, short, or stale history remains null and appears after ranked schemes; no NAV-price or alphabetical ranking substitutes for a return.
- The explorer intentionally offers only the periods verified through the bulk feed. Regular and IDCW plans are excluded from discovery comparisons to avoid duplicates and NAV-only comparisons that omit income distributions. Existing tracked holdings remain visible. Rankings describe past NAV performance, not an assessment of risk, expense ratios, future returns, or suitability.

## AI research assistant

Set `GEMINI_API_KEY` on the **backend process** to enable Ask Moneyfest. The default model is `gemini-3.5-flash-lite`; override it with `GEMINI_MODEL` if your account supports another model. A Google AI Studio free-tier key can be used subject to your account's current quota. No key is sent to the browser.

The assistant retrieves only the signed-in user's tracked stocks and funds, plus recent linked company and sector headlines from the database. It sends a capped context to Gemini and returns the answer with the actual source links separately. This is retrieval-augmented generation implemented directly with Spring JDBC and the provider's HTTPS API. There is no need for a framework in this small, bounded flow.

The assistant is limited to five requests per user per minute in one server process. Production with several server replicas should move that limit into a shared store and add a global provider budget. Model output is treated as uncertain research, not verified causation or an investment recommendation. If the key is absent, the UI shows setup status; fund tracking and news continue to work.

## Security boundary

Portfolio and fund holdings are stored and filtered by authenticated user ID in the backend. Mutations require the existing session and CSRF token. The AI key remains a server environment secret. Browser code can always be inspected by users; security relies on server authorization and secret handling rather than obscuring bundled JavaScript.
