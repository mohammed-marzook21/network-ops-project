-- DE6 - Warehouse Modelling for Network Analytics
-- Phase 3, Network Operations Predictive Intelligence Project
--
-- Star schema: fact_network_activity references dim_grid and dim_time.
-- Geometry lives ONLY in dim_grid, referenced once, never repeated
-- into the fact table.

PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS fact_network_activity;
DROP TABLE IF EXISTS dim_grid;
DROP TABLE IF EXISTS dim_time;

-- ── dim_grid ─────────────────────────────────────────────────────────
-- One row per grid cell. Populated ONCE from the static Milan reference
-- (milano-grid.geojson), not once per hourly activity record.
CREATE TABLE dim_grid (
    grid_id         INTEGER PRIMARY KEY,
    centroid_lat    REAL,
    centroid_lon    REAL,
    geometry_json   TEXT  -- reference to the full polygon, stored ONCE here
);

-- ── dim_time ─────────────────────────────────────────────────────────
-- One row per distinct hour observed in the data. time_key is a
-- readable surrogate key (YYYYMMDDHH), not the raw timestamp itself.
CREATE TABLE dim_time (
    time_key        INTEGER PRIMARY KEY,  -- e.g. 2013110800
    ts              TEXT NOT NULL,        -- ISO timestamp
    date            TEXT NOT NULL,        -- YYYY-MM-DD
    hour            INTEGER NOT NULL,
    day_of_week     TEXT NOT NULL
);

-- ── fact_network_activity ───────────────────────────────────────────
-- One row per (grid_id, time_key). NO geometry column here at all --
-- geometry belongs to dim_grid; the fact table only ever holds keys
-- and measures.
CREATE TABLE fact_network_activity (
    grid_id             INTEGER NOT NULL,
    time_key            INTEGER NOT NULL,
    sms_in              REAL,
    sms_out             REAL,
    call_in             REAL,
    call_out            REAL,
    internet_activity   REAL,
    total_sms           REAL,
    total_calls         REAL,
    total_activity      REAL,
    PRIMARY KEY (grid_id, time_key),
    FOREIGN KEY (grid_id) REFERENCES dim_grid(grid_id),
    FOREIGN KEY (time_key) REFERENCES dim_time(time_key)
);

-- ── Indexes on columns actually used for filtering/joining ──────────
-- fact's PRIMARY KEY (grid_id, time_key) already creates an implicit
-- composite index. Add a standalone index on time_key alone, since
-- "hourly trend" and "date range" queries filter by time WITHOUT
-- always also filtering by grid_id -- the composite PK index can't
-- efficiently serve a time-only lookup.
CREATE INDEX idx_fact_time_key ON fact_network_activity(time_key);

-- dim_time.date is used heavily for date-range filtering (e.g. "all
-- activity on 2013-11-01"), separate from hour-level lookups.
CREATE INDEX idx_dim_time_date ON dim_time(date);
