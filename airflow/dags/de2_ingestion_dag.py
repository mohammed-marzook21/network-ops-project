"""
DE2 - Landing-to-Raw Ingestion DAG
Phase 3, Network Operations Predictive Intelligence Project

This DAG is intentionally thin: it only orchestrates. All actual
validation/routing/logging logic lives in ingestion/ingestion.py so it
stays independently testable and reusable (see the trainer note in the
guide -- SP7 and DE8 both reuse this same module).
"""

import os
import sys
from datetime import datetime

from airflow import DAG
from airflow.operators.python import PythonOperator

# The ingestion module lives at <project_root>/ingestion/, one level up
# from AIRFLOW_HOME (<project_root>/airflow/). Add project root to the
# path so this DAG can import it.
PROJECT_ROOT = os.path.dirname(os.environ.get("AIRFLOW_HOME", os.path.expanduser("~/network-ops-project/airflow")))
sys.path.insert(0, PROJECT_ROOT)

from ingestion.ingestion import detect_files, process_file

LANDING_DIR = os.path.join(PROJECT_ROOT, "data", "landing")
RAW_DIR = os.path.join(PROJECT_ROOT, "data", "raw")
REJECTED_DIR = os.path.join(PROJECT_ROOT, "data", "rejected")
LOG_PATH = os.path.join(PROJECT_ROOT, "logs", "ingestion_log.jsonl")


def detect_files_task(**context):
    """Find candidate files in landing/ and push the list to XCom."""
    files = detect_files(LANDING_DIR)
    print(f"Detected {len(files)} file(s): {files}")
    context["ti"].xcom_push(key="detected_files", value=files)
    return files


def process_files_task(**context):
    """
    Pull the detected file list from XCom and run the full
    validate -> route -> log flow on each one, using the SAME
    already-tested functions from ingestion.ingestion -- no logic
    is duplicated here.
    """
    files = context["ti"].xcom_pull(task_ids="detect_files", key="detected_files")
    if not files:
        print("No files detected - nothing to process.")
        return []

    results = []
    for filepath in files:
        result = process_file(filepath, RAW_DIR, REJECTED_DIR, LOG_PATH)
        print(result)
        results.append(result)
    return results


default_args = {
    "owner": "mohammed",
    "retries": 0,
}

with DAG(
    dag_id="de2_landing_to_raw_ingestion",
    default_args=default_args,
    description="Detects, validates, routes, and logs daily telecom activity files",
    schedule_interval=None,  # manual trigger only, for now
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["phase3", "de2", "ingestion"],
) as dag:

    detect_task = PythonOperator(
        task_id="detect_files",
        python_callable=detect_files_task,
    )

    process_task = PythonOperator(
        task_id="process_files",
        python_callable=process_files_task,
    )

    detect_task >> process_task