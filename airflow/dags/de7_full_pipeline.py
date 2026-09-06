import json
import os
import subprocess
import sys
from datetime import datetime

import pendulum
from airflow import DAG
from airflow.exceptions import AirflowException
from airflow.operators.python import PythonOperator
from airflow.utils.trigger_rule import TriggerRule


# -------------------------------------------------------------------
# Paths
# -------------------------------------------------------------------

PROJECT_ROOT = os.path.dirname(
    os.environ.get(
        "AIRFLOW_HOME",
        os.path.expanduser("~/network-ops-project/airflow"),
    )
)

LANDING_DIR = os.path.join(PROJECT_ROOT, "data", "landing")
RAW_DIR = os.path.join(PROJECT_ROOT, "data", "raw")
REJECTED_DIR = os.path.join(PROJECT_ROOT, "data", "rejected")

OUTPUT_DIR = os.path.join(PROJECT_ROOT, "data", "phase3_output")
REFERENCE_DIR = os.path.join(PROJECT_ROOT, "data", "reference")

WAREHOUSE_DB = os.path.join(
    PROJECT_ROOT,
    "warehouse",
    "network_analytics.db",
)

ANALYTICS_FILE = os.path.join(
    OUTPUT_DIR, "analytics", "hourly_grid_summary", "part-0.parquet"
)

SPARK_METRICS_FILE = os.path.join(
    OUTPUT_DIR,
    "spark_metrics.json",
)

STATUS_DIR = os.path.join(
    PROJECT_ROOT,
    "data",
    "pipeline_status",
)

STATUS_FILE = os.path.join(
    STATUS_DIR,
    "de7_pipeline_status.json",
)

NOTIFICATION_LOG = os.path.join(
    PROJECT_ROOT,
    "logs",
    "de7_notification.log",
)


# -------------------------------------------------------------------
# INGEST
# -------------------------------------------------------------------

def ingest_task(**context):
    """
    Run the existing DE2 ingestion logic.
    """

    sys.path.insert(0, PROJECT_ROOT)

    from ingestion.ingestion import (
        detect_files,
        process_file,
    )

    os.makedirs(LANDING_DIR, exist_ok=True)
    os.makedirs(RAW_DIR, exist_ok=True)
    os.makedirs(REJECTED_DIR, exist_ok=True)

    files = detect_files(LANDING_DIR)

    if not files:
        raise AirflowException(
            f"No daily ingestion files found in {LANDING_DIR}"
        )

    results = []

    for filepath in files:
        result = process_file(
    filepath,
    RAW_DIR,
    REJECTED_DIR,
    os.path.join(PROJECT_ROOT, "logs", "ingestion_log.jsonl"),
)
        results.append(result)

    total_rows = sum(
        int(r.get("row_count", 0) or 0)
        for r in results
        if r.get("status") == "accepted"
    )

    rejected_rows = sum(
        int(r.get("row_count", 0) or 0)
        for r in results
        if r.get("status") == "rejected"
    )

    context["ti"].xcom_push(
        key="rows_in",
        value=total_rows,
    )

    context["ti"].xcom_push(
        key="rows_rejected",
        value=rejected_rows,
    )

    context["ti"].xcom_push(
        key="ingest_results",
        value=results,
    )

    print(f"Ingested files: {len(files)}")
    print(f"Rows in: {total_rows}")
    print(f"Rows rejected: {rejected_rows}")

    for result in results:
        print(result)


# -------------------------------------------------------------------
# VALIDATE
# -------------------------------------------------------------------

def validate_task(**context):
    """
    Validate ingestion results.

    accepted          -> valid
    skipped_duplicate -> valid for reruns/idempotency
    rejected          -> validation failure
    """

    results = context["ti"].xcom_pull(
        task_ids="ingest",
        key="ingest_results",
    )

    if not results:
        raise AirflowException(
            "No ingestion results found."
        )

    invalid_results = [
        result
        for result in results
        if result.get("status")
        not in {"accepted", "skipped_duplicate"}
    ]

    if invalid_results:
        raise AirflowException(
            f"Validation failed for "
            f"{len(invalid_results)} file(s): "
            f"{invalid_results}"
        )

    accepted = sum(
        1
        for result in results
        if result.get("status") == "accepted"
    )

    duplicates = sum(
        1
        for result in results
        if result.get("status") == "skipped_duplicate"
    )

    print("Validation passed.")
    print(f"Accepted files: {accepted}")
    print(f"Skipped duplicate files: {duplicates}")


