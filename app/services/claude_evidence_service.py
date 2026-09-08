"""
Curated evidence assembler for Phase 7 C1.

Builds one evidence package from existing analytics/ML outputs.
No raw telecom rows are sent to Claude and no ML features or
anomaly scores are recomputed here.
"""

"""
Curated evidence assembler for Phase 7 C1.
"""

from app.db import get_connection
from app.services.network_features_service import get_grid_features
from app.services.network_intelligence_service import get_alerts


def _get_predictive_risk(conn, grid_id: int, timestamp: str):
    try:
        row = conn.execute(
            """
            SELECT
                risk_score,
                risk_level,
                model_version
            FROM network_risk_scores
            WHERE grid_id = ?
              AND timestamp = ?
            LIMIT 1
            """,
            (grid_id, timestamp),
        ).fetchone()
    except Exception as exc:
        if "no such table: network_risk_scores" in str(exc):
            return None
        raise

    if row is None:
        return None

    return {
        "risk_score": row["risk_score"],
        "risk_level": row["risk_level"],
        "model_version": row["model_version"],
        "meaning": (
            "ML prediction of next-hour unusually high activity. "
            "This is an investigation-priority signal, not proof of "
            "congestion, outage, fault, or capacity exhaustion."
        ),
    }





def get_claude_grid_evidence(grid_id: int) -> dict:
    features = get_grid_features(grid_id)

    conn = get_connection()

    try:
        timestamp = features["feature_timestamp"]
        alerts_payload = get_alerts(
            limit=10000,
            requested_as_of=timestamp,
        )

        grid_alerts = [
            alert
            for alert in alerts_payload["alerts"]
            if alert["grid_id"] == grid_id
        ]

        anomaly = conn.execute(
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

        # Rule alert is deliberately read from its persisted/current
        # operational evidence only if the grid meets the API3 rule.
        #
        # API3 currently computes this dynamically, so C1 does not
        # duplicate that calculation here. We expose the ML4 anomaly
        # evidence and stored ML features first.
        rule_alerts = [
            {
                "severity": alert["severity"],
                "reason": alert["reason"],
            }
            for alert in grid_alerts
        ]
        
        predictive_risk = _get_predictive_risk(
            conn,
            grid_id,
            timestamp,
        )

        
        


        if anomaly is None:
            current_activity = None
            baseline_activity = None
            anomaly_score = None
            anomaly_direction = None
            anomaly_reason = None
            is_anomaly = None
            baseline_sample_count = None
        else:
            current_activity = anomaly["current_activity"]
            baseline_activity = anomaly["baseline_activity"]
            anomaly_score = anomaly["anomaly_score"]
            anomaly_direction = anomaly["direction"]
            anomaly_reason = anomaly["reason"]
            is_anomaly = bool(anomaly["is_anomaly"])
            baseline_sample_count = anomaly["baseline_sample_count"]

        return {
            "grid_id": grid_id,
            "timestamp": timestamp,

            "current_total_activity": current_activity,
            "baseline_total_activity": baseline_activity,

            "activity_growth": features["activity_growth"],
            "peak_ratio": features["peak_ratio"],
            "variability": features["variability"],
            "internet_share": features["internet_share"],

            "anomaly_score": anomaly_score,
            "anomaly_direction": anomaly_direction,
            "is_anomaly": is_anomaly,
            "anomaly_reason": anomaly_reason,
            "baseline_sample_count": baseline_sample_count,

            "rule_alerts": rule_alerts,
            "predictive_risk": predictive_risk,

            "evidence_metadata": {
                "feature_timestamp": features["feature_timestamp"],
                "data_quality_status": features["data_quality_status"],
                "feature_age_hours": features["feature_age_hours"],
                "feature_source": "grid_features",
                "anomaly_source": "network_anomaly_scores",
            },
        }

    finally:
        conn.close()
