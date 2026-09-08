"""
Phase 7 C2 — Claude NOC tool executor.

Maps Claude tool requests onto existing trusted project services.

Important:
- Existing services remain the source of truth.
- Business logic is not duplicated here.
- Claude never receives direct raw telecom-table access.
- The anomaly adapter only reads the already-persisted ML4 result.
"""

from app.db import get_connection
from app.services.network_summary_service import get_network_summary
from app.services.network_grid_service import get_grid_activity
from app.services.network_intelligence_service import get_hotspots
from app.services.network_features_service import get_grid_features
from app.services.operational_support_service import (
    get_grid_location,
    get_pipeline_status,
)


def _get_anomaly_score(grid_id: int, timestamp: str) -> dict:
    """
    Read one already-computed ML4 anomaly result.

    No anomaly calculation is performed here.
    """

    conn = get_connection()

    try:
        row = conn.execute(
            """
            SELECT
                grid_id,
                timestamp,
                current_activity,
                baseline_activity,
                baseline_std,
                baseline_sample_count,
                anomaly_score,
                direction,
                is_anomaly,
                reason
            FROM network_anomaly_scores
            WHERE grid_id = ?
              AND timestamp = ?
            LIMIT 1
            """,
            (grid_id, timestamp),
        ).fetchone()

        if row is None:
            return {
                "grid_id": grid_id,
                "timestamp": timestamp,
                "available": False,
                "reason": (
                    "No stored anomaly assessment exists for the "
                    "requested grid and timestamp."
                ),
            }

        return {
            "grid_id": row["grid_id"],
            "timestamp": row["timestamp"],
            "available": True,
            "current_activity": row["current_activity"],
            "baseline_activity": row["baseline_activity"],
            "baseline_std": row["baseline_std"],
            "baseline_sample_count": row["baseline_sample_count"],
            "anomaly_score": row["anomaly_score"],
            "direction": row["direction"],
            "is_anomaly": bool(row["is_anomaly"]),
            "reason": row["reason"],
        }

    finally:
        conn.close()


def execute_noc_tool(tool_name: str, tool_input: dict | None = None):
    """
    Execute one trusted C2 NOC tool.

    The returned value is sourced from existing project services or from
    persisted ML output.
    """

    tool_input = tool_input or {}

    if tool_name == "get_pipeline_status":
        return get_pipeline_status()

    if tool_name == "get_network_summary":
        return get_network_summary(
            requested_as_of=tool_input.get("as_of"),
        )

    if tool_name == "get_grid_activity":
        return get_grid_activity(
            grid_id=tool_input["grid_id"],
            date=tool_input.get("date"),
            hour=tool_input.get("hour"),
            requested_as_of=tool_input.get("as_of"),
        )

    if tool_name == "get_hotspots":
        return get_hotspots(
            limit=tool_input.get("limit", 20),
            requested_as_of=tool_input.get("as_of"),
        )

    if tool_name == "get_grid_features":
        return get_grid_features(
            tool_input["grid_id"],
        )

    if tool_name == "get_anomaly_score":
        return _get_anomaly_score(
            grid_id=tool_input["grid_id"],
            timestamp=tool_input["timestamp"],
        )

    if tool_name == "get_grid_location":
        return get_grid_location(
            tool_input["grid_id"],
        )

    raise ValueError(f"Unknown C2 NOC tool: {tool_name}")