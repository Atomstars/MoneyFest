ALTER TABLE stock ADD COLUMN currency VARCHAR(3) NOT NULL DEFAULT 'INR' CHECK(currency IN ('INR','USD'));
CREATE INDEX stock_currency_symbol ON stock(currency,symbol);

-- A small discoverable starting catalog. Official directory sync expands this;
-- no prices or news are seeded.
INSERT INTO stock(ticker,symbol,name,sector,exchange,currency,provider_symbol) VALUES
('AAPL.US','AAPL','Apple Inc.','Technology','NASDAQ','USD','AAPL'),
('MSFT.US','MSFT','Microsoft Corporation','Technology','NASDAQ','USD','MSFT'),
('NVDA.US','NVDA','NVIDIA Corporation','Semiconductors','NASDAQ','USD','NVDA'),
('AMZN.US','AMZN','Amazon.com Inc.','Consumer discretionary','NASDAQ','USD','AMZN'),
('GOOGL.US','GOOGL','Alphabet Inc.','Communication services','NASDAQ','USD','GOOGL'),
('META.US','META','Meta Platforms Inc.','Communication services','NASDAQ','USD','META'),
('TSLA.US','TSLA','Tesla Inc.','Consumer discretionary','NASDAQ','USD','TSLA'),
('JPM.US','JPM','JPMorgan Chase & Co.','Financials','NYSE','USD','JPM'),
('V.US','V','Visa Inc.','Financials','NYSE','USD','V'),
('JNJ.US','JNJ','Johnson & Johnson','Healthcare','NYSE','USD','JNJ'),
('XOM.US','XOM','Exxon Mobil Corporation','Energy','NYSE','USD','XOM'),
('KO.US','KO','The Coca-Cola Company','Consumer staples','NYSE','USD','KO')
ON CONFLICT(ticker) DO NOTHING;

CREATE TABLE portfolio_plan (
 user_id BIGINT PRIMARY KEY REFERENCES app_user(id) ON DELETE CASCADE,
 currency VARCHAR(3) NOT NULL CHECK(currency IN ('INR','USD')),
 risk VARCHAR(12) NOT NULL CHECK(risk IN ('CAUTIOUS','BALANCED','GROWTH')),
 horizon_years INTEGER NOT NULL CHECK(horizon_years BETWEEN 1 AND 40),
 budget NUMERIC(20,2) NOT NULL CHECK(budget > 0),
 allocations JSONB NOT NULL,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
