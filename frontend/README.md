# Moneyfest frontend

React, TypeScript, Vite, and Tailwind. The browser uses the Spring Boot API through a same-origin `/api` proxy, so session cookies and CSRF protection work locally.

From the repository root, run `./scripts/start-app.ps1` to start the database, API, and frontend together. For frontend-only work, start the API first, then run `npm ci` and `npm run dev` here. The app defaults to <http://127.0.0.1:5174> with the root startup script.

Run `npm run build`, `npm run lint`, and `npm run test:e2e` for verification. Browser tests require a running app and Playwright Chromium. See the [root README](../README.md) for features, limitations, and backend setup.
