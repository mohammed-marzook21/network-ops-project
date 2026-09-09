"""
Curated incident-context builder for Phase 7 C3.

C3 compares long/dumped context with a deliberately curated evidence
package. Historical warehouse records are summarized before they are
provided to Claude; raw telecom rows are not exposed.
"""
from app.services.claude_evidence_service import get_claude_grid_evidence
from app.services.operational_support_service import get_pipeline_status
from app.db import get_connection
from app.services.claude_noc_tool_executor import execute_noc_tool
def build_curated_incident_context(grid_id: int) -> dict:
    """
    Build the C3 curated incident evidence package.

    Current evidence comes from the existing C1 evidence assembler.
    Historical activity is summarized before entering Claude context.
    Pipeline status is included so data trustworthiness forms part of
    the incident investigation.
    """
    current_evidence = get_claude_grid_evidence(grid_id)

    incident_timestamp = current_evidence["timestamp"]

    recent_history = get_recent_history_summary(
        grid_id=grid_id,
        before_timestamp=incident_timestamp,
        interval_limit=24,
    )

    historical_evidence = get_historical_evidence_summary(
        grid_id=grid_id,
        before_timestamp=incident_timestamp,
    )

    pipeline_status = get_pipeline_status()

    return {
        "context_type": "curated_incident_evidence",
        "grid_id": grid_id,
        "incident_timestamp": incident_timestamp,
        "current_evidence": current_evidence,
        "recent_history_summary": recent_history,
        "historical_evidence_summary": historical_evidence,
        "pipeline_status": pipeline_status,
        "context_notes": {
            "raw_activity_rows_included": False,
            "history_is_summarized": True,
            "historical_anomaly_evidence_available": (
                historical_evidence["anomaly_history"][
                    "historical_evidence_available"
                ]
            ),
            "historical_predictive_risk_evidence_available": (
                historical_evidence["predictive_risk_history"][
                    "historical_evidence_available"
                ]
            ),
        },
    }
