# DE7 — End-to-End Airflow Orchestration: Troubleshooting Map

## 1. Purpose

This document provides the troubleshooting map and operational runbook for the DE7 End-to-End Airflow pipeline.

The pipeline automates the following batch workflow:

**Ingestion → Validation → Spark Processing → Warehouse Load → Quality Check → Notification**

The objective is to provide clear ownership for each failure type, recovery steps, validation evidence, and rerun behavior.

---

## 2. Pipeline Architecture

```text
Daily CSV File
     │
     ▼
data/landing/
     │
     ▼
┌──────────────┐
│    ingest    │
│ ingestion.py │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   validate   │
│    DE7 DAG   │
└──────┬───────┘
       │
       ▼
data/raw/
       │
       ▼
┌─────────────────────┐
│   spark_process     │
│ telecom_pipeline.py │
└──────────┬──────────┘
           │
           ▼
data/phase3_output/
           │
           ▼
┌─────────────────────┐
│   load_warehouse    │
│  load_warehouse.py  │
└──────────┬──────────┘
           │
           ▼
warehouse/network_analytics.db
           │
           ▼
┌─────────────────────┐
│    quality_check    │
│       DE7 DAG       │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│       notify        │
│       DE7 DAG       │
└─────────────────────┘
```

---

## 3. Main Components

| Component        | Location                                        | Responsibility                                                    |
| ---------------- | ----------------------------------------------- | ----------------------------------------------------------------- |
| Airflow DAG      | `airflow/dags/de7_full_pipeline.py`             | Orchestrates the complete pipeline                                |
| Ingestion        | `ingestion/ingestion.py`                        | Detects, validates, routes, and audits daily files                |
| Spark pipeline   | `spark/telecom_pipeline.py`                     | Cleans, transforms, aggregates, enriches, and publishes analytics |
| Warehouse loader | `warehouse/load_warehouse.py`                   | Loads analytics into SQLite warehouse                             |
| Warehouse        | `warehouse/network_analytics.db`                | Stores published network activity                                 |
| Reference data   | `data/reference/milano-grid.geojson`            | Static geospatial reference input                                 |
| Pipeline status  | `data/pipeline_status/de7_pipeline_status.json` | Machine-readable run status                                       |
| Ingestion audit  | `logs/ingestion_log.jsonl`                      | File-level ingestion audit                                        |
| Notification log | `logs/de7_notification.log`                     | Pipeline success/failure notification                             |

---

## 4. Troubleshooting Map

### 4.1 Ingestion Failure

**Responsible module:**

```text
ingestion/ingestion.py
```

**Symptoms:**

* No files detected.
* File rejected.
* Required column missing.
* Invalid or poor-quality data.
* File unexpectedly treated as a duplicate.

**Checks:**

```bash
ls -lh data/landing/
```

Check detected files:

```bash
python -c "from ingestion.ingestion import detect_files; print(detect_files('data/landing'))"
```

Check the ingestion audit:

```bash
tail -20 logs/ingestion_log.jsonl
```

**Important behavior:**

Previously accepted files are treated as duplicates.

Previously rejected files are allowed to be reprocessed after correction.

This allows a corrected file with the same filename to successfully enter the pipeline.

---

## 5. Validation Failure

**Responsible module:**

```text
airflow/dags/de7_full_pipeline.py
```

The `validate` task checks the results produced by ingestion.

A rejected input causes validation to fail so that invalid data does not proceed to Spark processing.

**Check:**

```bash
airflow tasks states-for-dag-run de7_full_pipeline <RUN_ID>
```

Also inspect:

```bash
tail -20 logs/ingestion_log.jsonl
```

---

## 6. Spark Processing Failure

**Responsible module:**

```text
spark/telecom_pipeline.py
```

**Possible causes:**

* Missing raw input.
* Invalid input data.
* Spark/Python/Java environment issue.
* Missing reference data.
* Transformation or aggregation error.
* Analytics output not generated.

**Checks:**

```bash
ls -lh data/raw/
```

Check analytics:

```bash
ls -lh data/phase3_output/analytics/hourly_grid_summary/
```

