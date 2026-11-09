# Hosted MoneyFest

The React frontend is deployed from frontend/ to Vercel. The Java 21 Spring Boot API is defined in render.yaml for Render's Singapore region. PostgreSQL is hosted separately on Neon's Free plan.

## Runtime

- The API uses the production Spring profile, binds 0.0.0.0 and the platform PORT, and validates its database with /api/v1/health.
- Set DB_URL, DB_USER and DB_PASSWORD as backend secrets. DB_URL must be a JDBC URL without embedded credentials: jdbc:postgresql://<Neon-host>/<database>?sslmode=verify-full&sslfactory=org.postgresql.ssl.DefaultJavaSSLFactory. Do not paste a postgres:// URL into a JDBC configuration. No credential is committed.
- The API connects to Neon over TLS with certificate verification. Flyway applies versioned migrations when the API starts.
- The Java container runs as an unprivileged user, with a bounded heap and a five-connection database pool.
- Existing GitHub Actions checks verify Java integration tests, frontend compilation, and browser workflows. The current Render service auto-deploys main on commit; the Blueprint template uses checksPass for future Blueprint-managed setup.
- API calls remain on the frontend origin through a Vercel /api/:path* rewrite to https://moneyfest-api.onrender.com/api/:path*. Preserve /api in the destination path. Never put database credentials in frontend variables.
- Verify health, CSRF token issuance, registration, login, session persistence, user isolation, portfolio reads/writes, and logout through the Vercel origin after connecting the API.
- GEMINI_API_KEY is optional; configure it only on the backend. Core account and portfolio features do not need it.

## Free deployment limits

The selected API and database plans are free. Free Render services sleep after inactivity and share a workspace allowance. Neon Free has no fixed expiry and no card requirement; its compute, storage, and network quotas still apply. The pool permits zero idle connections. Do not add artificial keep-alive requests. This configuration creates no Render Postgres database and authorizes no paid plan.

## Checkpoint

Before backend hosting changes: 2163d39b4202d753f9b27c56f9496a01ad79d9b2.
The existing frontend deployment and source remain available for rollback. Rolling back application code does not reverse database migrations.

## Verified deployment — 2026-11-09

- App: https://moneyfest-beta.vercel.app
- Backend health: https://moneyfest-api.onrender.com/api/v1/health
- Frontend-proxied health: https://moneyfest-beta.vercel.app/api/v1/health
- Render API service: srv-dbot0djm8hqs73euvl00, free plan, Singapore.
- Neon project: quiet-frost-89439351, free organization, Singapore, PostgreSQL 18, fixed 0.25 CU.
- Source revision tested: 7268d5cff3cdfc280a0a3e890c8000959d3b1b8a.
- Render deploy dep-dbot1ngqr7gs73b7l2ig reached live. All seven Flyway migrations succeeded.
- Full-stack CI passed: https://github.com/Atomstars/MoneyFest/actions/runs/42629511943
- Public-origin production smoke checks passed: https://github.com/Atomstars/MoneyFest/actions/runs/42629512189
- Production checks covered API/database health, unauthenticated access, CSRF rejection, registration, cookie session continuity, empty portfolio reads, persisted preferences, logout/login, and independent-session isolation.
- One synthetic Deployment check account was retained. No personal account or holdings were used.
- Live browser rendering/responsiveness was not independently rechecked; the repository browser suite passed against the isolated test application.
- Optional Gemini AI requires a backend-only key and was not configured by this deployment.
- The Render Blueprint remains unapplied. No Render database was created; the API was created directly with the user's approved private Neon environment variables.
