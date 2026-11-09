# Hosted MoneyFest

The React frontend is deployed from frontend/ to Vercel. The Java 21 Spring Boot API and PostgreSQL database are defined in render.yaml for Render's Singapore region.

## Runtime

- The API uses the production Spring profile, binds 0.0.0.0 and the platform PORT, and validates its database with /api/v1/health.
- Render supplies database properties and credentials through Blueprint references. No credential is committed.
- PostgreSQL accepts private-network connections only. Flyway applies versioned migrations when the API starts.
- The Java container runs as an unprivileged user, with a bounded heap and a five-connection database pool.
- Existing GitHub Actions checks verify Java integration tests, frontend compilation, and browser workflows. Subsequent API releases wait for these checks.
- Keep API calls on the frontend origin through a Vercel /api/:path* rewrite to the actual backend origin after provisioning. Preserve /api in the destination path. Never put database credentials in frontend variables.
- Verify health, CSRF token issuance, registration, login, session persistence, user isolation, portfolio reads/writes, and logout through the Vercel origin after connecting the API.
- GEMINI_API_KEY is optional; configure it only on the backend. Core account and portfolio features do not need it.

## Free deployment limits

The selected API and database plans are free. Free Render services sleep when idle. Free PostgreSQL expires after 30 days and has no managed backups; this configuration is for a temporary portfolio deployment. Upgrade or migrate the database before expiration to retain data. No paid upgrade is authorized by this configuration.

## Checkpoint

Before backend hosting changes: 2163d39b4202d753f9b27c56f9496a01ad79d9b2.
The existing frontend deployment and source remain available for rollback. Rolling back application code does not reverse database migrations.
