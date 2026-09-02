"""
DE3 - Full Pipeline: Ingestion + Spark Processing
Phase 3, Network Operations Predictive Intelligence Project

Task graph: detect_files -> process_files -> run_spark_job -> log_completion

This DAG is intentionally thin. No cleaning or aggregation logic exists
here -- detect_files/process_files reuse ingestion/ingestion.py exactly
as built in DE2, and run_spark_job simply invokes the already-tested
spark/telecom_pipeline.py as a subprocess. If that subprocess exits
non-zero (which it already does on empty input or a grain violation --
see SP7), Airflow marks the task FAILED, and log_completion (which
depends on it) never runs -- this is Airflow's default behavior, not
something coded here.
"""

import os
import sys
import subprocess
from datetime import datetime

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models import Variable

PROJECT_ROOT = os.path.dirname(os.environ.get("AIRFLOW_HOME", os.path.expanduser("~/network-ops-project/airflow")))
sys.path.insert(0, PROJECT_ROOT)

from ingestion.ingestion import detect_files, process_file

LANDING_DIR = os.path.join(PROJECT_ROOT, "data", "landing")
RAW_DIR = os.path.join(PROJECT_ROOT, "data", "raw")
REJECTED_DIR = os.path.join(PROJECT_ROOT, "data", "rejected")
LOG_PATH = os.path.join(PROJECT_ROOT, "logs", "ingestion_log.jsonl")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "data", "phase3_output")


def detect_files_task(**context):
    files = detect_files(LANDING_DIR)
    print(f"Detected {len(files)} file(s): {files}")
    context["ti"].xcom_push(key="detected_files", value=files)
    return files


def process_files_task(**context):
    files = context["ti"].xcom_pull(task_ids="detect_files", key="detected_files")
    if not files:
        print("No files detected - nothing to process.")
        return []
    results = [process_file(f, RAW_DIR, REJECTED_DIR, LOG_PATH) for f in files]
    for r in results:
        print(r)
    return results


def run_spark_job_task(**context):
    """
    Launches spark/telecom_pipeline.py as a subprocess. The reference
    GeoJSON directory is read from an Airflow Variable (REFERENCE_DIR),
    not hardcoded -- satisfies the "configuration, not a hardcoded
    string" acceptance criterion.

    If the subprocess exits non-zero, this function raises, which
    Airflow interprets as a task failure -- propagating naturally to
    downstream tasks without any extra code.
    """
    reference_dir = Variable.get("REFERENCE_DIR", default_var=os.path.join(PROJECT_ROOT, "data", "reference"))
    pipeline_script = os.path.join(PROJECT_ROOT, "spark", "telecom_pipeline.py")

    start_time = datetime.now().isoformat()
    print(f"spark_job_start={start_time}")
    print(f"Using reference_dir={reference_dir} (from Airflow Variable REFERENCE_DIR)")

    result = subprocess.run(
        [
            sys.executable, pipeline_script,
            "--input-dir", RAW_DIR,
            "--output-dir", OUTPUT_DIR,
            "--reference-dir", reference_dir,
        ],
        capture_output=True, text=True,
    )

    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
        print(f"spark_job_status=FAILED (exit code {result.returncode})")
        raise RuntimeError(f"telecom_pipeline.py failed with exit code {result.returncode}")

    end_time = datetime.now().isoformat()
    print(f"spark_job_end={end_time}")
    print("spark_job_status=SUCCESS")


def log_completion_task(**context):
    """
    Only ever runs if run_spark_job succeeded (Airflow's default
    trigger rule). Confirms analytics output actually exists before
    declaring the whole pipeline complete.
    """
    analytics_dir = os.path.join(OUTPUT_DIR, "analytics", "hourly_grid_summary")
    if not os.path.exists(analytics_dir):
        raise RuntimeError(f"Expected analytics output not found at {analytics_dir}")
    print(f"Pipeline completed successfully. Analytics output confirmed at {analytics_dir}")


default_args = {"owner": "mohammed", "retries": 0}

with DAG(
    dag_id="de3_full_pipeline",
    default_args=default_args,
    description="Ingestion + Spark processing, full pipeline",
    schedule_interval=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["phase3", "de3", "pipeline"],
) as dag:

    detect_task = PythonOperator(task_id="detect_files", python_callable=detect_files_task)
    process_task = PythonOperator(task_id="process_files", python_callable=process_files_task)
    spark_task = PythonOperator(task_id="run_spark_job", python_callable=run_spark_job_task)
    complete_task = PythonOperator(task_id="log_completion", python_callable=log_completion_task)

    detect_task >> process_task >> spark_task >> complete_task