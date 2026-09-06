"""
ML2 — Network Activity Feature Engineering
Phase 6, Network Operations Predictive Intelligence Project

Purpose
-------
Create leakage-safe historical network features for future high-activity
prediction.

Feature timestamp:
    t

Prediction target later in ML3:
    t + 1

No information after t is used by this module.

Feature definitions
-------------------
avg_activity
    Mean total_activity over the trailing 24-hour window ending at t.

activity_growth
    (recent_24h_avg - previous_24h_avg) / previous_24h_avg

active_hours
    Number of observed hours in the trailing 24-hour window where
    total_activity > 0.

peak_ratio
    max(total_activity) / avg_activity over trailing 24 hours.

variability
    Population coefficient of variation:
    std(total_activity) / avg_activity

internet_share
    sum(internet_activity) / sum(total_activity)

Outputs
-------
network_feature_table
    Historical feature rows:
        one row per grid_id + feature_timestamp

grid_features
    Latest feature row for each grid.
    This preserves the Phase 4 API4 contract.
"""

from collections import deque
from datetime import datetime, timedelta
import os
import sqlite3

from app.db import DB_PATH


RECENT_HOURS = 24
BASELINE_HOURS = 24

MIN_RECENT_ROWS = 24
MIN_BASELINE_ROWS = 24

TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


def _ensure_tables(conn):
    """
    Historical ML feature table.

    grid_features already exists from Phase 4 and its schema must remain
    compatible with API4.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS network_feature_table (
            grid_id INTEGER NOT NULL,
            avg_activity REAL,
            activity_growth REAL,
            active_hours INTEGER NOT NULL,
            peak_ratio REAL,
            variability REAL,
            internet_share REAL,
            feature_timestamp TEXT NOT NULL,
            data_quality_status TEXT NOT NULL,
            row_count INTEGER NOT NULL,
            PRIMARY KEY (grid_id, feature_timestamp),
            FOREIGN KEY (grid_id) REFERENCES dim_grid(grid_id)
        )
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_network_feature_timestamp
        ON network_feature_table(feature_timestamp)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_network_feature_grid
        ON network_feature_table(grid_id)
        """
    )

    # Preserve the exact API4-facing schema.
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


def _safe_ratio(numerator, denominator):
    """
    Explicit divide-by-zero handling.

    Returning None is safer than fabricating a zero ratio when the
    denominator itself contains no meaningful activity.
    """
    if denominator is None or denominator == 0:
        return None
    return numerator / denominator


def _mean(rows, key):
    if not rows:
        return None

    values = [row[key] for row in rows]
    return sum(values) / len(values)


def _calculate_recent_features(recent_rows):
    """
    Calculate all features except activity_growth from the recent
    trailing 24-hour window.
    """
    row_count = len(recent_rows)

    if row_count == 0:
        return {
            "avg_activity": None,
            "active_hours": 0,
            "peak_ratio": None,
            "variability": None,
            "internet_share": None,
            "row_count": 0,
        }

    activity_values = [row["total_activity"] for row in recent_rows]

    total_activity = sum(activity_values)
    avg_activity = total_activity / row_count

    active_hours = sum(1 for value in activity_values if value > 0)

    max_activity = max(activity_values)

    peak_ratio = _safe_ratio(max_activity, avg_activity)

    mean_square = sum(value * value for value in activity_values) / row_count
    variance = max(mean_square - (avg_activity * avg_activity), 0.0)
    std_activity = variance ** 0.5

    variability = _safe_ratio(std_activity, avg_activity)

    internet_total = sum(row["internet_activity"] for row in recent_rows)
    internet_share = _safe_ratio(internet_total, total_activity)

    return {
        "avg_activity": avg_activity,
        "active_hours": active_hours,
        "peak_ratio": peak_ratio,
        "variability": variability,
        "internet_share": internet_share,
        "row_count": row_count,
    }


def _calculate_growth(recent_rows, baseline_rows):
    """
    Growth compares two completely historical windows:

        previous 24h -> baseline
        recent 24h   -> ending at t

    No t+1 information is involved.
    """
    recent_avg = _mean(recent_rows, "total_activity")
    baseline_avg = _mean(baseline_rows, "total_activity")

    if recent_avg is None or baseline_avg is None or baseline_avg == 0:
        return None

    return (recent_avg - baseline_avg) / baseline_avg


def _quality_status(recent_rows, baseline_rows):
    """
    'ok' requires complete recent and baseline windows.

    This gives ML3 a clean way to exclude incomplete observations.
    """
    if (
        len(recent_rows) >= MIN_RECENT_ROWS
        and len(baseline_rows) >= MIN_BASELINE_ROWS
    ):
        return "ok"

    return "insufficient_data"


def _window_rows(history, start_ts, end_ts):
    """
    Return observations within an inclusive hourly timestamp range.

    This is timestamp-based rather than simply taking the last N rows,
    which prevents a missing source hour from silently changing what
    '24 hours' means.
    """
    return [
        row
        for row in history
        if start_ts <= row["timestamp"] <= end_ts
    ]


