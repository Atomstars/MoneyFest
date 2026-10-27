# Moneyfest

Moneyfest is a portfolio research app for Indian and US equities and Indian mutual funds. Track stocks in INR or USD, read linked company news, research price trends and build hypothetical portfolios in one personal workspace.

The new US stocks, stock research and portfolio builder sections are documented in [global research](docs/GLOBAL_RESEARCH.md). Portfolio coaching works with clearly labeled allocation rules without an AI key; broader AI answers use the optional Gemini connection.

Explore the [interactive architecture diagram](.archify/architecture-moneyfest-20261014-151740/moneyfest-architecture.html) for the current frontend, backend, database, external feeds, and optional AI path.

The current app is Spring Boot, PostgreSQL, and React. A previous Python explanation engine remains in the repository as a reference; its verified attribution logic is not yet connected to the Java app.

## Run locally on Windows

Requires Java 21+, Node.js, and PostgreSQL binaries. From the repository root:

```powershell
cd frontend
npm ci
cd ..
./scripts/start-app.ps1
```

Open <http://127.0.0.1:5174> and create an account. The startup script creates local databases, runs Flyway migrations, and starts the API and Vite. If PostgreSQL binaries are unavailable, run `./scripts/setup-local-postgres.ps1` first. Stop the app with `./scripts/stop-app.ps1`.

For a temporary phone preview away from the same Wi-Fi, run `npm run build` in `frontend`, download the current official Cloudflare `cloudflared` Windows binary into `.local/cloudflared.exe`, then run `./scripts/start-remote-preview.ps1 -AllowedEmail you@example.com` from the root. The script serves the built frontend on localhost and prints a temporary HTTPS URL protected by an email one-time PIN. Keep the computer and app running while testing. Run `./scripts/stop-remote-preview.ps1` to close the tunnel. This is a development preview, not permanent hosting.

To enable Ask Moneyfest, set `GEMINI_API_KEY` in the **backend process environment** before starting. The default model is `gemini-3.5-flash-lite`; `GEMINI_MODEL` can override it. The fund, stock, and news features work without an AI key. See [.env.example](.env.example), [development setup](docs/DEVELOPMENT.md), and [funds and research](docs/FUNDS_AND_RESEARCH.md).

## Current behavior

| Area | Behavior |
| --- | --- |
| Stocks | Search the synced NSE/BSE equity catalog, record holdings, watch stocks, and view last available closing prices. |
| News | Use a split-pane inbox on desktop and a separate reading screen on mobile; filter headlines, mark them read, save up to 200 on this device, and open the company's research. |
| Funds | Browse clear fund categories ranked by 3-year annualised or 1-year absolute returns from AMFI history; track units and purchase NAV in a personal portfolio. |
| Research | Inspect recent sector and macro headlines with a clearly labeled news-tone signal. |
| Assistant | Optional server-side Gemini answers grounded in your tracked holdings and saved linked headlines. |
| Accounts | Password hashing, owner-scoped data, persistent sessions, CSRF protection, and request limits on authentication and AI. |

News tone and AI scenarios do not establish why a price moved or reliably predict future returns. Fund categories do not reveal a scheme's actual holdings. There is no live trading, automatic rebalancing, or investment recommendation. Data feeds are best effort and retain saved data when a provider fails.

## Development checks

```powershell
cd backend
./mvnw.cmd test
cd ../frontend
npm run build
npm run lint
```

Browser tests use `npm run test:e2e` against a running local app. See [market data notes](docs/MARKET_DATA.md) for sources and refresh behavior. The old Python prototype and its documentation are preserved in [legacy/python](legacy/python/README.md).

## Repository layout

| Path | Purpose |
| --- | --- |
| `backend/src/main/java/com/moneyfest/api` | HTTP resources grouped by auth, portfolio, market, funds, and research |
| `backend/src/main/java/com/moneyfest/service` | Fund portfolio operations, market sync, fund sync, and research processing |
| `backend/src/main/java/com/moneyfest/repository` | Fund portfolio persistence and catalog queries |
| `backend/src/main/java/com/moneyfest/provider` | External market and news provider client |
| `backend/src/main/java/com/moneyfest/config` | Spring Security configuration |
| `backend/src/main/resources/db/migration` | Versioned PostgreSQL schema |
| `frontend/src` | React application |
| `scripts` | Local Windows launch and database scripts |
| `docs` | Current engineering notes and archived plans |
| `legacy/python` | Preserved, inactive Python prototype |

The fund HTTP resource delegates to a service and repository. Other API resources still contain some data-access and business logic. Extracting these into dedicated application services and repositories remains an architectural task; the package layout alone does not claim that separation is complete.