Check Spark metrics:

```bash
cat data/phase3_output/spark_metrics.json
```

The Spark stage must successfully produce the analytics output before warehouse loading proceeds.

---

## 7. Warehouse Load Failure

**Responsible module:**

```text
warehouse/load_warehouse.py
```

**Possible causes:**

* Analytics Parquet file missing.
* Incorrect schema.
* Invalid or duplicate grain.
* SQLite database problem.
* File permission problem.

**Checks:**

```bash
ls -lh data/phase3_output/analytics/hourly_grid_summary/
```

Check the warehouse:

```bash
python -c "import sqlite3; c=sqlite3.connect('warehouse/network_analytics.db'); print(c.execute('SELECT COUNT(*) FROM fact_network_activity').fetchone()[0]); c.close()"
```

The warehouse uses the following grain:

```text
(grid_id, timestamp)
```

The loader uses UPSERT behavior so that reruns do not create duplicate records.

---

## 8. Quality Check Failure

**Responsible module:**

```text
airflow/dags/de7_full_pipeline.py
```

The quality check verifies:

* Warehouse exists.
* Warehouse contains data.
* Duplicate grain groups are zero.
* Spark metrics exist.
* Required metrics are present.
* `AS_OF` is available.
* Pipeline status is written.

**Check status file:**

```bash
cat data/pipeline_status/de7_pipeline_status.json
```

**Check warehouse quality:**

```bash
python -c "import sqlite3; c=sqlite3.connect('warehouse/network_analytics.db'); print('Rows:', c.execute('SELECT COUNT(*) FROM fact_network_activity').fetchone()[0]); print('AS_OF:', c.execute('SELECT MAX(timestamp) FROM fact_network_activity').fetchone()[0]); print('Duplicate grain:', c.execute('SELECT COUNT(*) FROM (SELECT grid_id,timestamp FROM fact_network_activity GROUP BY grid_id,timestamp HAVING COUNT(*)>1)').fetchone()[0]); c.close()"
```

Expected duplicate grain:

```text
Duplicate grain: 0
```

---

## 9. Notification Failure

**Responsible module:**

```text
airflow/dags/de7_full_pipeline.py
```

The notification task runs with `ALL_DONE` so that the final pipeline outcome can be recorded even if an upstream task fails.

Notification output is written to:

```text
logs/de7_notification.log
```

Check the latest entries:

```bash
tail -5 logs/de7_notification.log
```

Successful pipeline:

```text
DE7 PIPELINE SUCCESS
```

Failed pipeline:

```text
DE7 PIPELINE FAILURE
```

---

## 10. Airflow DAG Failure

**Responsible module:**

```text
airflow/dags/de7_full_pipeline.py
```

Check DAG import errors:

```bash
airflow dags list-import-errors
```

Compile the DAG:

```bash
python -m py_compile airflow/dags/de7_full_pipeline.py
```

Check scheduler:

```bash
airflow jobs check --job-type SchedulerJob
```

Check DAG runs:

```bash
airflow dags list-runs -d de7_full_pipeline
```

Check individual task states:

```bash
airflow tasks states-for-dag-run de7_full_pipeline <RUN_ID>
```

---

## 11. Static Reference Data

The following file is static reference data:

```text
data/reference/milano-grid.geojson
```

It is used by the Spark geospatial enrichment stage.

It is **not** part of the daily ingestion flow.

Daily ingestion only processes activity files matching:

```text
sms-call-internet-mi-*.csv
```

Therefore the reference GeoJSON is not copied into `data/raw/` during daily ingestion.

---

## 12. Held-Back File Test

A held-back `2013-11-09` activity file was used to verify the complete landing-to-warehouse workflow.

The initial version was rejected because it was missing the required `internet` column.

After correction, the file was placed in:

```text
data/landing/sms-call-internet-mi-2013-11-09.csv
```

The ingestion logic was corrected so that a previously rejected file could be reprocessed.

The corrected file was accepted:

```text
2013-11-09.csv
status: accepted
row_count: 72
```

The complete pipeline then successfully processed the new data.

Final status:

