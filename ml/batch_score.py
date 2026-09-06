"""
ML6 batch scoring.

Reads the latest feature snapshot, scores every grid using the trained
ML3 classifier, and publishes network_risk_scores.
"""

from pathlib import Path
import sqlite3

import joblib
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

WAREHOUSE_PATH = ROOT / "warehouse" / "network_analytics.db"
MODEL_PATH = ROOT / "models" / "network_risk_model.joblib"
REPORT_PATH = ROOT / "reports" / "ml6_top20_attention.csv"

FEATURE_COLUMNS = [
    "avg_activity",
    "activity_growth",
    "active_hours",
    "peak_ratio",
    "variability",
    "internet_share",
]


def risk_level_from_score(score: float) -> str:
    if score >= 0.70:
        return "high"
    if score >= 0.30:
        return "medium"
    return "low"


def load_model_artifact():
    if not MODEL_PATH.exists():
        raise RuntimeError(
            f"Model artifact missing: {MODEL_PATH}. "
            "Run ML3 training before ML6 scoring."
        )

    artifact = joblib.load(MODEL_PATH)

    if not isinstance(artifact, dict):
        raise RuntimeError("Invalid model artifact format.")

    required = {"model", "feature_names", "model_version"}
    missing = required - artifact.keys()

    if missing:
        raise RuntimeError(
            "Model artifact missing required keys: "
            + ", ".join(sorted(missing))
        )

    if list(artifact["feature_names"]) != FEATURE_COLUMNS:
        raise RuntimeError(
            "Model feature schema does not match ML2 feature schema."
        )

    return artifact


def ensure_output_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS network_risk_scores (
            grid_id INTEGER NOT NULL,
            timestamp TEXT NOT NULL,
            risk_score REAL NOT NULL,
            risk_level TEXT NOT NULL,
            model_version TEXT NOT NULL,
            reason TEXT NOT NULL,
            PRIMARY KEY (grid_id, timestamp)
        )
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_network_risk_scores_timestamp
        ON network_risk_scores(timestamp)
        """
    )


def load_latest_features(conn):
    latest = conn.execute(
        """
        SELECT MAX(feature_timestamp)
        FROM network_feature_table
        """
    ).fetchone()[0]

    if latest is None:
        raise RuntimeError(
            "No features available in network_feature_table. "
            "Run ML2 feature generation before ML6 scoring."
        )

    query = """
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
    """

    df = pd.read_sql_query(
        query,
        conn,
        params=(latest,),
    )

    if df.empty:
        raise RuntimeError(
            f"No quality-approved features found for latest timestamp {latest}."
        )

    return latest, df


def score_latest_features():
    artifact = load_model_artifact()
    model = artifact["model"]
    model_version = artifact["model_version"]

    conn = sqlite3.connect(WAREHOUSE_PATH)

    try:
        ensure_output_table(conn)

        latest, features = load_latest_features(conn)

        X = features[FEATURE_COLUMNS]

        probabilities = model.predict_proba(X)[:, 1]

        rows = []

        for grid_id, score in zip(
            features["grid_id"],
            probabilities,
        ):
            score = float(score)
            level = risk_level_from_score(score)

            reason = (
                f"Model risk score {score:.3f} ({level}) indicates "
                "operational attention priority; investigate using "
                "network activity, alert, and anomaly evidence."
            )

            rows.append(
                (
                    int(grid_id),
                    latest,
                    score,
                    level,
                    model_version,
                    reason,
                )
            )

        conn.execute(
            """
            DELETE FROM network_risk_scores
            WHERE timestamp = ?
            """,
            (latest,),
        )

        conn.executemany(
            """
            INSERT INTO network_risk_scores (
                grid_id,
                timestamp,
                risk_score,
                risk_level,
                model_version,
                reason
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

        conn.commit()

        print("ML6 batch scoring")
        print("=================")
        print("Timestamp     :", latest)
        print("Scored grids  :", len(rows))
        print("Model version :", model_version)

        counts = conn.execute(
            """
            SELECT risk_level, COUNT(*)
            FROM network_risk_scores
            WHERE timestamp = ?
            GROUP BY risk_level
            ORDER BY risk_level
            """,
            (latest,),
        ).fetchall()

        for level, count in counts:
            print(f"{level:6}: {count}")

        print()
        print("Top 20 operational attention")
        print("----------------------------")

        top_rows = conn.execute(
            """
            SELECT grid_id, risk_score, risk_level, reason
            FROM network_risk_scores
            WHERE timestamp = ?
            ORDER BY risk_score DESC, grid_id ASC
            LIMIT 20
            """,
            (latest,),
        ).fetchall()

        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

        report_df = pd.DataFrame(
            top_rows,
            columns=[
                "grid_id",
                "risk_score",
                "risk_level",
                "reason",
            ],
        )

        report_df.insert(1, "timestamp", latest)
        report_df["model_version"] = model_version

        report_df.to_csv(REPORT_PATH, index=False)

        print()
        print("Attention report:", REPORT_PATH)

        for row in top_rows:
            print(
                f"grid={row[0]} "
                f"score={row[1]:.6f} "
                f"level={row[2]} "
                f"reason={row[3]}"
            )

        return latest, len(rows)

    finally:
        conn.close()


if __name__ == "__main__":
    score_latest_features()