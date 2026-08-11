-- Axiomra schema v1
-- Point-in-time correct: predictions, decisions and outcomes are immutable.

CREATE TABLE IF NOT EXISTS instruments (
    symbol TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    exchange TEXT NOT NULL DEFAULT 'NSE',
    sector TEXT,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    listed_at DATE
);

CREATE TABLE IF NOT EXISTS market_bars (
    symbol TEXT NOT NULL REFERENCES instruments(symbol),
    ts TIMESTAMPTZ NOT NULL,
    open DOUBLE PRECISION NOT NULL,
    high DOUBLE PRECISION NOT NULL,
    low DOUBLE PRECISION NOT NULL,
    close DOUBLE PRECISION NOT NULL,
    volume DOUBLE PRECISION NOT NULL,
    adjusted BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (symbol, ts)
);

CREATE TABLE IF NOT EXISTS fundamentals (
    symbol TEXT NOT NULL REFERENCES instruments(symbol),
    as_of DATE NOT NULL,
    field TEXT NOT NULL,
    value DOUBLE PRECISION,
    PRIMARY KEY (symbol, field, as_of)
);

CREATE TABLE IF NOT EXISTS news_events (
    id UUID PRIMARY KEY,
    symbol TEXT NOT NULL REFERENCES instruments(symbol),
    ts TIMESTAMPTZ NOT NULL,
    headline TEXT NOT NULL,
    source TEXT,
    score DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS features (
    symbol TEXT NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    feature_version TEXT NOT NULL,
    values JSONB NOT NULL,
    PRIMARY KEY (symbol, ts, feature_version)
);

CREATE TABLE IF NOT EXISTS model_versions (
    id UUID PRIMARY KEY,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS predictions (
    id UUID PRIMARY KEY,
    symbol TEXT NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    score DOUBLE PRECISION NOT NULL,
    confidence DOUBLE PRECISION,
    expected_return DOUBLE PRECISION,
    data_version TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS market_regimes (
    ts TIMESTAMPTZ PRIMARY KEY,
    regime TEXT NOT NULL,
    confidence DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS decisions (
    id UUID PRIMARY KEY,
    symbol TEXT NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    quant_score DOUBLE PRECISION,
    technical_score DOUBLE PRECISION,
    fundamental_score DOUBLE PRECISION,
    news_score DOUBLE PRECISION,
    combined_score DOUBLE PRECISION NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    regime TEXT,
    proposed_action TEXT NOT NULL,
    risk_status TEXT,
    risk_reasons JSONB,
    model_versions JSONB,
    prompt_versions JSONB,
    data_version TEXT,
    feature_version TEXT,
    evidence JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY,
    decision_id UUID REFERENCES decisions(id),
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    requested_quantity INTEGER NOT NULL,
    order_type TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fills (
    id UUID PRIMARY KEY,
    order_id UUID REFERENCES orders(id),
    quantity INTEGER NOT NULL,
    price DOUBLE PRECISION NOT NULL,
    filled_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS trade_outcomes (
    id UUID PRIMARY KEY,
    decision_id UUID REFERENCES decisions(id),
    return_pct DOUBLE PRECISION,
    max_adverse_excursion DOUBLE PRECISION,
    max_favorable_excursion DOUBLE PRECISION,
    holding_hours DOUBLE PRECISION,
    closed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS experiments (
    id UUID PRIMARY KEY,
    hypothesis TEXT NOT NULL,
    baseline_model TEXT,
    candidate_model TEXT,
    train_period TEXT,
    validation_period TEXT,
    test_period TEXT,
    metrics JSONB,
    status TEXT NOT NULL DEFAULT 'PROPOSED',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_decisions_symbol ON decisions(symbol);
CREATE INDEX IF NOT EXISTS idx_decisions_ts ON decisions(ts);
CREATE INDEX IF NOT EXISTS idx_predictions_symbol_ts ON predictions(symbol, ts);
