from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    precision_score,
    recall_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from app.db import DB_PATH


FEATURE_COLUMNS = [
    "avg_activity",
    "activity_growth",
    "active_hours",
    "peak_ratio",
    "variability",
    "internet_share",
]

TRAIN_END = "2013-11-06 22:00:00"
TEST_START = "2013-11-06 23:00:00"
TEST_END = "2013-11-07 22:00:00"

TARGET_PERCENTILE = 90

MODEL_DIR = Path("models")
MODEL_PATH = MODEL_DIR / "network_risk_model.joblib"
REPORT_PATH = MODEL_DIR / "ml3_evaluation.json"


def load_labeled_dataset(conn: sqlite3.Connection) -> pd.DataFrame:
    query = """
    SELECT
        nft.grid_id,
        nft.feature_timestamp,
        nft.avg_activity,
        nft.activity_growth,
        nft.active_hours,
        nft.peak_ratio,
        nft.variability,
        nft.internet_share,
        f.total_activity AS next_hour_total_activity
    FROM network_feature_table nft
    JOIN dim_time nt
        ON nt.ts = datetime(nft.feature_timestamp, '+1 hour')
    JOIN fact_network_activity f
        ON f.grid_id = nft.grid_id
       AND f.time_key = nt.time_key
    WHERE nft.data_quality_status = 'ok'
      AND nft.feature_timestamp <= ?
    ORDER BY nft.feature_timestamp, nft.grid_id
    """

    return pd.read_sql_query(
        query,
        conn,
        params=[TEST_END],
        parse_dates=["feature_timestamp"],
    )


def chronological_split(df: pd.DataFrame):
    train_mask = df["feature_timestamp"] <= pd.Timestamp(TRAIN_END)

    test_mask = (
        (df["feature_timestamp"] >= pd.Timestamp(TEST_START))
        & (df["feature_timestamp"] <= pd.Timestamp(TEST_END))
    )

    train_df = df.loc[train_mask].copy()
    test_df = df.loc[test_mask].copy()

    return train_df, test_df


def calculate_training_threshold(train_df: pd.DataFrame) -> float:
    return float(
        np.percentile(
            train_df["next_hour_total_activity"],
            TARGET_PERCENTILE,
        )
    )


def create_labels(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    threshold: float,
):
    train_df["high_activity_next_hour"] = (
        train_df["next_hour_total_activity"] > threshold
    ).astype(int)

    test_df["high_activity_next_hour"] = (
        test_df["next_hour_total_activity"] > threshold
    ).astype(int)

    return train_df, test_df


def validate_split(train_df: pd.DataFrame, test_df: pd.DataFrame):
    train_max = train_df["feature_timestamp"].max()
    test_min = test_df["feature_timestamp"].min()

    if train_max >= test_min:
        raise RuntimeError(
            f"Chronological split overlap detected: "
            f"train max={train_max}, test min={test_min}"
        )

    print()
    print("Chronological split validation")
    print("------------------------------")
    print("Train start :", train_df["feature_timestamp"].min())
    print("Train end   :", train_max)
    print("Test start  :", test_min)
    print("Test end    :", test_df["feature_timestamp"].max())
    print("Split check : PASS")


def train_model(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
):
    X_train = train_df[FEATURE_COLUMNS]
    y_train = train_df["high_activity_next_hour"]

    X_test = test_df[FEATURE_COLUMNS]
    y_test = test_df["high_activity_next_hour"]

    pipeline = Pipeline(
        steps=[
            (
                "imputer",
                SimpleImputer(strategy="median"),
            ),
            (
                "scaler",
                StandardScaler(),
            ),
            (
                "classifier",
                LogisticRegression(
                    max_iter=1000,
                    random_state=42,
                ),
            ),
        ]
    )

    print()
    print("Training Logistic Regression...")
    pipeline.fit(X_train, y_train)

    predictions = pipeline.predict(X_test)
    probabilities = pipeline.predict_proba(X_test)[:, 1]

    return pipeline, y_test, predictions, probabilities


def evaluate_model(
    y_test,
    predictions,
):
    accuracy = accuracy_score(y_test, predictions)
    precision = precision_score(
        y_test,
        predictions,
        zero_division=0,
    )
    recall = recall_score(
        y_test,
        predictions,
        zero_division=0,
    )
    base_rate = float(np.mean(y_test))
    cm = confusion_matrix(y_test, predictions)

    return {
        "accuracy": float(accuracy),
        "precision": float(precision),
        "recall": float(recall),
        "base_rate": base_rate,
        "confusion_matrix": cm.tolist(),
    }


def get_coefficients(model: Pipeline):
    classifier = model.named_steps["classifier"]

    coefficients = classifier.coef_[0]

    result = []

    for feature_name, coefficient in zip(
        FEATURE_COLUMNS,
        coefficients,
    ):
        result.append(
            {
                "feature": feature_name,
                "coefficient": float(coefficient),
            }
        )

    return sorted(
        result,
        key=lambda item: abs(item["coefficient"]),
        reverse=True,
    )