# -------------------------------------------------------------------
# SPARK PROCESS
# -------------------------------------------------------------------

def spark_process_task(**context):
    """
    Run the existing Spark processing pipeline.
    """

    script = os.path.join(
        PROJECT_ROOT,
        "spark",
        "telecom_pipeline.py",
    )

    command = [
        sys.executable,
        script,
        "--input-dir",
        RAW_DIR,
        "--output-dir",
        OUTPUT_DIR,
        "--reference-dir",
        REFERENCE_DIR,
    ]

    print("Running Spark pipeline:")
    print(" ".join(command))

    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        text=True,
    )

    if result.returncode != 0:
        raise AirflowException(
            f"Spark pipeline failed with exit code "
            f"{result.returncode}"
        )

    if not os.path.exists(ANALYTICS_FILE):
        raise AirflowException(
            f"Analytics output not found: {ANALYTICS_FILE}"
        )

    print(
        f"Spark processing completed successfully. "
        f"Analytics output: {ANALYTICS_FILE}"
    )


# -------------------------------------------------------------------
# LOAD WAREHOUSE
# -------------------------------------------------------------------

def load_warehouse_task(**context):
    """
    Load analytics output into SQLite warehouse.
    """

    script = os.path.join(
        PROJECT_ROOT,
        "warehouse",
        "load_warehouse.py",
    )

    command = [
        sys.executable,
        script,
        "--analytics-file",
        ANALYTICS_FILE,
        "--db",
        WAREHOUSE_DB,
    ]

    print("Running warehouse loader:")
    print(" ".join(command))

    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        text=True,
    )

    if result.returncode != 0:
        raise AirflowException(
            f"Warehouse load failed with exit code "
            f"{result.returncode}"
        )

    print("Warehouse load completed successfully.")



# -------------------------------------------------------------------
# ML FEATURE GENERATION
# -------------------------------------------------------------------

def generate_ml_features_task(**context):
    """
    Generate ML feature tables from the warehouse.

    Feature-engineering logic remains in ml.features
    rather than being implemented inside the DAG.
    """

    sys.path.insert(0, PROJECT_ROOT)

    from ml.features import build_features

    print("Starting ML feature generation...")

    try:
        build_features()
    except Exception as exc:
        raise AirflowException(
            f"ML feature generation failed: {exc}"
        ) from exc

    print("ML feature generation completed successfully.")


# -------------------------------------------------------------------
# ML6 RISK + ANOMALY SCORING
# -------------------------------------------------------------------

def ml_scoring_task(**context):
    """
    Run reusable ML risk scoring and anomaly scoring.

    Risk-scoring logic remains in ml.batch_score.
    Anomaly logic remains in ml.anomaly.
    """

    sys.path.insert(0, PROJECT_ROOT)

    from ml.batch_score import score_latest_features
    from ml.anomaly import main as run_anomaly_scoring

    print("Starting ML6 batch scoring...")

    try:
        timestamp, scored_grids = score_latest_features()

        print(
            f"Risk scoring completed: "
            f"{scored_grids} grids at {timestamp}"
        )

        print("Starting anomaly scoring...")
        run_anomaly_scoring()

    except Exception as exc:
        raise AirflowException(
            f"ML6 scoring failed: {exc}"
        ) from exc

    print(
        "ML6 risk and anomaly scoring completed successfully."
    )


# -------------------------------------------------------------------
# QUALITY CHECK
# -------------------------------------------------------------------