def get_recent_history_summary(
    grid_id: int,
    before_timestamp: str,
    interval_limit: int = 24,
) -> dict:
    """
    Summarize the most recent completed activity intervals before
    the incident timestamp. Raw hourly rows are not returned.
    """
    conn = get_connection()

    try:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS interval_count,
                AVG(total_activity) AS avg_total_activity,
                MIN(total_activity) AS min_total_activity,
                MAX(total_activity) AS max_total_activity
            FROM (
                SELECT
                    f.total_activity
                FROM fact_network_activity AS f
                JOIN dim_time AS t
                  ON t.time_key = f.time_key
                WHERE f.grid_id = ?
                  AND t.ts < ?
                ORDER BY t.ts DESC
                LIMIT ?
            )
            """,
            (grid_id, before_timestamp, interval_limit),
        ).fetchone()

        return {
            "requested_interval_limit": interval_limit,
            "interval_count": row["interval_count"],
            "avg_total_activity": row["avg_total_activity"],
            "min_total_activity": row["min_total_activity"],
            "max_total_activity": row["max_total_activity"],
        }

    finally:
        conn.close()

def get_historical_evidence_summary(
    grid_id: int,
    before_timestamp: str,
) -> dict:
    """
    Summarize evidence strictly before the current incident interval.

    Returns aggregate historical evidence only. Individual warehouse
    activity rows are deliberately not returned.
    """
    conn = get_connection()

    try:
        activity = conn.execute(
            """
            SELECT
                COUNT(*) AS interval_count,
                AVG(f.total_activity) AS avg_total_activity,
                MIN(f.total_activity) AS min_total_activity,
                MAX(f.total_activity) AS max_total_activity
            FROM fact_network_activity AS f
            JOIN dim_time AS t
              ON t.time_key = f.time_key
            WHERE f.grid_id = ?
              AND t.ts < ?
            """,
            (grid_id, before_timestamp),
        ).fetchone()

        anomaly = conn.execute(
            """
            SELECT
                COUNT(*) AS scored_intervals,
                SUM(CASE WHEN is_anomaly = 1 THEN 1 ELSE 0 END)
                    AS anomaly_count,
                SUM(
                    CASE
                        WHEN is_anomaly = 1 AND direction = 'high'
                        THEN 1 ELSE 0
                    END
                ) AS high_anomaly_count,
                SUM(
                    CASE
                        WHEN is_anomaly = 1 AND direction = 'low'
                        THEN 1 ELSE 0
                    END
                ) AS low_anomaly_count
            FROM network_anomaly_scores
            WHERE grid_id = ?
              AND timestamp < ?
            """,
            (grid_id, before_timestamp),
        ).fetchone()

        risk = conn.execute(
            """
            SELECT
                COUNT(*) AS scored_intervals,
                SUM(CASE WHEN risk_level = 'high' THEN 1 ELSE 0 END)
                    AS high_risk_count,
                SUM(CASE WHEN risk_level = 'medium' THEN 1 ELSE 0 END)
                    AS medium_risk_count,
                SUM(CASE WHEN risk_level = 'low' THEN 1 ELSE 0 END)
                    AS low_risk_count
            FROM network_risk_scores
            WHERE grid_id = ?
              AND timestamp < ?
            """,
            (grid_id, before_timestamp),
        ).fetchone()

        return {
            "history_before": before_timestamp,
            "activity_history": {
                "interval_count": activity["interval_count"],
                "avg_total_activity": activity["avg_total_activity"],
                "min_total_activity": activity["min_total_activity"],
                "max_total_activity": activity["max_total_activity"],
            },
            "anomaly_history": {
                "scored_intervals": anomaly["scored_intervals"],
                "anomaly_count": anomaly["anomaly_count"] or 0,
                "high_anomaly_count": anomaly["high_anomaly_count"] or 0,
                "low_anomaly_count": anomaly["low_anomaly_count"] or 0,
                "historical_evidence_available": anomaly["scored_intervals"] > 0,
            },
            "predictive_risk_history": {
                "scored_intervals": risk["scored_intervals"],
                "high_risk_count": risk["high_risk_count"] or 0,
                "medium_risk_count": risk["medium_risk_count"] or 0,
                "low_risk_count": risk["low_risk_count"] or 0,
                "historical_evidence_available": risk["scored_intervals"] > 0,
            },

        }



    finally:
        conn.close()

def build_dumped_incident_context(grid_id: int) -> dict:
    """
    Build the intentionally verbose C3 comparison context.

    This represents the 'dump everything' experiment using trusted,
    aggregated service/API evidence. It still does not expose raw
    source telecom rows.
    """
    pipeline_status = execute_noc_tool(
        "get_pipeline_status",
        {},
    )

    grid_activity = execute_noc_tool(
        "get_grid_activity",
        {"grid_id": grid_id},
    )

    features = execute_noc_tool(
        "get_grid_features",
        {"grid_id": grid_id},
    )

    location = execute_noc_tool(
        "get_grid_location",
        {"grid_id": grid_id},
    )

    network_summary = execute_noc_tool(
        "get_network_summary",
        {},
    )

    hotspots = execute_noc_tool(
        "get_hotspots",
        {"limit": 100},
    )

    current_evidence = get_claude_grid_evidence(grid_id)

    return {
        "context_type": "dumped_incident_evidence",
        "grid_id": grid_id,
        "pipeline_status": pipeline_status,
        "network_summary": network_summary,
        "grid_activity_full_response": grid_activity,
        "grid_features": features,
        "grid_location": location,
        "hotspots": hotspots,
        "current_evidence": current_evidence,
        "context_notes": {
            "raw_source_rows_included": False,
            "full_aggregated_activity_series_included": True,
            "purpose": (
                "Intentionally verbose comparison context for the "
                "C3 context-engineering experiment."
            ),
        },
    }
