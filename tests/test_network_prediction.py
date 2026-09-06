from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def valid_prediction_payload():
    return {
        "avg_activity": 412.7,
        "activity_growth": 0.183,
        "active_hours": 168,
        "peak_ratio": 6.2,
        "variability": 0.94,
        "internet_share": 0.71,
    }



def test_predict_risk_returns_trained_model_response():
    response = client.post(
        "/network/predict-risk",
        json=valid_prediction_payload(),
    )

    assert response.status_code == 200

    body = response.json()

    assert "risk_score" in body
    assert "risk_level" in body
    assert "model_version" in body
    assert "feature_timestamp" in body
    assert "explanation_note" in body

    assert 0.0 <= body["risk_score"] <= 1.0
    assert body["risk_level"] in {"low", "medium", "high"}

    assert body["model_version"] == "ml3-logreg-v1"

    # Manually supplied feature vectors have no source timestamp.
    assert body["feature_timestamp"] is None

    assert "stub" not in body["explanation_note"].lower()
    assert "trained" in body["explanation_note"].lower()


def test_predict_risk_missing_required_field_returns_422():
    payload = valid_prediction_payload()

    del payload["internet_share"]

    response = client.post(
        "/network/predict-risk",
        json=payload,
    )

    assert response.status_code == 422

    body = response.json()

    assert "detail" in body
    assert any(
        error["loc"] == ["body", "internet_share"]
        for error in body["detail"]
    )


def test_predict_risk_invalid_internet_share_returns_422():
    payload = valid_prediction_payload()

    payload["internet_share"] = 1.5

    response = client.post(
        "/network/predict-risk",
        json=payload,
    )

    assert response.status_code == 422


def test_predict_risk_negative_avg_activity_returns_422():
    payload = valid_prediction_payload()

    payload["avg_activity"] = -100

    response = client.post(
        "/network/predict-risk",
        json=payload,
    )

    assert response.status_code == 422


def test_swagger_exposes_prediction_contract():
    response = client.get("/openapi.json")

    assert response.status_code == 200

    schema = response.json()

    assert "/network/predict-risk" in schema["paths"]

    request_schema = schema["components"]["schemas"][
        "RiskPredictionRequest"
    ]

    response_schema = schema["components"]["schemas"][
        "RiskPredictionResponse"
    ]

    for field in [
        "avg_activity",
        "activity_growth",
        "active_hours",
        "peak_ratio",
        "variability",
        "internet_share",
    ]:
        assert field in request_schema["properties"]

    for field in [
    "risk_score",
    "risk_level",
    "model_version",
    "feature_timestamp",
    "explanation_note",
]:
        assert field in response_schema["properties"]
def test_missing_model_artifact_fails_clearly(monkeypatch, tmp_path):
    from app.services import network_prediction_service as service

    missing_model = tmp_path / "missing_model.joblib"

    monkeypatch.setattr(
        service,
        "MODEL_PATH",
        missing_model,
    )

    try:
        service.load_model_artifact()
        assert False, "Expected RuntimeError for missing model artifact"
    except RuntimeError as exc:
        message = str(exc).lower()

        assert "model artifact is missing" in message
        assert "run ml3 training" in message