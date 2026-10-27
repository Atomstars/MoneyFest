# Portfolio and news workspace

The Java app now downloads a searchable NSE/BSE equity catalog, imports daily closing
prices, and maintains a personal news inbox. No API key is needed for these adapters.

## Providers and scope

- Catalog: [Upstox public instrument files](https://upstox.com/developer/api-documentation/instruments/), refreshed daily. NSE `EQ` and BSE equity trading groups are included; debt, derivatives and funds are excluded. Coverage is the provider's available Indian listings, not every stock worldwide. BSE holdings use `.BSE` suffixes to distinguish them from NSE holdings. Provider exchange tokens supply BSE quote codes; codes are never guessed.
- Prices: Yahoo Finance's public chart endpoint, six months of daily closes. This is an unofficial, best-effort adapter and may be throttled or unavailable. Current-day bars are excluded until 16:00 Asia/Kolkata. Missing prices stay missing; saved values are retained when a refresh fails. These are not live quotes, adjusted total returns, or a transaction ledger.
- News: Google News RSS company searches from the last seven days. Headlines must mention the company or an unambiguous symbol. Stories are stored with source, URL, publication time and a deduplication fingerprint. Provider name abbreviations can reduce matching coverage.

## Refresh and inbox behavior

While the backend runs, its scheduler checks every 15 minutes. Holdings and watchlist
stocks are refreshed; adding either queues a refresh immediately. Users can also refresh
their tracked stocks or an individual stock. Stock requests have a 15-minute cooldown,
a bounded queue and provider timeouts. A daily catalog failure is retried at the next
scheduled pass. Scheduled jobs do not run while the server is stopped.

The news inbox supports holdings/watchlist scope, positive/negative/mixed/neutral filters,
pagination and persistent, per-account read state. In-app updates are available; email,
push and Telegram delivery are not connected to this Java pipeline. Existing delivery
preferences are stored for a later verified-driver pipeline and do not filter the news feed.

Each concise news entry is the source headline with its publisher suffix removed, not
an invented AI summary. Sentiment uses conservative event phrases; negation/speculation
defaults to neutral and conflicting phrases to mixed. It is **headline sentiment, not
verified stock impact or evidence that a headline caused a price move**. The existing
Python attribution engine has not been ported or silently replaced with these rules.

## Operations

Flyway V3 adds exchange identifiers, synchronization status, persisted news and read receipts.
`MARKET_DATA_ENABLED=false` disables external fetching. Tests and the `-TestDatabase`
startup script disable it by default. Deploying commercially requires checking provider
terms and replacing best-effort endpoints with a suitably licensed data service.

Authenticated endpoints:

| Endpoint | Purpose |
| --- | --- |
| `GET /api/v1/stocks?query=&filter=all&exchange=ALL&offset=0` | Server search and paging; 40 rows plus one lookahead |
| `GET /api/v1/market/status` | Catalog counts, timestamps and provider state |
| `POST /api/v1/me/refresh` | Queue tracked stocks |
| `POST /api/v1/stocks/{id}/refresh` | Queue one stock |
| `GET /api/v1/me/news` | News with scope, sentiment, unread, stockId and offset filters |
| `PUT /api/v1/me/news/{id}/read` | Mark a tracked story read for the signed-in account |

POST/PUT requests require the existing CSRF token. News source content remains plain
text, outgoing links require HTTPS, and RSS parsing disables external entities.
