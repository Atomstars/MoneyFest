-- Stock Impact Explainer -- SQLite schema (Phase 1)
-- Tables follow DESIGN.md section 2 exactly. attribution/driver are created now
-- but only written with NOISE/MARKET/EVENT_NO_MOVE/PENDING_ATTRIBUTION in Phase 1.
--
-- SQLite has no native array/bool types; we use INTEGER for booleans and store
-- list-valued columns (keywords, evidence_ids) as JSON text. Nullable columns are
-- explicitly annotated in comments.

PRAGMA foreign_keys = ON;

-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sector (
    id               INTEGER PRIMARY KEY,
    name             TEXT NOT NULL UNIQUE,
    template_version TEXT
);

CREATE TABLE IF NOT EXISTS stock (
    id           INTEGER PRIMARY KEY,
    ticker_nse   TEXT,             -- e.g. TCS
    ticker_bse   TEXT,             -- e.g. 532540
    name         TEXT NOT NULL,
    sector_id    INTEGER REFERENCES sector(id),
    listing_meta TEXT,             -- JSON blob, nullable
    UNIQUE (ticker_nse, ticker_bse)
);

-- Phase 3: Telegram users (single-tenant in practice; user_id plumbing kept).
CREATE TABLE IF NOT EXISTS user (
    id               INTEGER PRIMARY KEY,
    telegram_chat_id TEXT UNIQUE,
    display_name     TEXT,
    created_at       TEXT NOT NULL,
    prefs_json       TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS watchlist_item (
    id         INTEGER PRIMARY KEY,
    user_id    TEXT NOT NULL DEFAULT 'default',
    stock_id   INTEGER NOT NULL REFERENCES stock(id),
    qty        REAL,               -- nullable; enables portfolio rollups later
    added_at   TEXT NOT NULL,
    UNIQUE (user_id, stock_id)
);

-- Canonical closed factor vocabulary (~30 rows seeded from data/factors.yaml).
CREATE TABLE IF NOT EXISTS factor (
    id            TEXT PRIMARY KEY,   -- e.g. CRUDE_BRENT (stable string id)
    name          TEXT NOT NULL,
    kind          TEXT NOT NULL CHECK (kind IN ('series', 'event')),
    series_source TEXT,               -- nullable for event factors
    keywords      TEXT NOT NULL DEFAULT '[]',  -- JSON array of strings
    tier          INTEGER,            -- typical evidence tier for this factor
    unit          TEXT,
    description   TEXT
);

-- Hand-curated per-sector transmission edges (from data/sector_templates.yaml).
CREATE TABLE IF NOT EXISTS sector_template (
    id                  INTEGER PRIMARY KEY,
    sector_id           INTEGER NOT NULL REFERENCES sector(id),
    factor_id           TEXT NOT NULL REFERENCES factor(id),
    channel             TEXT NOT NULL,
    pnl_line            TEXT,
    direction           TEXT NOT NULL CHECK (direction IN ('-1', '+1', 'COND')),
    condition_note      TEXT,
    strength            TEXT NOT NULL CHECK (strength IN ('core', 'secondary')),
    chain_template_text TEXT NOT NULL,
    UNIQUE (sector_id, factor_id)
);

-- Per-stock overrides: add / remove / flip template edges.
CREATE TABLE IF NOT EXISTS exposure (
    id              INTEGER PRIMARY KEY,
    stock_id        INTEGER NOT NULL REFERENCES stock(id),
    factor_id       TEXT NOT NULL REFERENCES factor(id),
    channel         TEXT NOT NULL,
    pnl_line        TEXT,
    -- SUPPRESS is override-only: a ratified SUPPRESS row REMOVES the factor's edge
    -- from the effective profile (DESIGN.md 3.1 -- overrides may add, flip, or remove).
    direction       TEXT NOT NULL CHECK (direction IN ('-1', '+1', 'COND', 'SUPPRESS')),
    condition_note  TEXT,
    strength        TEXT NOT NULL CHECK (strength IN ('core', 'secondary')),
    rationale       TEXT,
    provenance      TEXT NOT NULL CHECK (provenance IN ('template', 'curator', 'llm_draft')),
    source_citation TEXT,
    status          TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'ratified')),
    last_reviewed_at TEXT,
    magnitude_note  TEXT,           -- reserved for future annual-report mining; unused in v1
    UNIQUE (stock_id, factor_id, status)
);

