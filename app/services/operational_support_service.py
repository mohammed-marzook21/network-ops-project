"""
Service layer for API6 operational support endpoints.
Phase 4, Network Operations Predictive Intelligence Project.

Pipeline status is read directly from the DE7-generated status record.
Grid location is read from dim_grid.
"""

import json
import os
from datetime import datetime

from app.db import get_connection


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

PIPELINE_STATUS_PATH = os.path.join(
    PROJECT_ROOT,
    "data",
    "pipeline_status",
    "de7_pipeline_status.json",
)


def get_pipeline_status():
    """
    Read the DE7 pipeline status record directly.

    Health is determined from the latest recorded pipeline result.
    This service does not recompute pipeline metrics independently.
    """

    if not os.path.exists(PIPELINE_STATUS_PATH):
        raise FileNotFoundError(
            f"Pipeline status record not found at {PIPELINE_STATUS_PATH}"
        )

    with open(PIPELINE_STATUS_PATH, "r", encoding="utf-8") as file:
        status = json.load(file)

    reasons = []

    # Required task statuses must all be successful.
    per_task_status = status.get("per_task_status", {})

    if not per_task_status:
        reasons.append("Pipeline status record contains no per-task status.")

    for task_name, task_status in per_task_status.items():
        if task_status != "success":
            reasons.append(
                f"Task '{task_name}' has status '{task_status}', not 'success'."
            )

    # Basic publication check.
    rows_published = status.get("rows_published")

    if rows_published is None:
        reasons.append("Pipeline status record is missing rows_published.")
    elif rows_published <= 0:
        reasons.append("Pipeline published zero rows.")

    # Required AS_OF check.
    as_of = status.get("AS_OF")

    if not as_of:
        reasons.append("Pipeline status record is missing AS_OF.")

    # Compare DE7 AS_OF with the analytics layer.
    freshness_hours = 0.0

    if as_of:
        conn = get_connection()

        try:
            row = conn.execute(
                "SELECT MAX(ts) AS max_ts FROM dim_time"
            ).fetchone()

            if row is None or row["max_ts"] is None:
                reasons.append(
                    "Analytics layer contains no timestamp for freshness validation."
                )
            else:
                latest_ts = row["max_ts"]

                as_of_dt = datetime.strptime(
                    as_of,
                    "%Y-%m-%d %H:%M:%S",
                )

                latest_dt = datetime.strptime(
                    latest_ts,
                    "%Y-%m-%d %H:%M:%S",
                )

                freshness_hours = abs(
                    (latest_dt - as_of_dt).total_seconds()
                ) / 3600

                if as_of != latest_ts:
                    reasons.append(
                        "Pipeline AS_OF does not match the latest analytics timestamp."
                    )

        finally:
            conn.close()

    healthy = len(reasons) == 0

    return {
        "healthy": healthy,
        "reasons": reasons,
        "run_id": status.get("run_id"),
        "run_timestamp": status.get("run_timestamp"),
        "per_task_status": per_task_status,
        "rows_in": status.get("rows_in"),
        "rows_rejected": status.get("rows_rejected"),
        "nulls_handled": status.get("nulls_handled"),
        "rows_published": rows_published,
        "as_of": as_of,
        "freshness_hours": freshness_hours,
    }


def get_grid_location(grid_id: int):
    """
    Return geographic evidence for a grid.

    Full polygon geometry is intentionally not returned.
    """

    conn = get_connection()

    try:
        row = conn.execute(
            """
            SELECT
                grid_id,
                centroid_lat,
                centroid_lon
            FROM dim_grid
            WHERE grid_id = ?
            """,
            (grid_id,),
        ).fetchone()

        if row is None:
            raise ValueError(f"Grid {grid_id} was not found.")

        return {
            "grid_id": row["grid_id"],
            "centroid_lat": row["centroid_lat"],
            "centroid_lon": row["centroid_lon"],
            "polygon_reference": f"dim_grid.geometry_json for grid_id {grid_id}",
        }

    finally:
        conn.close()