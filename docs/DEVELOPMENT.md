# Java development milestone

MoneyFest now has a Spring Boot 3.5.16 / Java 21-target backend and a connected React
frontend. PostgreSQL stores accounts, hashed passwords, sessions, holdings, watchlists
and preferences. The Python explanation engine remains a reference implementation;
its verified attribution has not yet been migrated into Java. Java now has a separate
catalog, closing-price and company-news pipeline; see [market data behavior](MARKET_DATA.md).
Mutual fund tracking and the research desk are documented in [funds and research](FUNDS_AND_RESEARCH.md).

## Windows quick start

Requirements: Java 21 or a compatible newer JDK, Node, and PostgreSQL server binaries.
Maven Wrapper pins Maven 3.9.12. On a machine without complete PostgreSQL tools,
`./scripts/setup-local-postgres.ps1` downloads a pinned project-local runtime from
Maven Central (Zonky's embedded PostgreSQL binary package). Python 3.12+ is needed
only for that archive extraction helper. No system database service is changed.

From the project root:

```powershell
cd frontend
npm ci
cd ..
# Only when a complete PostgreSQL installation is unavailable:
./scripts/setup-local-postgres.ps1
./scripts/start-app.ps1
```

Open http://127.0.0.1:5174. Register your own account, add holdings, edit/remove them,
browse the catalog, manage a watchlist and save preferences. The Java API listens on
127.0.0.1:8080 and Vite proxies /api to it. Port 5174 avoids the other local project
already using 5173. Do not mix localhost and 127.0.0.1 within a session.

For a phone on the same Wi-Fi, stop the app and restart with
`./scripts/start-app.ps1 -SkipBuild -Lan`. Open the LAN URL printed by the script.
Only the Vite web port is exposed; the Java API remains bound to loopback and is
reached through Vite's same-origin proxy. Windows Firewall may need a rule allowing
the web port from the local subnet.

For a phone away from that Wi-Fi, use the protected temporary preview described in the
[root README](../README.md). It requires a reachable email address for a one-time PIN,
and the development computer must remain on. The preview serves a built frontend and
proxies `/api` to the loopback Java process.

`start-app.ps1` builds the backend, starts a separate PostgreSQL cluster on loopback
port 55432, creates `moneyfest` and `moneyfest_test`, and starts hidden Java/Node
processes. Logs and process IDs are in `.local/` (gitignored). This local database
allows trusted connections from this computer only; production requires explicit
credentials and secure cookies. Stop the app with `./scripts/stop-app.ps1`; stop its
database separately with `./scripts/stop-database.ps1`. Scripts check recorded process
command lines before stopping them. A running server on a requested port is never killed.

Manual startup after database initialization:

```powershell
cd backend
./mvnw.cmd spring-boot:run '-Dspring-boot.run.profiles=local'
# In another terminal:
cd frontend
npm run dev -- --host 127.0.0.1 --port 5174 --strictPort
```

The local profile uses the project database. Default configuration requires DB_URL,
DB_USER and DB_PASSWORD and enables secure session cookies. `.env.example` documents
settings; Spring does not automatically read .env files. Set environment variables or
use your deployment secret manager. `compose.yaml` offers a database alternative when
Docker is available; use its password in DB_PASSWORD and the matching JDBC URL.

## Honest data states

The catalog starts with ten seeds and syncs available NSE/BSE equities from Upstox.
Holdings and watchlists trigger closing-price and news refreshes. Missing prices show a
dash; provider failures preserve saved data and are visible in the news feed. In-app news
has source links, headline sentiment and persistent read state. Verified move attribution
and external alert delivery remain unconnected. See MARKET_DATA.md for coverage limits.

Rates in API responses are fractions (0.1 = 10%). Monetary calculations use BigDecimal
and PostgreSQL NUMERIC. Portfolio P&L uses priced positions only; invested capital
includes all holdings and missing positions are disclosed. History still values today's
quantities at past closes and excludes dates with incomplete price coverage. A transaction
ledger, corporate-action processing, live quotes and total-return history are future work.

## Verification

```powershell
cd backend
./mvnw.cmd test
cd ../frontend
npm run build
npm run lint
```

Java integration tests run real HTTP requests against a random server port and the
dedicated PostgreSQL `moneyfest_test` database. They reset that test database's account,
position and price data and refuse a database name without the `_test` suffix. Never
point tests at an application database. CI can override TEST_DB_URL, DB_USER and DB_PASSWORD.

Browser tests use a separate test server pair:

```powershell
./scripts/start-app.ps1 -ApiPort 8081 -WebPort 5175 -TestDatabase
cd frontend
npm run test:e2e
cd ..
./scripts/stop-app.ps1 -WebPort 5175
```

The browser suite uses installed Chrome by default. E2E_BROWSER can select `msedge` or
`chromium` (install Playwright Chromium first for the latter). E2E_URL overrides the
test UI address. Tests create unique users in the test database. They cover registration,
position edits, persistence after reload, missing assessments, watchlists, saved settings,
logout, protected routes and a mobile viewport.

## API implemented in this milestone

All routes begin with `/api/v1`. Mutations require the token/header from GET /auth/csrf.
Sessions are HttpOnly cookies persisted through Spring Session JDBC. Requests derive
ownership from the signed-in principal; unknown input fields are rejected.

| Routes | Behavior |
|---|---|
| GET /health | Database health and market integration status |
| GET /auth/csrf; POST /auth/register, /auth/login, /auth/logout; GET /auth/me | Account session lifecycle |
| GET /stocks; GET /stocks/{id}/prices, /stocks/{id}/assessment | Catalog, stored prices and assessment state |
| GET /me/portfolio, /me/portfolio/allocation, /me/portfolio/history | Personal portfolio queries |
| PUT /me/portfolio/positions; DELETE /me/portfolio/positions/{ticker} | Current-position entry/removal |
| GET /me/watchlist; PUT/DELETE /me/watchlist/{stockId} | Personal watchlist |
| GET/PUT /me/preferences | Persist alert preferences |
| GET /funds, /funds/categories, /funds/{code}/nav; GET /me/funds | AMFI scheme catalog, NAV history and fund portfolio |
| PUT/DELETE /me/funds/positions | Record or remove fund holdings |
| GET /me/news, /research/themes, /market/status; POST /me/refresh | Linked company, sector and macro news signals with best-effort refresh |
| GET /me/assistant/status; POST /me/assistant | Optional Gemini response grounded in saved portfolio and source headlines |

Next milestone: transaction semantics and migration of the deterministic gate, evidence
and daily processing; then validated attribution and alert delivery. [The archived plan](archive/FULL_STACK_PLAN.md)
contains the full roadmap. This milestone is a working foundation, not the finished app.

Verified locally in October 2026: 19 Java tests, 3 browser scenarios, the frontend
build, and lint passed. GitHub Actions configuration is included but has not been
executed remotely. The archived Python baseline is independent of the current app.
