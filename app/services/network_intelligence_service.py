"""Hotspot & alert service layer.
Phase 4, Network Operations Predictive Intelligence Project

Two distinct rules, deliberately kept separate:

  * HOTSPOTS = the current highest-activity grids network-wide, at the
    single hour == as_of. A ranking, not an anomaly detector.

  * ALERTS = the NP3 rule-based anomaly rule: for each grid, compare its
    activity at as_of against ITS OWN historical mean/std (computed over
    every hour up to as_of). A grid alerts if its current z-score clears
    a threshold. This is what "rule-based" means here -- no ML model is
    involved yet; ML6 will eventually add a risk_score alongside this.

Both read exclusively from fact_network_activity/dim_time. Grid IDs
returned are always ones present in dim_grid, since every row here comes
from a join through fact_network_activity(grid_id) -> dim_grid.
"""

from app.db import get_connection
from app.services.time_utils import get_effective_as_of
from app.services.activity_baseline_service import (
    get_activity_baselines,
)

Z_THRESHOLD_HIGH = 3.0
Z_THRESHOLD_MEDIUM = 2.0

def _get_risk_scores(conn, as_of):
    """
    Return ML6 risk scores for one timestamp keyed by grid_id.

    If scoring has not been run yet, return an empty mapping so API3
    remains backward compatible and continues returning null ML fields.
    """
    try:
        rows = conn.execute(
            """
            SELECT
                grid_id,
                risk_score,
                risk_level,
                model_version
            FROM network_risk_scores
            WHERE timestamp = ?
            """,
            (as_of,),
        ).fetchall()
    except Exception as exc:
        if "no such table: network_risk_scores" in str(exc):
            return {}
        raise

    return {
        row["grid_id"]: {
            "risk_score": row["risk_score"],
            "risk_level": row["risk_level"],
            "model_version": row["model_version"],
        }
        for row in rows
    }
def get_hotspots(limit=20, severity=None, requested_as_of=None):
    conn = get_connection()
    try:
        as_of = get_effective_as_of(conn, requested_as_of)
        risk_by_grid = _get_risk_scores(conn, as_of)
        rows = conn.execute(
            """
            SELECT f.grid_id as grid_id, t.ts as ts, t.hour as hour,
                   f.total_activity as total_activity
            FROM fact_network_activity f
            JOIN dim_time t ON f.time_key = t.time_key
            WHERE t.ts = ?
            ORDER BY f.total_activity DESC, f.grid_id ASC
            LIMIT ?
            """,
            (as_of, limit),
        ).fetchall()

        hotspots = []
        for rank, row in enumerate(rows, start=1):
            item = {
                "grid_id": row["grid_id"],
                "ts": row["ts"],
                "hour": row["hour"],
                "total_activity": row["total_activity"],
                "status": "elevated",
                "reason": f"Ranked #{rank} by total network activity at this hour.",
                "risk_score": risk_by_grid.get(row["grid_id"], {}).get("risk_score"),
                "risk_level": risk_by_grid.get(row["grid_id"], {}).get("risk_level"),
                "model_version": risk_by_grid.get(row["grid_id"], {}).get("model_version"),
            }
            hotspots.append(item)

        if severity is not None:
            hotspots = [h for h in hotspots if h["status"] == severity]

        return {"as_of": as_of, "count": len(hotspots), "hotspots": hotspots}
    finally:
        conn.close()


def get_alerts(limit=20, severity=None, requested_as_of=None):
    conn = get_connection()
    try:
        as_of = get_effective_as_of(conn, requested_as_of)
        risk_by_grid = _get_risk_scores(conn, as_of)
        # Per-grid baseline mean/variance across every hour STRICTLY
        # BEFORE as_of (leave-one-out) -- not "<= as_of". If the current
        # hour were included in its own baseline, a genuine spike would
        # partially average itself away and understate its own z-score,
        # which weakens exactly the signal this rule exists to catch.
        baseline_by_grid = get_activity_baselines(
            conn,
            as_of,
            bucket="all_history",
        )

        current_rows = conn.execute(
            """
            SELECT f.grid_id as grid_id, t.ts as ts, t.hour as hour,
                   f.total_activity as total_activity
            FROM fact_network_activity f
            JOIN dim_time t ON f.time_key = t.time_key
            WHERE t.ts = ?
            """,
            (as_of,),
        ).fetchall()

        candidates = []
        for row in current_rows:
            baseline = baseline_by_grid.get(row["grid_id"])

            if baseline is None:
                continue

            mean_val = baseline["mean"]
            std_val = baseline["std"]

            if std_val == 0:
                continue

            z = (row["total_activity"] - mean_val) / std_val

            if z >= Z_THRESHOLD_HIGH:
                sev = "high"
            elif z >= Z_THRESHOLD_MEDIUM:
                sev = "medium"
            else:
                continue

            candidates.append(
                {
                    "grid_id": row["grid_id"],
                    "ts": row["ts"],
                    "hour": row["hour"],
                    "total_activity": row["total_activity"],
                    "baseline_activity": mean_val,
                    "severity": sev,
                    "reason": (
                        f"Activity is {z:.1f} standard deviations above this grid's "
                        f"historical average ({mean_val:.1f})."
                    ),
                    "risk_score": risk_by_grid.get(row["grid_id"], {}).get("risk_score"),
                    "risk_level": risk_by_grid.get(row["grid_id"], {}).get("risk_level"),
                    "model_version": risk_by_grid.get(row["grid_id"], {}).get("model_version"),
                    "_z": z,
                }
            )

        if severity is not None:
            candidates = [c for c in candidates if c["severity"] == severity]

        # Deterministic order: highest z-score first, grid_id as tiebreaker.
        candidates.sort(key=lambda c: (-c["_z"], c["grid_id"]))
        candidates = candidates[:limit]

        for c in candidates:
            c.pop("_z", None)

        return {"as_of": as_of, "count": len(candidates), "alerts": candidates}
    finally:
        conn.close()