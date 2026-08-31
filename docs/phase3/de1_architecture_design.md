DE1 — Network Intelligence Architecture Design
Mohammed Marzook
1. Architecture Flow
Daily CSVs (7 files)          milano-grid.geojson
       |                              |
       v                              v
   [Landing]                   [Reference zone]
       |                       (loaded once, not
       v                        daily-refreshed;
   [Raw]                        never re-ingested
   CSV, unchanged format,       on a schedule)
   basic validation only              |
       |                              |
       v                              |
   [Spark: clean, aggregate,  <-------+
    enrich with geometry]
       |
       v
   [Processed]  (Parquet, partitioned by date)
       |
       v
   [Analytics]  (SQL warehouse: hourly_grid_summary,
                 daily_grid_summary, hotspots, alerts)
       |
       +----------------+------------------+
       v                v                  v
   [FastAPI]        [ML models]      [Airflow]
   serves data      predict/detect    schedules and
   to consumers     patterns          tracks every step,
       |                              records success/
       +---------+                    failure per run
       v         v
   [React]   [Claude assistant]
   dashboard  explains results
   for humans in plain language

milano-grid.geojson enters through a separate reference zone, not through the daily landing/raw path — it is loaded once and reused, not re-validated or re-ingested every day the way the CSVs are.

2. Layer-to-Tool Mapping
Layer	File format	Tool that writes it	Tool that reads it
Landing	CSV (as-arrived)	External source drops the file	Ingestion check (DE2)
Raw	CSV (unchanged)	Ingestion script, after validation	Spark
Reference	GeoJSON (static)	Loaded once, not written by the pipeline	Spark (enrich step)
Processed	Parquet, partitioned by date	Spark	Spark, SQL loader
Analytics	SQL tables (warehouse)	SQL, loaded from Processed	FastAPI, React, ML

Raw stays as CSV (same format as arrival) because real transformation is Spark's job, which happens after raw, not before — raw only needs to prove the file is structurally valid, not already be reshaped.

3. Quality Gates

Gate 1 — before landing → raw acceptance:

All 7 expected daily files are present (file-completeness check).
Each file has the expected columns (datetime, CellID, countrycode, smsin, smsout, callin, callout, internet).
No row has a missing grid_id or timestamp, or a negative activity value (this is SP2's clean() rejection logic, applied as the formal raw-acceptance gate).

Gate 2 — before processed → analytics publication:

Zero duplicate (grid_id, timestamp) pairs after aggregation — SP3's mandatory duplicate assertion. The job halts entirely if this fails; nothing partial gets published.
Row-count accounting must reconcile: output rows = input rows − rejected rows (the same assertion built into SP2/SP7).
4. Analytics Outputs
hourly_grid_summary: one row per grid_id + hour, built by Spark (SP3/SP6/SP7), stored in the SQL analytics warehouse. Consumed by FastAPI and dashboards for hour-level views.
daily_grid_summary: one row per grid_id + day, a rollup of hourly_grid_summary computed in the warehouse layer (SQL), built new in DE6. Consumed by daily-trend dashboards.
hotspots: top-N highest-activity grids per day, derived from hourly_grid_summary/daily_grid_summary, stored as a small dedicated analytics table. Consumed by the map view in React.
alert / risk tables: NP3's rule-based alerts (HIGH_ACTIVITY, ACTIVITY_SPIKE, ACTIVITY_DROP), formally placed in the analytics warehouse alongside the summary tables (not left as loose CSV output as in Phase 1) so FastAPI and the Claude assistant can query them the same way as any other analytics table.
5. Tool Responsibilities (one sentence each, zero overlap)
Spark: cleans, aggregates, and enriches the data — the only tool that calculates.
Airflow: schedules and triggers the Spark job on a schedule, and records whether each run succeeded or failed — never touches the data itself.
SQL: stores the finished analytics tables in a queryable format for fast lookup — never recalculates anything Spark already calculated.
FastAPI: serves the already-calculated analytics data to other applications — never calculates anything itself.
React: displays data to a human in a browser (charts, dashboards) — never calculates or stores data.
ML: predicts/detects patterns (e.g. anomaly detection) on top of the analytics data — an additional layer added later, not a replacement for Spark's cleaning/aggregation.
Claude (assistant): answers questions about the data and explains results in plain language to a person — never calculates the underlying numbers itself.
6. Assumptions & Non-Goals

Assumptions:

Exactly one daily CSV file arrives per day, matching the sms-call-internet-mi-*.csv naming pattern already used throughout Phase 1/2.
milano-grid.geojson is stable and does not change — it is loaded once as reference data, not re-validated on every pipeline run.
Historical backfill (all 7 existing files) is available upfront for initial development and testing, separate from the ongoing daily arrival of new files.
The pipeline runs on a daily batch schedule, not in real time.

Non-goals:

We do not have capacity, throughput, or utilization data.
This project does not support real-time/streaming ingestion — all processing is daily batch, consistent with Phase 2's Spark design.
This project does not support multiple cities — the grid, schema, and business logic are specific to the Milan dataset.
This project does not implement user authentication or multi-tenant access control in the API/dashboard layer at this stage.
7. Where Pipeline Health Is Recorded

Airflow is the single source of truth for pipeline health: every DAG run records success/failure status, timestamps, and (in DE7/DE8) task-level logs for each step (ingest, validate, Spark job, warehouse load). This is the exact data source that API6 (a later lab) exposes to the outside world — a "pipeline health" endpoint reads directly from Airflow's own run history rather than needing a separate, duplicate tracking system.