DDL = """
CREATE TABLE IF NOT EXISTS global_settings (
    key   TEXT PRIMARY KEY,
    value REAL
);

CREATE TABLE IF NOT EXISTS companies (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    name                 TEXT UNIQUE NOT NULL COLLATE NOCASE,
    entry_fee            REAL,
    free_days            INTEGER,
    storage_rate         REAL,
    storage_period_days  INTEGER,
    created_at           TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS containers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    number          TEXT UNIQUE NOT NULL,
    display_number  TEXT NOT NULL,
    company_id      INTEGER REFERENCES companies(id) ON DELETE SET NULL,
    type            TEXT,
    status          TEXT NOT NULL DEFAULT 'on_terminal'
                    CHECK (status IN ('in_transit', 'on_terminal', 'departed')),
    registered_at   TEXT NOT NULL DEFAULT (datetime('now')),
    arrival_date    TEXT,
    departure_date  TEXT
);

CREATE INDEX IF NOT EXISTS idx_containers_status ON containers(status);
CREATE INDEX IF NOT EXISTS idx_containers_company ON containers(company_id);
-- arrival_date / departure_date — ORDER BY в list_active, list_departed,
-- active_for_company, all_for_company. Без индекса = full table scan.
CREATE INDEX IF NOT EXISTS idx_containers_arrival_date ON containers(arrival_date);
CREATE INDEX IF NOT EXISTS idx_containers_departure_date ON containers(departure_date);
-- type — WHERE в active_by_type (поиск контейнеров по типу).
CREATE INDEX IF NOT EXISTS idx_containers_type ON containers(type);

CREATE TABLE IF NOT EXISTS users (
    tg_id      INTEGER PRIMARY KEY,
    username   TEXT,
    full_name  TEXT,
    role       TEXT NOT NULL DEFAULT 'none'
               CHECK (role IN ('full', 'operator', 'reports_only', 'none')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""