def quality_check_task(**context):
    """
    Verify warehouse quality and create machine-readable
    DE7 pipeline status.
    """

    if not os.path.exists(WAREHOUSE_DB):
        raise AirflowException(
            f"Warehouse database not found: {WAREHOUSE_DB}"
        )

    import sqlite3

    conn = sqlite3.connect(WAREHOUSE_DB)

    try:
        warehouse_rows = conn.execute(
            """
            SELECT COUNT(*)
            FROM fact_network_activity
            """
        ).fetchone()[0]

        as_of_row = conn.execute(
            """
            SELECT MAX(timestamp)
            FROM fact_network_activity
            """
        ).fetchone()

        as_of = as_of_row[0]

        duplicate_grain = conn.execute(
            """
            SELECT COUNT(*)
            FROM (
                SELECT grid_id, timestamp
                FROM fact_network_activity
                GROUP BY grid_id, timestamp
                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]

        feature_rows = conn.execute(
            """
            SELECT COUNT(*)
            FROM network_feature_table
            """
        ).fetchone()[0]

        latest_feature_row = conn.execute(
            """
            SELECT MAX(feature_timestamp)
            FROM network_feature_table
            """
        ).fetchone()

        latest_feature_timestamp = (
            latest_feature_row[0]
            if latest_feature_row
            else None
        )

        risk_rows = conn.execute(
            """
            SELECT COUNT(*)
            FROM network_risk_scores
            WHERE timestamp = ?
            """,
            (latest_feature_timestamp,),
        ).fetchone()[0]

        risk_duplicates = conn.execute(
            """
            SELECT COUNT(*)
            FROM (
                SELECT grid_id, timestamp
                FROM network_risk_scores
                GROUP BY grid_id, timestamp
                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]

        missing_model_versions = conn.execute(
            """
            SELECT COUNT(*)
            FROM network_risk_scores
            WHERE model_version IS NULL
               OR TRIM(model_version) = ''
            """
        ).fetchone()[0]

        anomaly_rows = conn.execute(
            """
            SELECT COUNT(*)
            FROM network_anomaly_scores
            WHERE timestamp = ?
            """,
            (latest_feature_timestamp,),
        ).fetchone()[0]

    finally:
        conn.close()

    if warehouse_rows == 0:
        raise AirflowException(
            "Quality check failed: warehouse contains 0 rows."
        )

    if duplicate_grain != 0:
        raise AirflowException(
            f"Quality check failed: "
            f"{duplicate_grain} duplicate grain groups found."
        )

    if feature_rows == 0:
        raise AirflowException(
            "Quality check failed: "
            "network_feature_table contains 0 rows."
        )

    if not latest_feature_timestamp:
        raise AirflowException(
            "Quality check failed: "
            "no latest ML feature timestamp found."
        )

    if risk_rows == 0:
        raise AirflowException(
            "Quality check failed: "
            "network_risk_scores contains "
            "no scores for the latest feature timestamp."
        )

    if risk_duplicates != 0:
        raise AirflowException(
            f"Quality check failed: "
            f"{risk_duplicates} duplicate "
            f"risk-score grain groups found."
        )

    if missing_model_versions != 0:
        raise AirflowException(
            f"Quality check failed: "
            f"{missing_model_versions} risk scores "
            f"have missing model_version."
        )

    if not os.path.exists(SPARK_METRICS_FILE):
        raise AirflowException(
            f"Spark metrics file not found: "
            f"{SPARK_METRICS_FILE}"
        )

    with open(
        SPARK_METRICS_FILE,
        "r",
        encoding="utf-8",
    ) as f:
        spark_metrics = json.load(f)

    required_metrics = [
        "input_rows",
        "rejected_rows",
        "nulls_handled",
        "rows_published",
    ]

    missing_metrics = [
        key
        for key in required_metrics
        if key not in spark_metrics
    ]

    if missing_metrics:
        raise AirflowException(
            f"Missing Spark metrics: {missing_metrics}"
        )

    rows_in = spark_metrics["input_rows"]
    rows_rejected = spark_metrics["rejected_rows"]
    nulls_handled = spark_metrics["nulls_handled"]
    rows_published = spark_metrics["rows_published"]

    run_id = context["run_id"]

    status = {
        "run_id": run_id,
        "run_timestamp": datetime.now().isoformat(),

        "per_task_status": {
            "ingest": "success",
            "validate": "success",
            "spark_process": "success",
            "load_warehouse": "success",
            "generate_ml_features": "success",
            "ml_scoring": "success",
            "quality_check": "success",
        },

        "rows_in": rows_in,
        "rows_rejected": rows_rejected,
        "nulls_handled": nulls_handled,
        "rows_published": rows_published,

        "warehouse_rows": warehouse_rows,

        "duplicate_grain_groups": duplicate_grain,

        "AS_OF": as_of,
        "ml6": {
            "feature_rows": feature_rows,
            "feature_timestamp": latest_feature_timestamp,
            "risk_rows": risk_rows,
            "risk_duplicate_grain_groups": risk_duplicates,
            "missing_model_versions": missing_model_versions,
            "anomaly_rows": anomaly_rows,
        },
    }

    os.makedirs(
        STATUS_DIR,
        exist_ok=True,
    )

    with open(
        STATUS_FILE,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            status,
            f,
            indent=2,
        )

    print(
        f"Quality check passed. "
        f"Warehouse rows: {warehouse_rows}"
    )

    print(f"AS_OF: {as_of}")

    print(
        f"Pipeline status written to: "
        f"{STATUS_FILE}"
    )


# -------------------------------------------------------------------
# NOTIFY
# -------------------------------------------------------------------

def notify_task(**context):
    """
    Lightweight success/failure notification.

    TriggerRule.ALL_DONE ensures this task executes even when
    an upstream task fails.
    """

    dag_run = context["dag_run"]

    task_ids = [
        "ingest",
        "validate",
        "spark_process",
        "load_warehouse",
        "generate_ml_features",
        "ml_scoring",
        "quality_check",
    ]

    task_status = {}

    for task_id in task_ids:
        task_instance = dag_run.get_task_instance(
            task_id=task_id
        )

        task_status[task_id] = (
            task_instance.state
            if task_instance
            else "unknown"
        )

    all_success = all(
        state == "success"
        for state in task_status.values()
    )

    timestamp = datetime.now().isoformat()

    os.makedirs(
        os.path.dirname(NOTIFICATION_LOG),
        exist_ok=True,
    )

    if all_success:
        message = (
            f"{timestamp} | "
            f"DE7 PIPELINE SUCCESS | "
            f"run_id={context['run_id']} | "
            f"tasks={task_status}"
        )
    else:
        message = (
            f"{timestamp} | "
            f"DE7 PIPELINE FAILURE | "
            f"run_id={context['run_id']} | "
            f"tasks={task_status}"
        )

    with open(
        NOTIFICATION_LOG,
        "a",
        encoding="utf-8",
    ) as f:
        f.write(message + "\n")

    print(message)

    if not all_success:
        raise AirflowException(
            "DE7 pipeline failed. "
            f"Task states: {task_status}"
        )

    print("DE7 pipeline completed successfully.")


# -------------------------------------------------------------------
# DAG
# -------------------------------------------------------------------

with DAG(
    dag_id="de7_full_pipeline",

    description=(
        "DE7 End-to-End Airflow Orchestration: "
        "ingest -> validate -> Spark -> warehouse -> "
        "quality check -> notify"
    ),

    start_date=pendulum.datetime(
        2026,
        1,
        1,
        tz="UTC",
    ),

    schedule=None,

    catchup=False,

    max_active_runs=1,

    default_args={
        "owner": "airflow",
        "retries": 0,
    },

    tags=[
        "DE7",
        "network-ops",
        "batch-pipeline",
    ],
) as dag:

    ingest = PythonOperator(
        task_id="ingest",
        python_callable=ingest_task,
    )

    validate = PythonOperator(
        task_id="validate",
        python_callable=validate_task,
    )

    spark_process = PythonOperator(
        task_id="spark_process",
        python_callable=spark_process_task,
    )

    load_warehouse = PythonOperator(
        task_id="load_warehouse",
        python_callable=load_warehouse_task,
    )

    generate_ml_features = PythonOperator(
        task_id="generate_ml_features",
        python_callable=generate_ml_features_task,
    )

    ml_scoring = PythonOperator(
        task_id="ml_scoring",
        python_callable=ml_scoring_task,
    )

    quality_check = PythonOperator(
        task_id="quality_check",
        python_callable=quality_check_task,
    )

    notify = PythonOperator(
        task_id="notify",
        python_callable=notify_task,
        trigger_rule=TriggerRule.ALL_DONE,
    )

    # ---------------------------------------------------------------
    # Dependencies
    # ---------------------------------------------------------------

    (
        ingest
        >> validate
        >> spark_process
        >> load_warehouse
        >> generate_ml_features
        >> ml_scoring
        >> quality_check
        >> notify
    )