def _build_grid_rows(grid_rows):
    """
    Generate one historical feature row for every observed timestamp
    for one grid.

    For feature timestamp t:

        recent:
            t - 23h ... t

        baseline:
            t - 47h ... t - 24h
    """
    history = deque()
    output_rows = []

    for source_row in grid_rows:
        current_ts = datetime.strptime(
            source_row["ts"],
            TIMESTAMP_FORMAT,
        )

        history.append(
            {
                "timestamp": current_ts,
                "total_activity": float(source_row["total_activity"] or 0.0),
                "internet_activity": float(source_row["internet_activity"] or 0.0),
            }
        )

        oldest_allowed = current_ts - timedelta(hours=47)

        while history and history[0]["timestamp"] < oldest_allowed:
            history.popleft()

        recent_start = current_ts - timedelta(hours=23)
        recent_end = current_ts

        baseline_start = current_ts - timedelta(hours=47)
        baseline_end = current_ts - timedelta(hours=24)

        recent_rows = _window_rows(
            history,
            recent_start,
            recent_end,
        )

        baseline_rows = _window_rows(
            history,
            baseline_start,
            baseline_end,
        )

        features = _calculate_recent_features(recent_rows)

        activity_growth = _calculate_growth(
            recent_rows,
            baseline_rows,
        )

        data_quality_status = _quality_status(
            recent_rows,
            baseline_rows,
        )

        output_rows.append(
            (
                source_row["grid_id"],
                features["avg_activity"],
                activity_growth,
                features["active_hours"],
                features["peak_ratio"],
                features["variability"],
                features["internet_share"],
                source_row["ts"],
                data_quality_status,
                features["row_count"],
            )
        )

    return output_rows


def build_features():
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(
            f"Warehouse database not found at {DB_PATH}"
        )

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        _ensure_tables(conn)

        print("ML2 feature engineering started")
        print(f"Warehouse: {DB_PATH}")
        print(f"Recent feature window: {RECENT_HOURS} hours")
        print(f"Prior baseline window: {BASELINE_HOURS} hours")

        source_cursor = conn.execute(
            """
            SELECT
                f.grid_id,
                t.ts,
                f.total_activity,
                f.internet_activity
            FROM fact_network_activity f
            JOIN dim_time t
                ON t.time_key = f.time_key
            ORDER BY
                f.grid_id,
                t.ts
            """
        )

        conn.execute("DELETE FROM network_feature_table")
        conn.commit()

        insert_sql = """
            INSERT INTO network_feature_table (
                grid_id,
                avg_activity,
                activity_growth,
                active_hours,
                peak_ratio,
                variability,
                internet_share,
                feature_timestamp,
                data_quality_status,
                row_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        current_grid = None
        grid_rows = []

        grids_processed = 0
        feature_rows_written = 0

        def flush_grid(rows):
            nonlocal grids_processed
            nonlocal feature_rows_written

            if not rows:
                return

            generated = _build_grid_rows(rows)

            conn.executemany(
                insert_sql,
                generated,
            )

            grids_processed += 1
            feature_rows_written += len(generated)

            if grids_processed % 500 == 0:
                conn.commit()
                print(
                    f"Processed {grids_processed:,} grids "
                    f"and {feature_rows_written:,} historical feature rows"
                )

        for row in source_cursor:
            grid_id = row["grid_id"]

            if current_grid is None:
                current_grid = grid_id

            if grid_id != current_grid:
                flush_grid(grid_rows)
                grid_rows = []
                current_grid = grid_id

            grid_rows.append(row)

        flush_grid(grid_rows)

        conn.commit()

        # -------------------------------------------------------------
        # Refresh API4 latest snapshot from historical ML feature table.
        # -------------------------------------------------------------
        conn.execute("DELETE FROM grid_features")

        conn.execute(
            """
            INSERT INTO grid_features (
                grid_id,
                avg_activity,
                activity_growth,
                active_hours,
                peak_ratio,
                variability,
                internet_share,
                feature_timestamp,
                data_quality_status,
                row_count
            )
            SELECT
                nft.grid_id,
                COALESCE(nft.avg_activity, 0.0),
                nft.activity_growth,
                nft.active_hours,
                nft.peak_ratio,
                nft.variability,
                nft.internet_share,
                nft.feature_timestamp,
                nft.data_quality_status,
                nft.row_count
            FROM network_feature_table nft
            JOIN (
                SELECT
                    grid_id,
                    MAX(feature_timestamp) AS max_feature_timestamp
                FROM network_feature_table
                GROUP BY grid_id
            ) latest
                ON latest.grid_id = nft.grid_id
               AND latest.max_feature_timestamp = nft.feature_timestamp
            """
        )

        conn.commit()

        summary = conn.execute(
            """
            SELECT
                COUNT(*) AS feature_rows,
                COUNT(DISTINCT grid_id) AS grids,
                MIN(feature_timestamp) AS min_ts,
                MAX(feature_timestamp) AS max_ts,
                SUM(
                    CASE
                        WHEN data_quality_status = 'ok'
                        THEN 1 ELSE 0
                    END
                ) AS quality_ok
            FROM network_feature_table
            """
        ).fetchone()

        latest_count = conn.execute(
            "SELECT COUNT(*) FROM grid_features"
        ).fetchone()[0]

        print()
        print("ML2 feature engineering complete")
        print(f"Historical feature rows : {summary['feature_rows']:,}")
        print(f"Distinct grids          : {summary['grids']:,}")
        print(f"Feature range           : {summary['min_ts']} -> {summary['max_ts']}")
        print(f"Quality OK rows         : {summary['quality_ok']:,}")
        print(f"Latest API4 rows        : {latest_count:,}")

    finally:
        conn.close()


if __name__ == "__main__":
    build_features()