from __future__ import annotations

import sqlite3

import joblib
import numpy as np
import pandas as pd

from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
)

from app.db import DB_PATH


MODEL_PATH = "models/network_risk_model.joblib"

TEST_START = "2013-11-06 23:00:00"
TEST_END = "2013-11-07 22:00:00"

Z_THRESHOLD_MEDIUM = 2.0

FEATURE_COLUMNS = [
    "avg_activity",
    "activity_growth",
    "active_hours",
    "peak_ratio",
    "variability",
    "internet_share",
]


def load_model():
    artifact = joblib.load(MODEL_PATH)

    return (
        artifact["model"],
        artifact["target_threshold"],
        artifact["model_version"],
    )


def load_ml_test_data(conn):
    query = """
    SELECT
        nft.grid_id,
        nft.feature_timestamp,
        datetime(
            nft.feature_timestamp,
            '+1 hour'
        ) AS label_timestamp,

        nft.avg_activity,
        nft.activity_growth,
        nft.active_hours,
        nft.peak_ratio,
        nft.variability,
        nft.internet_share,

        f.total_activity AS next_hour_total_activity

    FROM network_feature_table nft

    JOIN dim_time nt
        ON nt.ts = datetime(
            nft.feature_timestamp,
            '+1 hour'
        )

    JOIN fact_network_activity f
        ON f.grid_id = nft.grid_id
       AND f.time_key = nt.time_key

    WHERE nft.data_quality_status = 'ok'
      AND nft.feature_timestamp >= ?
      AND nft.feature_timestamp <= ?

    ORDER BY
        nft.feature_timestamp,
        nft.grid_id
    """

    return pd.read_sql_query(
        query,
        conn,
        params=[TEST_START, TEST_END],
    )


def load_np3_results(conn):
    """
    Reproduce the NP3 service rule exactly:

    baseline = every observation strictly before
               the current hour for that grid

    z = (current - historical_mean) / historical_std

    alert if z >= 2.0
    """

    query = """
    WITH history AS (
        SELECT
            f.grid_id,
            t.ts,

            f.total_activity,

            AVG(f.total_activity) OVER (
                PARTITION BY f.grid_id
                ORDER BY t.ts
                ROWS BETWEEN UNBOUNDED PRECEDING
                         AND 1 PRECEDING
            ) AS baseline_mean,

            AVG(
                f.total_activity * f.total_activity
            ) OVER (
                PARTITION BY f.grid_id
                ORDER BY t.ts
                ROWS BETWEEN UNBOUNDED PRECEDING
                         AND 1 PRECEDING
            ) AS baseline_mean_sq

        FROM fact_network_activity f
        JOIN dim_time t
            ON f.time_key = t.time_key
    ),

    scored AS (
        SELECT
            grid_id,
            ts,
            total_activity,
            baseline_mean,

            CASE
                WHEN baseline_mean IS NULL
                    THEN NULL

                WHEN (
                    baseline_mean_sq
                    - baseline_mean * baseline_mean
                ) <= 0
                    THEN NULL

                ELSE
                    (
                        total_activity
                        - baseline_mean
                    )
                    /
                    SQRT(
                        baseline_mean_sq
                        - baseline_mean * baseline_mean
                    )
            END AS z_score

        FROM history
    )

    SELECT
        grid_id,
        ts AS label_timestamp,
        total_activity,
        baseline_mean,
        z_score

    FROM scored

    WHERE ts >= datetime(?, '+1 hour')
      AND ts <= datetime(?, '+1 hour')

    ORDER BY
        ts,
        grid_id
    """

    return pd.read_sql_query(
        query,
        conn,
        params=[TEST_START, TEST_END],
    )


def show_metrics(name, y_true, y_pred):
    print()
    print(name)
    print("-" * len(name))

    print(
        "Accuracy :",
        accuracy_score(y_true, y_pred),
    )

    print(
        "Precision:",
        precision_score(
            y_true,
            y_pred,
            zero_division=0,
        ),
    )

    print(
        "Recall   :",
        recall_score(
            y_true,
            y_pred,
            zero_division=0,
        ),
    )


