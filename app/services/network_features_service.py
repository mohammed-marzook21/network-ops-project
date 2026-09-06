"""
Grid feature-serving layer.
Phase 4, Network Operations Predictive Intelligence Project

IMPORTANT: this module reads grid_features and NEVER recomputes a
feature. If a feature is missing (grid unknown, or no row in
grid_features yet), that's a clear, explicit error -- never a
silently-computed zero and never a fallback to fact_network_activity.
The actual feature engineering lives in ml/features_placeholder.py
today, and will live in ml/features.py once ML2 is built for real --
either way, it does NOT belong here.
"""
from datetime import datetime

from app.db import get_connection
from app.services.network_grid_service import MAX_GRID_ID, MIN_GRID_ID, UnknownGridError
from app.services.time_utils import get_effective_as_of


class FeaturesNotFoundError(Exception):
    """The grid is valid, but grid_features has no row for it yet
    (pipeline hasn't run for this grid, or produced no output)."""


def get_grid_features(grid_id):
    if grid_id < MIN_GRID_ID or grid_id > MAX_GRID_ID:
        raise UnknownGridError(
            f"grid_id {grid_id} is outside the valid range {MIN_GRID_ID}-{MAX_GRID_ID}"
        )

    conn = get_connection()
    try:
        exists = conn.execute(
            "SELECT 1 FROM dim_grid WHERE grid_id = ? LIMIT 1", (grid_id,)
        ).fetchone()
        if not exists:
            raise UnknownGridError(f"grid_id {grid_id} was not found in dim_grid")

        try:
            row = conn.execute(
                """
                SELECT grid_id, avg_activity, activity_growth, active_hours,
                       peak_ratio, variability, internet_share, feature_timestamp,
                       data_quality_status, row_count
                FROM grid_features
                WHERE grid_id = ?
                """,
                (grid_id,),
            ).fetchone()
        except Exception as exc:
            # e.g. sqlite3.OperationalError: no such table: grid_features --
            # the feature pipeline has never been run at all.
            raise FileNotFoundError(
                "grid_features table not found -- has the feature pipeline "
                "(ml/features_placeholder.py, or ml/features.py once ML2 ships) been run?"
            ) from exc

        if row is None:
            raise FeaturesNotFoundError(
                f"No stored features found for grid_id {grid_id}. "
                f"Run the feature pipeline to populate grid_features for this grid."
            )

        # Freshness is computed live, not stored -- it should always reflect
        # how stale the CURRENT warehouse data makes this snapshot look,
        # not a number frozen at the time the features were computed.
        current_as_of = get_effective_as_of(conn, None)
        feature_age_hours = _hours_between(row["feature_timestamp"], current_as_of)

        return {
            "grid_id": row["grid_id"],
            "avg_activity": row["avg_activity"],
            "activity_growth": row["activity_growth"],
            "active_hours": row["active_hours"],
            "peak_ratio": row["peak_ratio"],
            "variability": row["variability"],
            "internet_share": row["internet_share"],
            "feature_timestamp": row["feature_timestamp"],
            "data_quality_status": row["data_quality_status"],
            "row_count": row["row_count"],
            "feature_age_hours": feature_age_hours,
        }
    finally:
        conn.close()


def _hours_between(earlier_ts: str, later_ts: str) -> float:
    fmt = "%Y-%m-%d %H:%M:%S"
    earlier = datetime.strptime(earlier_ts, fmt)
    later = datetime.strptime(later_ts, fmt)
    return round((later - earlier).total_seconds() / 3600.0, 2)
