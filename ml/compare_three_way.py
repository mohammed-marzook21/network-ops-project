from __future__ import annotations

import sqlite3

import joblib
import pandas as pd

from app.db import DB_PATH
from app.services.activity_baseline_service import (
    get_activity_baselines,
)


MODEL_PATH = "models/network_risk_model.joblib"
AS_OF = "2013-11-07 23:00:00"
FEATURE_TS = "2013-11-07 22:00:00"

FEATURE_COLUMNS = [
    "avg_activity",
    "activity_growth",
    "active_hours",
    "peak_ratio",
    "variability",
    "internet_share",
]

NP3_THRESHOLD = 2.0


def load_ml_predictions(conn):
    artifact = joblib.load(MODEL_PATH)

    model = artifact["model"]

    df = pd.read_sql_query(
        """
        SELECT
            grid_id,
            feature_timestamp,
            avg_activity,
            activity_growth,
            active_hours,
            peak_ratio,
            variability,
            internet_share
        FROM network_feature_table
        WHERE feature_timestamp = ?
          AND data_quality_status = 'ok'
        ORDER BY grid_id
        """,
        conn,
        params=[FEATURE_TS],
    )

    df["ml_risk_score"] = model.predict_proba(
        df[FEATURE_COLUMNS]
    )[:, 1]

    df["ml_positive"] = model.predict(
        df[FEATURE_COLUMNS]
    )

    return df[
        [
            "grid_id",
            "ml_risk_score",
            "ml_positive",
        ]
    ]


def load_ml4(conn):
    return pd.read_sql_query(
        """
        SELECT
            grid_id,
            current_activity,
            baseline_activity AS ml4_baseline,
            anomaly_score,
            direction,
            is_anomaly AS ml4_anomaly
        FROM network_anomaly_scores
        WHERE timestamp = ?
        ORDER BY grid_id
        """,
        conn,
        params=[AS_OF],
    )


def load_np3(conn):
    baselines = get_activity_baselines(
        conn,
        AS_OF,
        bucket="all_history",
    )

    current_rows = conn.execute(
        """
        SELECT
            f.grid_id,
            f.total_activity
        FROM fact_network_activity f
        JOIN dim_time t
            ON f.time_key = t.time_key
        WHERE t.ts = ?
        ORDER BY f.grid_id
        """,
        (AS_OF,),
    ).fetchall()

    rows = []

    for row in current_rows:
        baseline = baselines.get(row["grid_id"])

        if baseline is None:
            continue

        std = baseline["std"]

        if std == 0:
            continue

        z = (
            float(row["total_activity"])
            - baseline["mean"]
        ) / std

        rows.append(
            {
                "grid_id": row["grid_id"],
                "np3_z_score": z,
                "np3_alert": int(
                    z >= NP3_THRESHOLD
                ),
            }
        )

    return pd.DataFrame(rows)


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        ml = load_ml_predictions(conn)
        ml4 = load_ml4(conn)
        np3 = load_np3(conn)

    finally:
        conn.close()

    combined = (
        ml4
        .merge(
            ml,
            on="grid_id",
            how="left",
        )
        .merge(
            np3,
            on="grid_id",
            how="left",
        )
    )

    combined["ml_positive"] = (
        combined["ml_positive"]
        .fillna(0)
        .astype(int)
    )

    combined["np3_alert"] = (
        combined["np3_alert"]
        .fillna(0)
        .astype(int)
    )

    print("ML4 three-way comparison")
    print("========================")

    print("Rows       :", len(combined))
    print(
        "ML3 positive:",
        int(combined["ml_positive"].sum()),
    )
    print(
        "NP3 alerts  :",
        int(combined["np3_alert"].sum()),
    )
    print(
        "ML4 anomalies:",
        int(combined["ml4_anomaly"].sum()),
    )

    print()
    print("ML4 direction counts")
    print("--------------------")

    high = combined[
        (combined["ml4_anomaly"] == 1)
        & (combined["direction"] == "high")
    ]

    low = combined[
        (combined["ml4_anomaly"] == 1)
        & (combined["direction"] == "low")
    ]

    print("High:", len(high))
    print("Low :", len(low))

    print()
    print("Signal combinations")
    print("-------------------")

    counts = (
        combined.groupby(
            [
                "ml_positive",
                "np3_alert",
                "ml4_anomaly",
            ]
        )
        .size()
        .reset_index(name="count")
        .sort_values("count", ascending=False)
    )

    print(counts.to_string(index=False))

    print()
    print("Example: ML4 high + NP3 alert")
    print("----------------------------")

    sample = combined[
        (combined["ml4_anomaly"] == 1)
        & (combined["direction"] == "high")
        & (combined["np3_alert"] == 1)
    ][
        [
            "grid_id",
            "current_activity",
            "ml_risk_score",
            "ml_positive",
            "np3_z_score",
            "anomaly_score",
            "direction",
        ]
    ].head(5)

    print(sample.to_string(index=False))

    print()
    print("Example: ML4 low anomaly only")
    print("----------------------------")

    sample = combined[
        (combined["ml4_anomaly"] == 1)
        & (combined["direction"] == "low")
        & (combined["np3_alert"] == 0)
        & (combined["ml_positive"] == 0)
    ][
        [
            "grid_id",
            "current_activity",
            "ml_risk_score",
            "np3_z_score",
            "anomaly_score",
            "direction",
        ]
    ].head(5)

    print(sample.to_string(index=False))

    print()
    print("Example: ML3 positive, no anomaly")
    print("--------------------------------")

    sample = combined[
        (combined["ml_positive"] == 1)
        & (combined["np3_alert"] == 0)
        & (combined["ml4_anomaly"] == 0)
    ][
        [
            "grid_id",
            "current_activity",
            "ml_risk_score",
            "np3_z_score",
            "anomaly_score",
        ]
    ].head(5)

    print(sample.to_string(index=False))

    print()
    print("Example: NP3 alert, ML4 not anomaly")
    print("----------------------------------")

    sample = combined[
        (combined["np3_alert"] == 1)
        & (combined["ml4_anomaly"] == 0)
    ][
        [
            "grid_id",
            "current_activity",
            "ml_risk_score",
            "ml_positive",
            "np3_z_score",
            "anomaly_score",
        ]
    ].head(5)

    print(sample.to_string(index=False))


if __name__ == "__main__":
    main()