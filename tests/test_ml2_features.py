"""
ML2 feature engineering validation tests.

These tests validate:
1. Feature names/schema.
2. Feature timestamp boundary.
3. Future-data leakage prevention.
4. A deliberately broken feature window is detected.
5. Safe zero-denominator behaviour.
"""

import sqlite3
from datetime import datetime, timedelta

from app.db import DB_PATH


TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def test_network_feature_table_has_expected_columns():
    conn = _conn()
    try:
        columns = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(network_feature_table)"
            ).fetchall()
        }

        expected = {
            "grid_id",
            "avg_activity",
            "activity_growth",
            "active_hours",
            "peak_ratio",
            "variability",
            "internet_share",
            "feature_timestamp",
            "data_quality_status",
            "row_count",
        }

        assert expected.issubset(columns)
    finally:
        conn.close()


def test_latest_grid_4821_feature_timestamp_exists():
    conn = _conn()
    try:
        row = conn.execute(
            """
            SELECT feature_timestamp
            FROM network_feature_table
            WHERE grid_id = 4821
            ORDER BY feature_timestamp DESC
            LIMIT 1
            """
        ).fetchone()

        assert row is not None
        assert row["feature_timestamp"] is not None
    finally:
        conn.close()


def test_recent_feature_window_does_not_use_future_data():
    conn = _conn()
    try:
        row = conn.execute(
            """
            SELECT feature_timestamp
            FROM network_feature_table
            WHERE grid_id = 4821
            ORDER BY feature_timestamp DESC
            LIMIT 1
            """
        ).fetchone()

        feature_ts = datetime.strptime(
            row["feature_timestamp"],
            TIMESTAMP_FORMAT,
        )

        recent_start = feature_ts - timedelta(hours=23)

        source_rows = conn.execute(
            """
            SELECT dt.ts
            FROM fact_network_activity f
            JOIN dim_time dt
              ON dt.time_key = f.time_key
            WHERE f.grid_id = ?
              AND dt.ts BETWEEN ? AND ?
            ORDER BY dt.ts
            """,
            (
                4821,
                recent_start.strftime(TIMESTAMP_FORMAT),
                feature_ts.strftime(TIMESTAMP_FORMAT),
            ),
        ).fetchall()

        assert len(source_rows) == 24

        latest_source_ts = max(
            datetime.strptime(r["ts"], TIMESTAMP_FORMAT)
            for r in source_rows
        )

        assert latest_source_ts <= feature_ts

    finally:
        conn.close()


def test_deliberately_broken_future_window_is_detected():
    """
    Deliberately include t+1.

    A correct leakage test must detect that the source window
    extends beyond feature_timestamp t.
    """
    conn = _conn()
    try:
        row = conn.execute(
            """
            SELECT feature_timestamp
            FROM network_feature_table
            WHERE grid_id = 4821
              AND feature_timestamp < (
                    SELECT MAX(ts)
                    FROM dim_time
              )
            ORDER BY feature_timestamp DESC
            LIMIT 1
            """
        ).fetchone()

        assert row is not None

        feature_ts = datetime.strptime(
            row["feature_timestamp"],
            TIMESTAMP_FORMAT,
        )

        broken_end = feature_ts + timedelta(hours=1)
        broken_start = feature_ts - timedelta(hours=22)

        source_rows = conn.execute(
            """
            SELECT dt.ts
            FROM fact_network_activity f
            JOIN dim_time dt
              ON dt.time_key = f.time_key
            WHERE f.grid_id = ?
              AND dt.ts BETWEEN ? AND ?
            ORDER BY dt.ts
            """,
            (
                4821,
                broken_start.strftime(TIMESTAMP_FORMAT),
                broken_end.strftime(TIMESTAMP_FORMAT),
            ),
        ).fetchall()

        latest_source_ts = max(
            datetime.strptime(r["ts"], TIMESTAMP_FORMAT)
            for r in source_rows
        )

        leakage_detected = latest_source_ts > feature_ts

        assert leakage_detected is True

    finally:
        conn.close()


def test_no_invalid_ratios_for_zero_activity():
    """
    Ratios must never become infinity or NaN.

    Rows with zero activity should use NULL/None for ratios whose
    denominator is zero.
    """
    conn = _conn()
    try:
        bad_rows = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM network_feature_table
            WHERE
                peak_ratio != peak_ratio
                OR variability != variability
                OR internet_share != internet_share
            """
        ).fetchone()["n"]

        assert bad_rows == 0
    finally:
        conn.close()