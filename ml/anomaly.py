"""
ML4 - Explainable Hour-of-Day Anomaly Baseline

Compares each grid's current activity with its own historical behaviour
at the SAME hour of day.

This is intentionally simple and explainable.

Example:
    activity at 03:00 today

is compared with:

    activity at 03:00 on previous days

rather than with every hour mixed together.

Both unusually HIGH and unusually LOW activity are retained.
"""

from __future__ import annotations

import sqlite3

from app.db import DB_PATH
from app.services.activity_baseline_service import (
    get_activity_baselines,
)


ANOMALY_THRESHOLD = 2.0
MIN_BASELINE_SAMPLES = 2


def get_latest_as_of(conn: sqlite3.Connection) -> str:
    row = conn.execute(
        """
        SELECT MAX(ts) AS as_of
        FROM dim_time
        """
    ).fetchone()

    if row is None or row["as_of"] is None:
        raise RuntimeError(
            "Cannot calculate ML4 anomalies: "
            "dim_time contains no timestamps."
        )

    return row["as_of"]


def ensure_output_table(conn: sqlite3.Connection):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS network_anomaly_scores (
            grid_id INTEGER NOT NULL,
            timestamp TEXT NOT NULL,

            current_activity REAL NOT NULL,
            baseline_activity REAL NOT NULL,
            baseline_std REAL NOT NULL,
            baseline_sample_count INTEGER NOT NULL,

            anomaly_score REAL NOT NULL,
            direction TEXT NOT NULL,
            is_anomaly INTEGER NOT NULL,

            reason TEXT NOT NULL,

            PRIMARY KEY (grid_id, timestamp)
        )
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_network_anomaly_scores_timestamp
        ON network_anomaly_scores(timestamp)
        """
    )


def score_current_snapshot(
    conn: sqlite3.Connection,
    as_of: str,
):
    """
    Score all grids at one timestamp.

    Historical baseline:
        same grid
        same hour-of-day
        timestamps STRICTLY before as_of

    anomaly_score:
        standardized deviation / z-score

        (current - baseline_mean) / baseline_std

    direction:
        high if score > 0
        low  if score < 0

    anomaly:
        abs(score) >= ANOMALY_THRESHOLD
    """

    baselines = get_activity_baselines(
        conn,
        as_of,
        bucket="hour_of_day",
    )

    current_rows = conn.execute(
        """
        SELECT
            f.grid_id,
            t.ts,
            f.total_activity
        FROM fact_network_activity f
        JOIN dim_time t
            ON f.time_key = t.time_key
        WHERE t.ts = ?
        ORDER BY f.grid_id
        """,
        (as_of,),
    ).fetchall()

    results = []

    for row in current_rows:
        grid_id = row["grid_id"]
        current_activity = float(
            row["total_activity"]
        )

        baseline = baselines.get(grid_id)

        if baseline is None:
            continue

        sample_count = baseline["count"]
        baseline_mean = baseline["mean"]
        baseline_std = baseline["std"]

        # More than one historical day must contribute.
        if sample_count < MIN_BASELINE_SAMPLES:
            continue

        # A zero standard deviation means every historical
        # comparable hour had exactly the same activity.
        # Standardized deviation is undefined in that case.
        if baseline_std == 0:
            continue

        anomaly_score = (
            current_activity - baseline_mean
        ) / baseline_std

        if anomaly_score > 0:
            direction = "high"
        elif anomaly_score < 0:
            direction = "low"
        else:
            direction = "normal"

        is_anomaly = int(
            abs(anomaly_score) >= ANOMALY_THRESHOLD
        )

        if is_anomaly:
            reason = (
                f"Activity is {abs(anomaly_score):.1f} standard "
                f"deviations {direction} compared with this grid's "
                f"historical activity at the same hour of day "
                f"({baseline_mean:.1f})."
            )
        else:
            reason = (
                f"Activity is within the expected historical range "
                f"for this grid at the same hour of day "
                f"({baseline_mean:.1f})."
            )

        results.append(
            {
                "grid_id": grid_id,
                "timestamp": row["ts"],
                "current_activity": current_activity,
                "baseline_activity": baseline_mean,
                "baseline_std": baseline_std,
                "baseline_sample_count": sample_count,
                "anomaly_score": anomaly_score,
                "direction": direction,
                "is_anomaly": is_anomaly,
                "reason": reason,
            }
        )

    return results


def persist_scores(
    conn: sqlite3.Connection,
    as_of: str,
    scores,
):
    # Rebuilding this timestamp makes repeated execution
    # deterministic and duplicate-safe.
    conn.execute(
        """
        DELETE FROM network_anomaly_scores
        WHERE timestamp = ?
        """,
        (as_of,),
    )

    conn.executemany(
        """
        INSERT INTO network_anomaly_scores (
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
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                item["grid_id"],
                item["timestamp"],
                item["current_activity"],
                item["baseline_activity"],
                item["baseline_std"],
                item["baseline_sample_count"],
                item["anomaly_score"],
                item["direction"],
                item["is_anomaly"],
                item["reason"],
            )
            for item in scores
        ],
    )


def print_summary(scores, as_of: str):
    high = [
        item
        for item in scores
        if item["is_anomaly"]
        and item["direction"] == "high"
    ]

    low = [
        item
        for item in scores
        if item["is_anomaly"]
        and item["direction"] == "low"
    ]

    print()
    print("ML4 anomaly scoring")
    print("===================")
    print("As of                  :", as_of)
    print("Scored grids           :", len(scores))
    print("High anomalies         :", len(high))
    print("Low anomalies          :", len(low))

    if scores:
        counts = [
            item["baseline_sample_count"]
            for item in scores
        ]

        print(
            "Min baseline samples   :",
            min(counts),
        )

        print(
            "Max baseline samples   :",
            max(counts),
        )

    print()
    print("Top HIGH anomalies")
    print("------------------")

    for item in sorted(
        high,
        key=lambda x: x["anomaly_score"],
        reverse=True,
    )[:5]:
        print(
            f"grid={item['grid_id']} "
            f"current={item['current_activity']:.4f} "
            f"baseline={item['baseline_activity']:.4f} "
            f"score={item['anomaly_score']:.4f} "
            f"samples={item['baseline_sample_count']}"
        )

    print()
    print("Top LOW anomalies")
    print("-----------------")

    for item in sorted(
        low,
        key=lambda x: x["anomaly_score"],
    )[:5]:
        print(
            f"grid={item['grid_id']} "
            f"current={item['current_activity']:.4f} "
            f"baseline={item['baseline_activity']:.4f} "
            f"score={item['anomaly_score']:.4f} "
            f"samples={item['baseline_sample_count']}"
        )


def main():
    print("ML4 started")
    print("Warehouse:", DB_PATH)
    print(
        "Anomaly threshold:",
        f"+/- {ANOMALY_THRESHOLD} standard deviations",
    )

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        ensure_output_table(conn)

        as_of = get_latest_as_of(conn)

        scores = score_current_snapshot(
            conn,
            as_of,
        )

        persist_scores(
            conn,
            as_of,
            scores,
        )

        conn.commit()

        print_summary(
            scores,
            as_of,
        )

    finally:
        conn.close()

    print()
    print("Output table: network_anomaly_scores")
    print("ML4 anomaly scoring complete")


if __name__ == "__main__":
    main()