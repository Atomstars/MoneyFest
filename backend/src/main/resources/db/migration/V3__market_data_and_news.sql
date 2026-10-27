ALTER TABLE stock ADD COLUMN exchange VARCHAR(8) NOT NULL DEFAULT 'NSE';
ALTER TABLE stock ADD COLUMN symbol VARCHAR(30);
ALTER TABLE stock ADD COLUMN isin VARCHAR(20);
ALTER TABLE stock ADD COLUMN provider_symbol VARCHAR(40);
ALTER TABLE stock ADD COLUMN catalog_at TIMESTAMPTZ;
UPDATE stock SET symbol=ticker, provider_symbol=ticker||'.NS';
CREATE TABLE market_sync (
 scope VARCHAR(50) PRIMARY KEY,
 attempted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 succeeded_at TIMESTAMPTZ,
 status VARCHAR(20) NOT NULL,
 detail VARCHAR(250)
);
CREATE TABLE news_item (
 id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 stock_id BIGINT NOT NULL REFERENCES stock(id),
 headline TEXT NOT NULL,
 summary TEXT NOT NULL,
 url TEXT NOT NULL,
 source VARCHAR(200) NOT NULL,
 published_at TIMESTAMPTZ NOT NULL,
 fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 sentiment VARCHAR(12) NOT NULL CHECK(sentiment IN ('POSITIVE','NEGATIVE','MIXED','NEUTRAL')),
 fingerprint VARCHAR(64) NOT NULL,
 UNIQUE(stock_id,fingerprint)
);
CREATE INDEX news_stock_date ON news_item(stock_id,published_at DESC);
CREATE TABLE news_read (
 user_id BIGINT NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
 news_id BIGINT NOT NULL REFERENCES news_item(id) ON DELETE CASCADE,
 read_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(user_id,news_id)
);
