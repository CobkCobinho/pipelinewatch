PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS components (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    family TEXT NOT NULL,
    nominal_voltage REAL NOT NULL CHECK(nominal_voltage > 0)
);
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    event_date TEXT NOT NULL,
    created_at TEXT NOT NULL,
    pipeline_name TEXT NOT NULL,
    component_family TEXT NOT NULL,
    plant TEXT NOT NULL,
    scenario TEXT NOT NULL,
    seed INTEGER NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('Sucesso','Alerta','Falha')),
    input_rows INTEGER NOT NULL CHECK(input_rows >= 0),
    accepted_rows INTEGER NOT NULL CHECK(accepted_rows >= 0),
    rejected_rows INTEGER NOT NULL CHECK(rejected_rows >= 0),
    error_count INTEGER NOT NULL CHECK(error_count >= 0),
    duration_ms REAL NOT NULL CHECK(duration_ms >= 0),
    measured_ms REAL NOT NULL CHECK(measured_ms >= 0),
    CHECK(input_rows = accepted_rows + rejected_rows)
);
CREATE TABLE IF NOT EXISTS accepted_records (
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    record_id TEXT NOT NULL,
    component_code TEXT NOT NULL REFERENCES components(code),
    supplier TEXT NOT NULL,
    lot TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK(quantity > 0),
    voltage_v REAL NOT NULL,
    temperature_c REAL NOT NULL,
    inspection_date TEXT NOT NULL,
    PRIMARY KEY(run_id, record_id)
);
CREATE TABLE IF NOT EXISTS rejected_records (
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    row_number INTEGER NOT NULL,
    record_id TEXT,
    payload TEXT NOT NULL,
    PRIMARY KEY(run_id, row_number)
);
CREATE TABLE IF NOT EXISTS quality_errors (
    error_id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    row_number INTEGER,
    record_id TEXT,
    rule_name TEXT NOT NULL,
    field TEXT NOT NULL,
    message TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS stage_events (
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    stage_name TEXT NOT NULL,
    stage_index INTEGER NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('Sucesso','Alerta','Falha','Ignorada')),
    input_rows INTEGER NOT NULL,
    output_rows INTEGER NOT NULL,
    rejected_rows INTEGER NOT NULL,
    duration_ms REAL NOT NULL,
    PRIMARY KEY(run_id, stage_name)
);
CREATE INDEX IF NOT EXISTS idx_runs_date ON runs(event_date);
CREATE INDEX IF NOT EXISTS idx_errors_run ON quality_errors(run_id);
CREATE VIEW IF NOT EXISTS v_runs AS
SELECT *, CASE WHEN input_rows > 0 THEN ROUND(100.0 * accepted_rows / input_rows, 2)
               ELSE NULL END AS quality_pct
FROM runs;
CREATE VIEW IF NOT EXISTS v_events AS
SELECT e.*, r.event_date, r.pipeline_name, r.component_family, r.plant, r.status AS run_status
FROM stage_events e JOIN runs r USING(run_id);
CREATE VIEW IF NOT EXISTS v_errors AS
SELECT e.*, r.event_date, r.pipeline_name, r.component_family, r.plant, r.status AS run_status
FROM quality_errors e JOIN runs r USING(run_id);
CREATE VIEW IF NOT EXISTS v_daily AS
SELECT event_date, COUNT(*) AS executions, SUM(input_rows) AS input_rows,
       SUM(accepted_rows) AS accepted_rows, SUM(rejected_rows) AS rejected_rows,
       SUM(status = 'Falha') AS failed_runs, ROUND(AVG(duration_ms), 2) AS avg_duration_ms
FROM runs GROUP BY event_date;