def main():
    print("ML3 vs NP3 comparison")
    print("=====================")

    model, target_threshold, model_version = load_model()

    print("Model version :", model_version)
    print("Target threshold:", target_threshold)

    conn = sqlite3.connect(DB_PATH)

    try:
        ml_df = load_ml_test_data(conn)

        print()
        print("Loaded ML test rows:", len(ml_df))

        X_test = ml_df[FEATURE_COLUMNS]

        ml_df["risk_score"] = (
            model.predict_proba(X_test)[:, 1]
        )

        ml_df["ml_prediction"] = (
            model.predict(X_test)
        )

        ml_df["actual_label"] = (
            ml_df["next_hour_total_activity"]
            > target_threshold
        ).astype(int)

        print("Loading NP3 historical z-scores...")

        np3_df = load_np3_results(conn)

    finally:
        conn.close()

    print("Loaded NP3 rows:", len(np3_df))

    np3_df["np3_alert"] = (
        np3_df["z_score"] >= Z_THRESHOLD_MEDIUM
    ).astype(int)

    combined = ml_df.merge(
        np3_df[
            [
                "grid_id",
                "label_timestamp",
                "baseline_mean",
                "z_score",
                "np3_alert",
            ]
        ],
        on=[
            "grid_id",
            "label_timestamp",
        ],
        how="left",
    )

    combined["np3_alert"] = (
        combined["np3_alert"]
        .fillna(0)
        .astype(int)
    )

    print()
    print("Aligned comparison rows:", len(combined))

    print()
    print("Positive counts")
    print("---------------")

    print(
        "Actual high-activity labels :",
        int(combined["actual_label"].sum()),
    )

    print(
        "ML positive predictions     :",
        int(combined["ml_prediction"].sum()),
    )

    print(
        "NP3 alerts                  :",
        int(combined["np3_alert"].sum()),
    )

    both = (
        (combined["ml_prediction"] == 1)
        & (combined["np3_alert"] == 1)
    )

    ml_only = (
        (combined["ml_prediction"] == 1)
        & (combined["np3_alert"] == 0)
    )

    np3_only = (
        (combined["ml_prediction"] == 0)
        & (combined["np3_alert"] == 1)
    )

    neither = (
        (combined["ml_prediction"] == 0)
        & (combined["np3_alert"] == 0)
    )

    print()
    print("ML vs NP3 agreement")
    print("-------------------")

    print("Both positive :", int(both.sum()))
    print("ML only       :", int(ml_only.sum()))
    print("NP3 only      :", int(np3_only.sum()))
    print("Neither       :", int(neither.sum()))

    agreement = (
        combined["ml_prediction"]
        == combined["np3_alert"]
    ).mean()

    print("Agreement rate:", agreement)

    show_metrics(
        "ML against high-activity target",
        combined["actual_label"],
        combined["ml_prediction"],
    )

    show_metrics(
        "NP3 against high-activity target",
        combined["actual_label"],
        combined["np3_alert"],
    )

    print()
    print("Example: ML positive, NP3 not alerting")
    print("--------------------------------------")

    sample = combined.loc[
        ml_only,
        [
            "grid_id",
            "feature_timestamp",
            "label_timestamp",
            "next_hour_total_activity",
            "risk_score",
            "z_score",
            "actual_label",
        ],
    ].head(5)

    print(sample.to_string(index=False))

    print()
    print("Example: NP3 alert, ML negative")
    print("--------------------------------")

    sample = combined.loc[
        np3_only,
        [
            "grid_id",
            "feature_timestamp",
            "label_timestamp",
            "next_hour_total_activity",
            "risk_score",
            "z_score",
            "actual_label",
        ],
    ].head(5)

    print(sample.to_string(index=False))

    print()
    print("Interpretation reminder")
    print("-----------------------")
    print(
        "ML predicts future absolute high activity."
    )
    print(
        "NP3 detects unusual activity relative to "
        "each grid's own historical baseline."
    )
    print(
        "Disagreement does not automatically mean "
        "one method is wrong."
    )


if __name__ == "__main__":
    main()