CREATE TABLE fund_return_snapshot (
 code varchar(20) PRIMARY KEY REFERENCES fund_scheme(code),
 nav_date date NOT NULL,
 nav numeric(20,6) NOT NULL CHECK(nav > 0),
 return_1y double precision,
 return_3y double precision,
 return_5y double precision,
 anchor_1y date,
 anchor_3y date,
 anchor_5y date,
 updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE VIEW fund_discovery_scheme AS
SELECT f.*, CASE
 WHEN lower(category) LIKE '%index%' OR lower(category) LIKE '% etf%' THEN 'index'
 WHEN lower(category) LIKE '%large%mid%' THEN 'large-mid'
 WHEN lower(category) LIKE '%large cap%' THEN 'large'
 WHEN lower(category) LIKE '%mid cap%' THEN 'mid'
 WHEN lower(category) LIKE '%small cap%' THEN 'small'
 WHEN lower(category) LIKE '%flexi cap%' THEN 'flexi'
 WHEN lower(category) LIKE '%multi cap%' THEN 'multi'
 WHEN lower(category) LIKE '%elss%' THEN 'elss'
 WHEN lower(category) LIKE '%hybrid%' OR lower(category) LIKE '%balanced%' OR lower(category) LIKE '%arbitrage%' OR lower(category) LIKE '%equity savings%' THEN 'hybrid'
 WHEN lower(category) LIKE '%debt%' OR lower(category) LIKE '%income%' OR lower(category) LIKE '%liquid%' OR lower(category) LIKE '%money market%' OR lower(category) LIKE '%gilt%' OR lower(category) LIKE '%overnight%' THEN 'debt'
 WHEN lower(category) LIKE '%sector%' OR lower(category) LIKE '%thematic%' THEN 'sector'
 ELSE 'other' END AS group_id
FROM fund_scheme f;
