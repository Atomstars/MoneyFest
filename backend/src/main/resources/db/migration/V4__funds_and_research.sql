CREATE TABLE fund_scheme (
  code VARCHAR(20) PRIMARY KEY,
  name VARCHAR(240) NOT NULL,
  plan VARCHAR(80) NOT NULL,
  option_name VARCHAR(80) NOT NULL,
  category VARCHAR(180) NOT NULL,
  amc VARCHAR(160) NOT NULL,
  isin VARCHAR(20),
  active BOOLEAN NOT NULL DEFAULT true,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX fund_scheme_search ON fund_scheme USING gin(to_tsvector('english',name||' '||amc||' '||category));
CREATE TABLE fund_nav (
  code VARCHAR(20) NOT NULL REFERENCES fund_scheme(code),
  date DATE NOT NULL,
  nav NUMERIC(20,6) NOT NULL CHECK(nav>0),
  PRIMARY KEY(code,date)
);
CREATE TABLE fund_position (
  user_id BIGINT NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
  code VARCHAR(20) NOT NULL REFERENCES fund_scheme(code),
  units NUMERIC(20,6) NOT NULL CHECK(units>0),
  avg_nav NUMERIC(20,6) NOT NULL CHECK(avg_nav>=0),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY(user_id,code)
);
CREATE INDEX fund_position_code ON fund_position(code);
CREATE TABLE research_event (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  theme VARCHAR(32) NOT NULL,
  headline TEXT NOT NULL,
  source VARCHAR(200) NOT NULL,
  url TEXT NOT NULL,
  published_at TIMESTAMPTZ NOT NULL,
  sentiment VARCHAR(12) NOT NULL,
  fingerprint VARCHAR(64) NOT NULL,
  UNIQUE(theme,fingerprint)
);
CREATE INDEX research_event_theme_date ON research_event(theme,published_at DESC);
