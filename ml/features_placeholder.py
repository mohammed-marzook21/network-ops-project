"""
PLACEHOLDER for ML2's feature-engineering pipeline.
Phase 4, Network Operations Predictive Intelligence Project

*** THIS IS NOT THE REAL ML2 DELIVERABLE. ***

ML2 has not been built yet. This script exists only so API4 has a real
`grid_features` table with real (not fake) numbers to read from, computed
straight from your actual warehouse data, in the exact schema the lab
spec calls for. When ML2 is built for real, it should:

  1. Produce a `grid_features` table with the SAME six column names used
     here (avg_activity, activity_growth, active_hours, peak_ratio,
     variability, internet_share) plus feature_timestamp -- API4 does not
     need to change at all if the schema matches.
  2. Replace this file (or just re-run it with better logic) -- nothing
     downstream cares how the numbers were computed, only that the table
     and column names match.

Run from C:\\network-ops-project with the venv active:

    python ml/features_placeholder.py

Feature definitions (intentionally simple -- a real ML2 pass may want
richer logic, e.g. day-of-week-aware growth, but these are honest,
non-fabricated numbers computed directly from fact_network_activity):

  avg_activity       mean total_activity across all observed hours
  activity_growth    (avg on the LAST observed date - avg on the FIRST
                      observed date) / avg on the FIRST observed date
  active_hours       count of hours with total_activity > 0
  peak_ratio         max hourly total_activity / avg_activity
  variability        coefficient of variation (std / mean) of total_activity
  internet_share     mean(internet_activity) / mean(total_activity)
  feature_timestamp  the warehouse's AS_OF (MAX(dim_time.ts)) at the
                     moment this script ran -- i.e. what data this
                     snapshot reflects
  data_quality_status "ok" if the grid has at least MIN_HOURS_FOR_QUALITY
                      observed hours, else "insufficient_data"
  row_count          total fact rows for this grid (quality/freshness signal)
"""
import os
import sqlite3

from app.db import DB_PATH

MIN_HOURS_FOR_QUALITY = 24  # at least one full day of hourly observations


def _ensure_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS grid_features (
            grid_id INTEGER PRIMARY KEY,
            avg_activity REAL NOT NULL,
            activity_growth REAL,
            active_hours INTEGER NOT NULL,
            peak_ratio REAL,
            variability REAL,
            internet_share REAL,
            feature_timestamp TEXT NOT NULL,
            data_quality_status TEXT NOT NULL,
            row_count INTEGER NOT NULL,
            FOREIGN KEY (grid_id) REFERENCES dim_grid(grid_id)
        )
        """
    )
    conn.commit()


def build_features():
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"Warehouse database not found at {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        _ensure_table(conn)

        as_of_row = conn.execute("SELECT MAX(ts) as max_ts FROM dim_time").fetchone()
        feature_timestamp = as_of_row["max_ts"]
        if feature_timestamp is None:
            raise ValueError("dim_time is empty -- nothing to compute features from")

        first_date_row = conn.execute("SELECT MIN(date) as d FROM dim_time").fetchone()
        last_date_row = conn.execute("SELECT MAX(date) as d FROM dim_time").fetchone()
        first_date, last_date = first_date_row["d"], last_date_row["d"]

        base_stats = conn.execute(
            """
            SELECT
                f.grid_id as grid_id,
                COUNT(*) as row_count,
                SUM(CASE WHEN f.total_activity > 0 THEN 1 ELSE 0 END) as active_hours,
                AVG(f.total_activity) as avg_activity,
                MAX(f.total_activity) as max_activity,
                AVG(f.total_activity * f.total_activity) as mean_sq_activity,
                AVG(f.internet_activity) as avg_internet
            FROM fact_network_activity f
            GROUP BY f.grid_id
            """
        ).fetchall()

        first_date_stats = {
            r["grid_id"]: r["avg_val"]
            for r in conn.execute(
                """
                SELECT f.grid_id as grid_id, AVG(f.total_activity) as avg_val
                FROM fact_network_activity f
                JOIN dim_time t ON f.time_key = t.time_key
                WHERE t.date = ?
                GROUP BY f.grid_id
                """,
                (first_date,),
            ).fetchall()
        }
        last_date_stats = {
            r["grid_id"]: r["avg_val"]
            for r in conn.execute(
                """
                SELECT f.grid_id as grid_id, AVG(f.total_activity) as avg_val
                FROM fact_network_activity f
                JOIN dim_time t ON f.time_key = t.time_key
                WHERE t.date = ?
                GROUP BY f.grid_id
                """,
                (last_date,),
            ).fetchall()
        }

        rows_to_insert = []
        for r in base_stats:
            grid_id = r["grid_id"]
            avg_activity = r["avg_activity"] or 0.0
            row_count = r["row_count"]
            active_hours = r["active_hours"] or 0

            variance = max((r["mean_sq_activity"] or 0.0) - avg_activity * avg_activity, 0.0)
            std_activity = variance ** 0.5
            variability = (std_activity / avg_activity) if avg_activity else None

            peak_ratio = (r["max_activity"] / avg_activity) if avg_activity else None
            internet_share = (r["avg_internet"] / avg_activity) if avg_activity else None

            first_avg = first_date_stats.get(grid_id)
            last_avg = last_date_stats.get(grid_id)
            if first_avg and first_avg > 0 and last_avg is not None:
                activity_growth = (last_avg - first_avg) / first_avg
            else:
                activity_growth = None

            data_quality_status = "ok" if row_count >= MIN_HOURS_FOR_QUALITY else "insufficient_data"

            rows_to_insert.append(
                (
                    grid_id,
                    avg_activity,
                    activity_growth,
                    active_hours,
                    peak_ratio,
                    variability,
                    internet_share,
                    feature_timestamp,
                    data_quality_status,
                    row_count,
                )
            )

        conn.execute("DELETE FROM grid_features")
        conn.executemany(
            """
            INSERT INTO grid_features
                (grid_id, avg_activity, activity_growth, active_hours, peak_ratio,
                 variability, internet_share, feature_timestamp, data_quality_status, row_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows_to_insert,
        )
        conn.commit()

        print(f"Wrote {len(rows_to_insert):,} rows to grid_features")
        print(f"feature_timestamp = {feature_timestamp}")
        n_ok = sum(1 for r in rows_to_insert if r[8] == "ok")
        print(f"data_quality_status: ok={n_ok:,}, insufficient_data={len(rows_to_insert) - n_ok:,}")
    finally:
        conn.close()


if __name__ == "__main__":
    build_features()