-- One normalised row per ingested evidence item.
CREATE TABLE IF NOT EXISTS evidence (
    id                        INTEGER PRIMARY KEY,
    tier                      INTEGER NOT NULL CHECK (tier IN (1, 2, 3)),
    source                    TEXT NOT NULL,
    url                       TEXT,
    headline                  TEXT,
    body_text                 TEXT,
    body_hash                 TEXT NOT NULL,   -- dedupe key
    stock_id                  INTEGER REFERENCES stock(id),     -- nullable
    factor_id                 TEXT REFERENCES factor(id),       -- nullable
    published_at              TEXT,            -- publisher clock (untrusted)
    first_seen_at             TEXT NOT NULL,   -- OUR crawler clock (trusted)
    exchange_dissemination_at TEXT,            -- Tier-1 only
    suspect_reactive          INTEGER NOT NULL DEFAULT 0,  -- boolean
    UNIQUE (body_hash)
);
CREATE INDEX IF NOT EXISTS idx_evidence_stock ON evidence(stock_id);
CREATE INDEX IF NOT EXISTS idx_evidence_factor ON evidence(factor_id);
CREATE INDEX IF NOT EXISTS idx_evidence_first_seen ON evidence(first_seen_at);

-- Per (stock, date) quantitative result. gate_inputs_json freezes reproducibility.
-- close/volume are the raw adjusted price inputs, stored so portfolio valuation and
-- price charts never need a network round-trip (and so a valuation is reproducible
-- from the row alone, same guarantee the gate already has).
CREATE TABLE IF NOT EXISTS daily_metric (
    stock_id        INTEGER NOT NULL REFERENCES stock(id),
    date            TEXT NOT NULL,   -- ISO trading date
    ret             REAL,
    index_ret       REAL,
    sigma60         REAL,
    beta60          REAL,
    sigma_idio      REAL,
    idio_ret        REAL,
    vol_zscore      REAL,
    close           REAL,            -- adjusted close on this date
    volume          REAL,
    gate_result     TEXT NOT NULL,
    gate_inputs_json TEXT NOT NULL,
    PRIMARY KEY (stock_id, date)
);

-- Portfolio positions. Deliberately separate from watchlist_item: a watchlist is
-- what you TRACK, a holding is what you OWN, and most users want both.
-- avg_cost is the per-share buy price; qty * avg_cost is the invested amount.
-- No transaction ledger in v1 -- positions are stated, not derived from trades.
CREATE TABLE IF NOT EXISTS holding (
    id         INTEGER PRIMARY KEY,
    user_id    TEXT NOT NULL DEFAULT 'default',
    stock_id   INTEGER NOT NULL REFERENCES stock(id),
    qty        REAL NOT NULL,
    avg_cost   REAL NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (user_id, stock_id)
);
CREATE INDEX IF NOT EXISTS idx_holding_user ON holding(user_id);

CREATE TABLE IF NOT EXISTS attribution (
    id                INTEGER PRIMARY KEY,
    stock_id          INTEGER NOT NULL REFERENCES stock(id),
    date              TEXT NOT NULL,
    trigger           TEXT NOT NULL CHECK (trigger IN ('move', 'event')),
    gate_snapshot_json TEXT,
    outcome           TEXT NOT NULL CHECK (outcome IN
                        ('NOISE','MARKET','MIXED','ATTRIBUTED','NO_DRIVER',
                         'EVENT_NO_MOVE','PENDING_ATTRIBUTION','DATA_ISSUE')),
    rendered_text     TEXT,
    bundle_json       TEXT,          -- persisted frozen bundle for INVESTIGATE/MIXED
    created_at        TEXT NOT NULL,
    model_version     TEXT,
    verifier_log_json TEXT,
    UNIQUE (stock_id, date, trigger)
);

-- Phase 3: per-user alert delivery log. UNIQUE(user_id, attribution_id) is the
-- at-most-once dedupe key -- an EOD rerun can never double-send.
CREATE TABLE IF NOT EXISTS alert (
    id              INTEGER PRIMARY KEY,
    user_id         TEXT NOT NULL,
    stock_id        INTEGER NOT NULL REFERENCES stock(id),
    date            TEXT NOT NULL,
    attribution_id  INTEGER NOT NULL REFERENCES attribution(id),
    outcome         TEXT NOT NULL,
    sent_at         TEXT,
    delivery_status TEXT NOT NULL DEFAULT 'pending'
                      CHECK (delivery_status IN ('pending', 'sent', 'failed')),
    error_text      TEXT,
    UNIQUE (user_id, attribution_id)
);
CREATE INDEX IF NOT EXISTS idx_alert_date ON alert(date);