def main():
    print("ML3 training started")
    print("Warehouse:", DB_PATH)

    conn = sqlite3.connect(DB_PATH)

    try:
        df = load_labeled_dataset(conn)
    finally:
        conn.close()

    print()
    print("Labeled dataset")
    print("----------------")
    print("Rows              :", len(df))
    print("Distinct timestamps:", df["feature_timestamp"].nunique())
    print("Start             :", df["feature_timestamp"].min())
    print("End               :", df["feature_timestamp"].max())

    train_df, test_df = chronological_split(df)

    validate_split(train_df, test_df)

    threshold = calculate_training_threshold(train_df)

    print()
    print("Target definition")
    print("-----------------")
    print("Proxy target percentile :", TARGET_PERCENTILE)
    print("Training-only threshold :", threshold)
    print(
        "Label rule             : next_hour_total_activity > threshold"
    )

    train_df, test_df = create_labels(
        train_df,
        test_df,
        threshold,
    )

    train_base_rate = float(
        train_df["high_activity_next_hour"].mean()
    )
    test_base_rate = float(
        test_df["high_activity_next_hour"].mean()
    )

    print()
    print("Class balance")
    print("-------------")
    print("Train rows      :", len(train_df))
    print("Train positives :", int(train_df["high_activity_next_hour"].sum()))
    print("Train base rate :", train_base_rate)

    print("Test rows       :", len(test_df))
    print("Test positives  :", int(test_df["high_activity_next_hour"].sum()))
    print("Test base rate  :", test_base_rate)

    model, y_test, predictions, probabilities = train_model(
        train_df,
        test_df,
    )

    metrics = evaluate_model(
        y_test,
        predictions,
    )

    coefficients = get_coefficients(model)

    print()
    print("ML3 evaluation")
    print("--------------")
    print("Accuracy  :", metrics["accuracy"])
    print("Base rate :", metrics["base_rate"])
    print("Precision :", metrics["precision"])
    print("Recall    :", metrics["recall"])
    print("Confusion matrix:")
    print(metrics["confusion_matrix"])

    print()
    print("Logistic Regression coefficients")
    print("--------------------------------")
    for item in coefficients:
        print(
            f"{item['feature']:20s} "
            f"{item['coefficient']:+.6f}"
        )

    if metrics["accuracy"] > 0.95:
        print()
        print(
            "WARNING: accuracy exceeds 95%. "
            "Investigate leakage or target circularity "
            "before accepting this model."
        )

    MODEL_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    artifact = {
        "model": model,
        "feature_names": FEATURE_COLUMNS,
        "target_name": "high_activity_next_hour",
        "target_percentile": TARGET_PERCENTILE,
        "target_threshold": threshold,
        "model_version": "ml3-logreg-v1",
        "train_start": str(
            train_df["feature_timestamp"].min()
        ),
        "train_end": str(
            train_df["feature_timestamp"].max()
        ),
        "test_start": str(
            test_df["feature_timestamp"].min()
        ),
        "test_end": str(
            test_df["feature_timestamp"].max()
        ),
    }

    joblib.dump(
        artifact,
        MODEL_PATH,
    )

    report = {
        "model_version": "ml3-logreg-v1",
        "algorithm": "LogisticRegression",
        "feature_names": FEATURE_COLUMNS,
        "target": {
            "name": "high_activity_next_hour",
            "percentile": TARGET_PERCENTILE,
            "threshold": threshold,
            "meaning": (
                "Positive means investigate unusually "
                "high activity in the next hour. "
                "It does not mean confirmed congestion."
            ),
        },
        "train": {
            "start": str(
                train_df["feature_timestamp"].min()
            ),
            "end": str(
                train_df["feature_timestamp"].max()
            ),
            "rows": len(train_df),
            "base_rate": train_base_rate,
        },
        "test": {
            "start": str(
                test_df["feature_timestamp"].min()
            ),
            "end": str(
                test_df["feature_timestamp"].max()
            ),
            "rows": len(test_df),
            "base_rate": test_base_rate,
        },
        "metrics": metrics,
        "coefficients": coefficients,
        "limitations": [
            (
                "Only seven days of warehouse source "
                "history are currently available."
            ),
            (
                "The high-activity label is a statistical "
                "proxy and is not a physical capacity or "
                "congestion label."
            ),
        ],
    }

    with REPORT_PATH.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            report,
            f,
            indent=2,
        )

    print()
    print("Artifacts")
    print("---------")
    print("Model  :", MODEL_PATH)
    print("Report :", REPORT_PATH)

    print()
    print("ML3 baseline training complete")


if __name__ == "__main__":
    main()