```text
rows_in: 144
rows_rejected: 0
nulls_handled: 0
rows_published: 144
warehouse_rows: 144
duplicate_grain_groups: 0
AS_OF: 2013-11-09 23:00:00
```

This demonstrates:

```text
Held-back file
      ↓
Landing
      ↓
Ingestion
      ↓
Validation
      ↓
Raw
      ↓
Spark
      ↓
Analytics
      ↓
Warehouse
      ↓
Quality Check
      ↓
Notification
```

---

## 13. Machine-Readable Pipeline Status

The quality check writes the final machine-readable status to:

```text
data/pipeline_status/de7_pipeline_status.json
```

The status contains:

```text
run_id
run_timestamp
per_task_status
rows_in
rows_rejected
nulls_handled
rows_published
warehouse_rows
duplicate_grain_groups
AS_OF
```

Example successful status:

```json
{
  "run_id": "manual__2026-09-03T20:14:27+00:00",
  "per_task_status": {
    "ingest": "success",
    "validate": "success",
    "spark_process": "success",
    "load_warehouse": "success",
    "quality_check": "success"
  },
  "rows_in": 144,
  "rows_rejected": 0,
  "nulls_handled": 0,
  "rows_published": 144,
  "warehouse_rows": 144,
  "duplicate_grain_groups": 0,
  "AS_OF": "2013-11-09 23:00:00"
}
```

---

## 14. Idempotency and Rerun Behavior

The DE7 pipeline was rerun after the successful 144-row load.

The final warehouse remained:

```text
Rows: 144
AS_OF: 2013-11-09 23:00:00
Duplicate grain: 0
```

The row count did not increase to 288.

This demonstrates that rerunning the complete pipeline does not duplicate warehouse records.

The warehouse loader protects the `(grid_id, timestamp)` grain using UPSERT behavior.

Therefore:

```text
First successful processing:
144 rows

Complete pipeline rerun:
144 rows

Duplicate grain:
0
```

Result:

```text
IDEMPOTENCY: PASS
```

---

## 15. Recovery Procedure

When a pipeline failure occurs:

1. Identify the failed Airflow task.
2. Use the troubleshooting map to identify the responsible module.
3. Inspect the corresponding logs and output files.
4. Correct the underlying problem.
5. Trigger the DAG again.
6. Verify all task states.
7. Verify warehouse row count.
8. Verify duplicate grain.
9. Verify `AS_OF`.
10. Verify the machine-readable status file.
11. Verify the notification log.

The DAG is configured with:

```text
max_active_runs = 1
```

to prevent overlapping pipeline executions.

---

## 16. Final DE7 Verification

The following acceptance tests were completed:

* [x] Airflow DAG created and successfully imported.
* [x] Ingestion task implemented.
* [x] Validation task implemented.
* [x] Spark processing task implemented.
* [x] Warehouse loading task implemented.
* [x] Quality check implemented.
* [x] Notification task implemented.
* [x] Task dependencies configured.
* [x] Failure behavior demonstrated.
* [x] Corrected rejected file successfully reprocessed.
* [x] Held-back file successfully traced from landing to warehouse.
* [x] Static `milano-grid.geojson` kept as reference input.
* [x] Machine-readable pipeline status generated.
* [x] Per-task status recorded.
* [x] Row counts recorded.
* [x] `AS_OF` recorded.
* [x] Duplicate grain check implemented.
* [x] Successful rerun verified.
* [x] No duplicate warehouse records after rerun.
* [x] Success and failure notification logs generated.

---

## 17. Final Result

```text
DE7 END-TO-END AIRFLOW PIPELINE
STATUS: PASS
```

Latest successful pipeline behavior:

```text
Input rows       : 144
Rejected rows    : 0
Nulls handled    : 0
Published rows   : 144
Warehouse rows   : 144
Duplicate grain  : 0
AS_OF            : 2013-11-09 23:00:00
Rerun status     : SUCCESS
Idempotency      : PASS
```

The DE7 pipeline successfully demonstrates automated batch orchestration from file landing through validation, Spark processing, analytics publication, warehouse loading, quality validation, and final notification.
