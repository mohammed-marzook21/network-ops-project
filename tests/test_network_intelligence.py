from __future__ import annotations

import json

import pytest
from pydantic import BaseModel

from tests.conftest import AS_OF_RICH, GRID_A, GRID_B


# ---------------------------------------------------------------------------
# Hotspots: simple current-activity ranking at the single hour == as_of
# ---------------------------------------------------------------------------
def test_hotspots_ranks_the_spiking_grid_first(rich_client):
    resp = rich_client.get("/network/hotspots")
    assert resp.status_code == 200
    body = resp.json()
    assert body["as_of"] == AS_OF_RICH
    assert body["hotspots"][0]["grid_id"] == GRID_A
    assert body["hotspots"][0]["total_activity"] == pytest.approx(5000.0)
    assert body["hotspots"][0]["status"] == "elevated"


def test_hotspots_respects_limit(rich_client):
    resp = rich_client.get("/network/hotspots", params={"limit": 1})
    body = resp.json()
    assert len(body["hotspots"]) == 1
    assert body["count"] == 1


def test_hotspots_word_congestion_never_appears(rich_client):
    resp = rich_client.get("/network/hotspots")
    raw_text = json.dumps(resp.json()).lower()
    assert "congestion" not in raw_text

    schema = rich_client.get("/openapi.json").json()
    schema_text = json.dumps(schema).lower()
    # Only check the hotspot/alert schema and paths, not the whole spec,
    # in case unrelated endpoints legitimately use the word elsewhere.
    for key in ("hotspotitem", "alertitem", "hotspotsresponse", "alertsresponse"):
        assert key in schema_text  # sanity: schema names present
    assert "congestion" not in schema_text


def test_hotspots_order_is_deterministic_across_repeated_calls(rich_client):
    first = rich_client.get("/network/hotspots").json()
    second = rich_client.get("/network/hotspots").json()
    assert [h["grid_id"] for h in first["hotspots"]] == [h["grid_id"] for h in second["hotspots"]]


def test_every_returned_grid_id_exists_in_dim_grid(rich_client):
    resp = rich_client.get("/network/hotspots")
    for h in resp.json()["hotspots"]:
        assert h["grid_id"] in (GRID_A, GRID_B)


# ---------------------------------------------------------------------------
# Alerts: NP3 rule-based z-score anomaly vs each grid's own history
# ---------------------------------------------------------------------------
def test_alerts_flags_the_spiking_grid_as_high_severity(rich_client):
    resp = rich_client.get("/network/alerts")
    assert resp.status_code == 200
    body = resp.json()
    grid_ids = [a["grid_id"] for a in body["alerts"]]
    assert GRID_A in grid_ids
    alert = next(a for a in body["alerts"] if a["grid_id"] == GRID_A)
    assert alert["severity"] == "high"
    # baseline is leave-one-out (excludes the spike itself), so it should
    # sit near the ~100 baseline, nowhere close to the 5000 spike value
    assert alert["baseline_activity"] == pytest.approx(100.0, abs=5.0)


def test_alerts_never_flags_the_flat_grid(rich_client):
    resp = rich_client.get("/network/alerts")
    grid_ids = [a["grid_id"] for a in resp.json()["alerts"]]
    assert GRID_B not in grid_ids


def test_alerts_severity_filter(rich_client):
    resp = rich_client.get("/network/alerts", params={"severity": "medium"})
    body = resp.json()
    assert all(a["severity"] == "medium" for a in body["alerts"])


def test_alerts_word_congestion_never_appears(rich_client):
    resp = rich_client.get("/network/alerts")
    assert "congestion" not in json.dumps(resp.json()).lower()


def test_alerts_as_of_reproducible(rich_client):
    params = {"as_of": AS_OF_RICH}
    first = rich_client.get("/network/alerts", params=params).json()
    second = rich_client.get("/network/alerts", params=params).json()
    assert first == second


# ---------------------------------------------------------------------------
# Forward-compatibility: adding a NEW nullable ML field must not break an
# existing client. We simulate "the client's own copy of the schema" with
# an extra field the server doesn't send yet, and confirm parsing still
# succeeds -- i.e. the real server response validates fine against a
# schema that has ONE MORE optional field than it currently returns.
# ---------------------------------------------------------------------------
class FutureHotspotItem(BaseModel):
    grid_id: int
    ts: str
    hour: int
    total_activity: float
    status: str
    reason: str
    risk_score: float | None = None
    risk_level: str | None = None
    model_version: str | None = None
    model_confidence: float | None = None  # <-- hypothetical ML6 addition


def test_adding_a_future_nullable_field_does_not_break_parsing(rich_client):
    resp = rich_client.get("/network/hotspots")
    for raw_item in resp.json()["hotspots"]:
        # Should parse cleanly even though the server never sends
        # model_confidence -- proving the contract is additive-safe.
        parsed = FutureHotspotItem(**raw_item)
        assert parsed.model_confidence is None


def test_swagger_schema_exposes_nullable_ml_fields(rich_client):
    schema = rich_client.get("/openapi.json").json()
    hotspot_props = schema["components"]["schemas"]["HotspotItem"]["properties"]
    alert_props = schema["components"]["schemas"]["AlertItem"]["properties"]
    for props in (hotspot_props, alert_props):
        for field in ("risk_score", "risk_level", "model_version"):
            assert field in props