-- Phase 3: one row per EOD run attempt (idempotency + operational visibility).
CREATE TABLE IF NOT EXISTS run_log (
    id           INTEGER PRIMARY KEY,
    date         TEXT NOT NULL,
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    summary_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_run_log_date ON run_log(date);

-- --------------------------------------------------------------------------
-- Security master + reference data (the browsable universe).
--
-- `stock` stays what it always was: a name this app ANALYSES, with prices, gate
-- rows and an exposure profile. `security` is the far larger catalogue of what
-- EXISTS on the exchanges -- ~2.4k NSE symbols and ~4.9k BSE scrips -- that a user
-- can search through before deciding to track anything. Keeping them separate is
-- what stops the EOD job from trying to price 7,000 names every evening.
--
-- ISIN is the primary key because it is the only identifier both exchanges agree
-- on. That join is also how `scrip_bse` gets filled: a scrip code derived from a
-- matching ISIN is verified by construction, which is strictly better than the
-- hand-maintained data/bse_scrip_map.yaml it supersedes (a wrong code silently
-- attaches another company's filings to a stock -- see CLAUDE.md).
CREATE TABLE IF NOT EXISTS security (
    isin         TEXT PRIMARY KEY,
    symbol_nse   TEXT,             -- NULL for BSE-only scrips
    scrip_bse    TEXT,             -- NULL for NSE-only symbols
    name         TEXT NOT NULL,
    series       TEXT,             -- NSE series (EQ, BE, ...)
    bse_group    TEXT,             -- BSE group (A, B, T, ...)
    industry     TEXT,             -- BSE-reported industry, nullable
    face_value   REAL,
    listing_date TEXT,             -- ISO, from NSE
    market_cap   REAL,             -- BSE-reported, in Rs crore; indicative only
    exchanges    TEXT NOT NULL,    -- 'NSE' | 'BSE' | 'NSE,BSE'
    status       TEXT NOT NULL DEFAULT 'Active',
    stock_id     INTEGER REFERENCES stock(id),  -- set once promoted to a tracked stock
    synced_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_security_symbol ON security(symbol_nse);
CREATE INDEX IF NOT EXISTS idx_security_scrip ON security(scrip_bse);
CREATE INDEX IF NOT EXISTS idx_security_stock ON security(stock_id);
CREATE INDEX IF NOT EXISTS idx_security_name ON security(name);

-- Cached third-party reference payloads (fundamentals, company profile, quotes).
--
-- One row per (stock, kind). Deliberately a JSON blob rather than 40 typed columns:
-- the upstream shapes are outside our control and change without notice, and none of
-- this data feeds the gate or the attribution bundle -- it is display-only. Typing it
-- would buy nothing and break on every upstream field rename.
--
-- `fetched_at` drives TTL expiry; `source` records provenance so the UI can attribute
-- a number to whoever actually reported it.
CREATE TABLE IF NOT EXISTS reference_data (
    stock_id   INTEGER NOT NULL REFERENCES stock(id),
    kind       TEXT NOT NULL CHECK (kind IN
                 ('key_stats', 'financials', 'profile', 'shareholding', 'quote')),
    payload_json TEXT NOT NULL,
    source     TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (stock_id, kind)
);

-- Market-wide cached payloads (index levels, top movers). Same idea as
-- reference_data but not keyed to a stock -- these describe the whole market.
CREATE TABLE IF NOT EXISTS market_data (
    kind         TEXT PRIMARY KEY CHECK (kind IN ('indices', 'movers')),
    payload_json TEXT NOT NULL,
    source       TEXT NOT NULL,
    fetched_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS driver (
    id                    INTEGER PRIMARY KEY,
    attribution_id        INTEGER NOT NULL REFERENCES attribution(id),
    rank                  INTEGER,
    factor_id             TEXT REFERENCES factor(id),   -- nullable
    evidence_ids          TEXT NOT NULL DEFAULT '[]',   -- JSON array
    chain_text            TEXT,
    direction             TEXT,
    confidence            TEXT CHECK (confidence IN ('HIGH','MEDIUM','LOW')),
    confidence_reason     TEXT,   -- the rubric's plain-language reason (persisted for the UI)
    agent_confidence_claim TEXT,
    verifier_status       TEXT CHECK (verifier_status IN ('passed','stripped','demoted'))
);
