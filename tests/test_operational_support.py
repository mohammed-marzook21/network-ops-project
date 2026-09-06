from __future__ import annotations

import json

import pytest

from tests.conftest import AS_OF_RICH, GRID_A


def write_status_file(tmp_path, payload):
    """Create an isolated DE7 pipeline status record for testing."""
    status_path = tmp_path / "de7_pipeline_status.json"

    with open(status_path, "w", encoding="utf-8") as file:
        json.dump(payload, file)

    return str(status_path)


def healthy_status_payload():
    """A successful DE7 status record matching the rich test warehouse."""
    return {
        "run_id": "test_success_run",
        "run_timestamp": "2020-03-03T23:00:00",
        "per_task_status": {
            "ingest": "success",
            "validate": "success",
            "spark_process": "success",
            "load_warehouse": "success",
            "quality_check": "success",
        },
        "rows_in": 144,
        "rows_rejected": 0,
        "nulls_handled": 0,
        "rows_published": 144,
        "warehouse_rows": 144,
        "duplicate_grain_groups": 0,
        "AS_OF": AS_OF_RICH,
    }


def test_pipeline_status_reports_healthy_for_successful_run(
    rich_client, tmp_path, monkeypatch
):
    import app.services.operational_support_service as service_module

    status_path = write_status_file(
        tmp_path,
        healthy_status_payload(),
    )

    monkeypatch.setattr(
        service_module,
        "PIPELINE_STATUS_PATH",
        status_path,
    )

    resp = rich_client.get("/pipeline/status")

    assert resp.status_code == 200

    body = resp.json()

    assert body["healthy"] is True
    assert body["reasons"] == []
    assert body["run_id"] == "test_success_run"
    assert body["as_of"] == AS_OF_RICH
    assert body["freshness_hours"] == pytest.approx(0.0)


def test_pipeline_status_reports_unhealthy_after_failed_run(
    rich_client, tmp_path, monkeypatch
):
    """
    Required API6 acceptance test:
    a deliberately failed pipeline run must report healthy=False
    with a populated reasons list.
    """
    import app.services.operational_support_service as service_module

    payload = healthy_status_payload()

    payload["run_id"] = "test_failed_run"
    payload["per_task_status"]["quality_check"] = "failed"

    status_path = write_status_file(
        tmp_path,
        payload,
    )

    monkeypatch.setattr(
        service_module,
        "PIPELINE_STATUS_PATH",
        status_path,
    )

    resp = rich_client.get("/pipeline/status")

    assert resp.status_code == 200

    body = resp.json()

    assert body["healthy"] is False
    assert len(body["reasons"]) > 0

    assert any(
        "quality_check" in reason
        for reason in body["reasons"]
    )


def test_pipeline_status_reports_unhealthy_when_as_of_is_stale(
    rich_client, tmp_path, monkeypatch
):
    import app.services.operational_support_service as service_module

    payload = healthy_status_payload()
    payload["AS_OF"] = "2020-03-02 23:00:00"

    status_path = write_status_file(
        tmp_path,
        payload,
    )

    monkeypatch.setattr(
        service_module,
        "PIPELINE_STATUS_PATH",
        status_path,
    )

    resp = rich_client.get("/pipeline/status")

    assert resp.status_code == 200

    body = resp.json()

    assert body["healthy"] is False
    assert len(body["reasons"]) > 0
    assert body["freshness_hours"] == pytest.approx(24.0)


def test_missing_pipeline_status_file_returns_500(
    rich_client, monkeypatch
):
    import app.services.operational_support_service as service_module

    monkeypatch.setattr(
        service_module,
        "PIPELINE_STATUS_PATH",
        "/nonexistent/de7_pipeline_status.json",
    )

    resp = rich_client.get("/pipeline/status")

    assert resp.status_code == 500


def test_pipeline_status_as_of_matches_analytics_layer(
    rich_client, tmp_path, monkeypatch
):
    import app.services.operational_support_service as service_module

    status_path = write_status_file(
        tmp_path,
        healthy_status_payload(),
    )

    monkeypatch.setattr(
        service_module,
        "PIPELINE_STATUS_PATH",
        status_path,
    )

    resp = rich_client.get("/pipeline/status")

    assert resp.status_code == 200

    body = resp.json()

    assert body["as_of"] == AS_OF_RICH


def test_grid_location_returns_centroid_and_polygon_reference(
    rich_client,
):
    resp = rich_client.get(
        f"/network/grid/{GRID_A}/location"
    )

    assert resp.status_code == 200

    body = resp.json()

    assert body["grid_id"] == GRID_A
    assert body["centroid_lat"] == pytest.approx(45.46)
    assert body["centroid_lon"] == pytest.approx(9.19)

    assert "polygon_reference" in body


def test_grid_location_does_not_return_polygon_geometry(
    rich_client,
):
    resp = rich_client.get(
        f"/network/grid/{GRID_A}/location"
    )

    assert resp.status_code == 200

    body = resp.json()

    assert "geometry_json" not in body
    assert "coordinates" not in body
    assert "polygon" not in body or "polygon_reference" in body


@pytest.mark.parametrize(
    "grid_id",
    [0, -1, 999999],
)
def test_unknown_grid_location_returns_404(
    rich_client,
    grid_id,
):
    resp = rich_client.get(
        f"/network/grid/{grid_id}/location"
    )

    assert resp.status_code == 404


def test_swagger_exposes_operational_support_schemas(
    rich_client,
):
    schema = rich_client.get(
        "/openapi.json"
    ).json()

    pipeline_props = schema[
        "components"
    ]["schemas"][
        "PipelineStatusResponse"
    ]["properties"]

    for field in (
        "healthy",
        "reasons",
        "run_id",
        "run_timestamp",
        "per_task_status",
        "rows_in",
        "rows_rejected",
        "nulls_handled",
        "rows_published",
        "as_of",
        "freshness_hours",
    ):
        assert field in pipeline_props

    location_props = schema[
        "components"
    ]["schemas"][
        "GridLocationResponse"
    ]["properties"]

    for field in (
        "grid_id",
        "centroid_lat",
        "centroid_lon",
        "polygon_reference",
    ):
        assert field in location_props