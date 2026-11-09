# Hosted MoneyFest

The React frontend is deployed from frontend/ to Vercel. The Java 21 Spring Boot API is defined in render.yaml for Render's Singapore region. PostgreSQL is hosted separately on Neon's Free plan.

## Runtime

- The API uses the production Spring profile, binds 0.0.0.0 and the platform PORT, and validates its database with /api/v1/health.
- Set DB_URL, DB_USER and DB_PASSWORD as backend secrets. DB_URL must be a JDBC URL without embedded credentials: jdbc:postgresql://<Neon-host>/<database>?sslmode=verify-full. Do not paste a postgres:// URL into a JDBC configuration. No credential is committed.
- The API connects to Neon over TLS with certificate verification. Flyway applies versioned migrations when the API starts.
- The Java container runs as an unprivileged user, with a bounded heap and a five-connection database pool.
- Existing GitHub Actions checks verify Java integration tests, frontend compilation, and browser workflows. Subsequent API releases wait for these checks.
- Keep API calls on the frontend origin through a Vercel /api/:path* rewrite to the actual backend origin after provisioning. Preserve /api in the destination path. Never put database credentials in frontend variables.
- Verify health, CSRF token issuance, registration, login, session persistence, user isolation, portfolio reads/writes, and logout through the Vercel origin after connecting the API.
- GEMINI_API_KEY is optional; configure it only on the backend. Core account and portfolio features do not need it.

## Free deployment limits

The selected API and database plans are free. Free Render services sleep after inactivity and share a workspace allowance. Neon Free has no fixed expiry and no card requirement; its compute, storage, and network quotas still apply. The pool permits zero idle connections. Do not add artificial keep-alive requests. This configuration creates no Render Postgres database and authorizes no paid plan.

## Checkpoint

Before backend hosting changes: 2163d39b4202d753f9b27c56f9496a01ad79d9b2.
The existing frontend deployment and source remain available for rollback. Rolling back application code does not reverse database migrations.
