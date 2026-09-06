import sqlite3

import joblib
import pandas as pd
import pytest
from sklearn.linear_model import LogisticRegression

import ml.batch_score as batch_score


FEATURE_COLUMNS = batch_score.FEATURE_COLUMNS


def _create_feature_table(db_path):
    conn = sqlite3.connect(db_path)

    conn.execute(
        """
        CREATE TABLE network_feature_table (
            grid_id INTEGER NOT NULL,
            feature_timestamp TEXT NOT NULL,
            avg_activity REAL,
            activity_growth REAL,
            active_hours INTEGER,
            peak_ratio REAL,
            variability REAL,
            internet_share REAL,
            data_quality_status TEXT NOT NULL
        )
        """
    )

    rows = [
        (
            1,
            "2013-11-07 23:00:00",
            100.0,
            0.10,
            24,
            1.5,
            0.20,
            0.70,
            "ok",
        ),
        (
            2,
            "2013-11-07 23:00:00",
            500.0,
            0.40,
            24,
            2.2,
            0.50,
            0.90,
            "ok",
        ),
        (
            3,
            "2013-11-07 23:00:00",
            300.0,
            0.20,
            23,
            1.8,
            0.30,
            0.80,
            "insufficient_data",
        ),
    ]

    conn.executemany(
        """
        INSERT INTO network_feature_table (
            grid_id,
            feature_timestamp,
            avg_activity,
            activity_growth,
            active_hours,
            peak_ratio,
            variability,
            internet_share,
            data_quality_status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )

    conn.commit()
    conn.close()


def _create_model_artifact(model_path):
    X = pd.DataFrame(
        [
            [50.0, 0.0, 24, 1.2, 0.10, 0.50],
            [100.0, 0.1, 24, 1.5, 0.20, 0.60],
            [500.0, 0.4, 24, 2.2, 0.50, 0.90],
            [700.0, 0.6, 24, 2.8, 0.70, 0.95],
        ],
        columns=FEATURE_COLUMNS,
    )

    y = [0, 0, 1, 1]

    model = LogisticRegression(random_state=42)
    model.fit(X, y)

    artifact = {
        "model": model,
        "feature_names": FEATURE_COLUMNS,
        "model_version": "test-model-v1",
    }

    joblib.dump(artifact, model_path)

    return model


def test_missing_feature_table_fails_cleanly(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    model_path = tmp_path / "model.joblib"
    report_path = tmp_path / "report.csv"

    sqlite3.connect(db_path).close()
    _create_model_artifact(model_path)

    monkeypatch.setattr(batch_score, "WAREHOUSE_PATH", db_path)
    monkeypatch.setattr(batch_score, "MODEL_PATH", model_path)
    monkeypatch.setattr(batch_score, "REPORT_PATH", report_path)

    with pytest.raises(
        RuntimeError,
        match="network_feature_table does not exist",
    ):
        batch_score.score_latest_features()


def test_scoring_writes_one_row_per_quality_grid_with_model_version(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "warehouse.db"
    model_path = tmp_path / "model.joblib"
    report_path = tmp_path / "report.csv"

    _create_feature_table(db_path)
    _create_model_artifact(model_path)

    monkeypatch.setattr(batch_score, "WAREHOUSE_PATH", db_path)
    monkeypatch.setattr(batch_score, "MODEL_PATH", model_path)
    monkeypatch.setattr(batch_score, "REPORT_PATH", report_path)

    latest, count = batch_score.score_latest_features()

    assert latest == "2013-11-07 23:00:00"
    assert count == 2

    conn = sqlite3.connect(db_path)

    rows = conn.execute(
        """
        SELECT
            grid_id,
            timestamp,
            risk_score,
            risk_level,
            model_version
        FROM network_risk_scores
        ORDER BY grid_id
        """
    ).fetchall()

    duplicate_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT grid_id, timestamp
            FROM network_risk_scores
            GROUP BY grid_id, timestamp
            HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]

    conn.close()

    assert len(rows) == 2
    assert duplicate_count == 0
    assert {row[0] for row in rows} == {1, 2}
    assert all(row[1] == latest for row in rows)
    assert all(row[4] == "test-model-v1" for row in rows)


def test_rerunning_same_snapshot_does_not_duplicate(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "warehouse.db"
    model_path = tmp_path / "model.joblib"
    report_path = tmp_path / "report.csv"

    _create_feature_table(db_path)
    _create_model_artifact(model_path)

    monkeypatch.setattr(batch_score, "WAREHOUSE_PATH", db_path)
    monkeypatch.setattr(batch_score, "MODEL_PATH", model_path)
    monkeypatch.setattr(batch_score, "REPORT_PATH", report_path)

    batch_score.score_latest_features()
    batch_score.score_latest_features()

    conn = sqlite3.connect(db_path)

    row_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM network_risk_scores
        """
    ).fetchone()[0]

    duplicate_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT grid_id, timestamp
            FROM network_risk_scores
            GROUP BY grid_id, timestamp
            HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]

    conn.close()

    assert row_count == 2
    assert duplicate_count == 0


def test_stored_score_matches_direct_model_inference(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "warehouse.db"
    model_path = tmp_path / "model.joblib"
    report_path = tmp_path / "report.csv"

    _create_feature_table(db_path)
    model = _create_model_artifact(model_path)

    monkeypatch.setattr(batch_score, "WAREHOUSE_PATH", db_path)
    monkeypatch.setattr(batch_score, "MODEL_PATH", model_path)
    monkeypatch.setattr(batch_score, "REPORT_PATH", report_path)

    batch_score.score_latest_features()

    conn = sqlite3.connect(db_path)

    stored_score = conn.execute(
        """
        SELECT risk_score
        FROM network_risk_scores
        WHERE grid_id = 2
          AND timestamp = '2013-11-07 23:00:00'
        """
    ).fetchone()[0]

    conn.close()

    X = pd.DataFrame(
        [[500.0, 0.40, 24, 2.2, 0.50, 0.90]],
        columns=FEATURE_COLUMNS,
    )

    direct_score = float(model.predict_proba(X)[0, 1])

    assert stored_score == pytest.approx(direct_score)


def test_top_attention_report_uses_investigation_language(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "warehouse.db"
    model_path = tmp_path / "model.joblib"
    report_path = tmp_path / "report.csv"

    _create_feature_table(db_path)
    _create_model_artifact(model_path)

    monkeypatch.setattr(batch_score, "WAREHOUSE_PATH", db_path)
    monkeypatch.setattr(batch_score, "MODEL_PATH", model_path)
    monkeypatch.setattr(batch_score, "REPORT_PATH", report_path)

    batch_score.score_latest_features()

    report = pd.read_csv(report_path)

    assert not report.empty
    assert {
        "grid_id",
        "timestamp",
        "risk_score",
        "risk_level",
        "reason",
        "model_version",
    }.issubset(report.columns)

    reasons = " ".join(report["reason"].str.lower())

    assert "attention" in reasons
    assert "investigate" in reasons
    assert "confirmed fault" not in reasons
    assert "congestion" not in reasons
