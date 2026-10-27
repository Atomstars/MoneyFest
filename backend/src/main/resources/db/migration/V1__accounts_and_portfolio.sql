CREATE TABLE app_user (
 id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 email VARCHAR(254) NOT NULL UNIQUE,
 password_hash VARCHAR(100) NOT NULL,
 display_name VARCHAR(80) NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE stock (
 id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 ticker VARCHAR(30) NOT NULL UNIQUE,
 name VARCHAR(160) NOT NULL,
 sector VARCHAR(80)
);
CREATE TABLE position (
 user_id BIGINT NOT NULL REFERENCES app_user(id),
 stock_id BIGINT NOT NULL REFERENCES stock(id),
 qty NUMERIC(20,6) NOT NULL CHECK(qty > 0),
 avg_cost NUMERIC(20,6) NOT NULL CHECK(avg_cost >= 0),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(user_id, stock_id)
);
CREATE TABLE watchlist_item (
 user_id BIGINT NOT NULL REFERENCES app_user(id),
 stock_id BIGINT NOT NULL REFERENCES stock(id),
 PRIMARY KEY(user_id, stock_id)
);
CREATE TABLE user_preferences (
 user_id BIGINT PRIMARY KEY REFERENCES app_user(id),
 alert_level VARCHAR(20) NOT NULL DEFAULT 'ALL' CHECK(alert_level IN ('ALL','EXPLAINED_ONLY','HIGH_ONLY')),
 quiet_market BOOLEAN NOT NULL DEFAULT false,
 daily_digest BOOLEAN NOT NULL DEFAULT false
);
CREATE TABLE price_bar (
 stock_id BIGINT NOT NULL REFERENCES stock(id),
 date DATE NOT NULL,
 close NUMERIC(20,6) NOT NULL CHECK(close > 0),
 source VARCHAR(80) NOT NULL,
 PRIMARY KEY(stock_id,date)
);
CREATE TABLE assessment (
 stock_id BIGINT NOT NULL REFERENCES stock(id),
 date DATE NOT NULL,
 outcome VARCHAR(40) NOT NULL,
 rendered_text TEXT NOT NULL,
 drivers JSONB NOT NULL DEFAULT '[]',
 evidence JSONB NOT NULL DEFAULT '[]',
 PRIMARY KEY(stock_id,date)
);
-- Catalog only: no fabricated quotes or explanations in a fresh installation.
INSERT INTO stock(ticker,name,sector) VALUES
 ('TCS','Tata Consultancy Services','IT_SERVICES'),
 ('INFY','Infosys','IT_SERVICES'),
 ('HDFCBANK','HDFC Bank','BANKS_PRIVATE'),
 ('ICICIBANK','ICICI Bank','BANKS_PRIVATE'),
 ('SBIN','State Bank of India','BANKS_PSU'),
 ('RELIANCE','Reliance Industries',NULL),
 ('ASIANPAINT','Asian Paints','PAINTS'),
 ('ONGC','Oil and Natural Gas Corporation','UPSTREAM_OIL'),
 ('MARUTI','Maruti Suzuki India','AUTOS'),
 ('SUNPHARMA','Sun Pharmaceutical Industries','PHARMA');
