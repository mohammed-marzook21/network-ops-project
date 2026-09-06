"""
Shared historical activity baseline utilities.

Phase 6 - ML4

This module provides ONE baseline implementation used by:

1. NP3 rule alerts
   - compare a grid against all of its history before as_of

2. ML4 anomaly scoring
   - compare a grid against historical observations from the same
     hour-of-day before as_of

Keeping this logic shared prevents NP3 and ML4 from drifting into two
different implementations of historical mean / variance.
"""

from __future__ import annotations

from typing import Literal


BaselineBucket = Literal["all_history", "hour_of_day"]


def get_activity_baselines(
    conn,
    as_of: str,
    bucket: BaselineBucket = "all_history",
):
    """
    Return historical baseline statistics for every grid.

    Only observations STRICTLY BEFORE as_of are used.

    bucket="all_history"
        Use every historical hour before as_of.
        This preserves the existing NP3 behaviour.

    bucket="hour_of_day"
        Use only historical observations having the same hour-of-day
        as as_of. This is the ML4 comparable-hour baseline.

    Returns:
        {
            grid_id: {
                "count": int,
                "mean": float,
                "mean_sq": float,
                "std": float,
            }
        }
    """

    if bucket == "all_history":
        rows = conn.execute(
            """
            SELECT
                f.grid_id AS grid_id,
                COUNT(*) AS sample_count,
                AVG(f.total_activity) AS mean_val,
                AVG(
                    f.total_activity * f.total_activity
                ) AS mean_sq
            FROM fact_network_activity f
            JOIN dim_time t
                ON f.time_key = t.time_key
            WHERE t.ts < ?
            GROUP BY f.grid_id
            """,
            (as_of,),
        ).fetchall()

    elif bucket == "hour_of_day":
        rows = conn.execute(
            """
            SELECT
                f.grid_id AS grid_id,
                COUNT(*) AS sample_count,
                AVG(f.total_activity) AS mean_val,
                AVG(
                    f.total_activity * f.total_activity
                ) AS mean_sq
            FROM fact_network_activity f
            JOIN dim_time t
                ON f.time_key = t.time_key
            WHERE t.ts < ?
              AND t.hour = (
                    SELECT hour
                    FROM dim_time
                    WHERE ts = ?
              )
            GROUP BY f.grid_id
            """,
            (as_of, as_of),
        ).fetchall()

    else:
        raise ValueError(
            "bucket must be 'all_history' or 'hour_of_day'"
        )

    baselines = {}

    for row in rows:
        mean_val = float(row["mean_val"])
        mean_sq = float(row["mean_sq"])

        variance = max(
            mean_sq - mean_val * mean_val,
            0.0,
        )

        baselines[row["grid_id"]] = {
            "count": int(row["sample_count"]),
            "mean": mean_val,
            "mean_sq": mean_sq,
            "std": variance ** 0.5,
        }

    return baselines