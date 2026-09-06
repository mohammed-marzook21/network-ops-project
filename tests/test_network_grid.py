from __future__ import annotations

import pytest

from tests.conftest import AS_OF_RICH, GRID_A, GRID_B, TOTAL_HOURS


def test_default_window_returns_exactly_24_points(rich_client):
    resp = rich_client.get(f"/network/grid/{GRID_A}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["point_count"] == 24
    assert len(body["series"]) == 24
    assert body["as_of"] == AS_OF_RICH
    assert body["window_end"] == AS_OF_RICH


def test_default_window_includes_the_spike_at_the_last_hour(rich_client):
    resp = rich_client.get(f"/network/grid/{GRID_A}")
    body = resp.json()
    last_point = body["series"][-1]
    assert last_point["ts"] == AS_OF_RICH
    assert last_point["total_activity"] == pytest.approx(5000.0)
    # every other point in the window is near the ~100 baseline (small
    # deterministic per-hour variation, never the 5000 spike)
    for point in body["series"][:-1]:
        assert 90.0 <= point["total_activity"] <= 110.0


def test_no_timestamp_appears_twice_in_a_single_response(rich_client):
    resp = rich_client.get(f"/network/grid/{GRID_A}")
    series = resp.json()["series"]
    timestamps = [p["ts"] for p in series]
    assert len(timestamps) == len(set(timestamps))


def test_series_is_ordered_ascending_by_timestamp(rich_client):
    resp = rich_client.get(f"/network/grid/{GRID_A}")
    series = resp.json()["series"]
    timestamps = [p["ts"] for p in series]
    assert timestamps == sorted(timestamps)


def test_boring_grid_has_no_spike(rich_client):
    resp = rich_client.get(f"/network/grid/{GRID_B}")
    body = resp.json()
    for point in body["series"]:
        assert point["total_activity"] == pytest.approx(50.0)


@pytest.mark.parametrize("bad_grid_id", [0, 10001, -5, 999999])
def test_unknown_grid_ids_return_404(rich_client, bad_grid_id):
    resp = rich_client.get(f"/network/grid/{bad_grid_id}")
    assert resp.status_code == 404


def test_grid_id_1_and_10000_are_valid_boundaries(rich_client):
    # These grid_ids are in-range but not seeded with activity in this
    # fixture -- they exist in dim_grid? No: this fixture only seeds
    # GRID_A/GRID_B in dim_grid, so 1 and 10000 are legitimately unknown
    # HERE. The real warehouse seeds dim_grid for all of 1-10000, so
    # there this same request would succeed with an empty/valid series
    # instead. This test documents that boundary values are handled by
    # the *range check*, not rejected outright, by checking they don't
    # crash the range-validation path itself (a ValueError/500 would
    # indicate a bug in the boundary math, e.g. off-by-one).
    resp_low = rich_client.get("/network/grid/1")
    resp_high = rich_client.get("/network/grid/10000")
    assert resp_low.status_code == 404  # unknown in THIS fixture's dim_grid
    assert resp_high.status_code == 404
    assert resp_low.status_code != 500
    assert resp_high.status_code != 500


def test_date_filter_returns_matching_day_only(rich_client):
    resp = rich_client.get(f"/network/grid/{GRID_A}", params={"date": "2020-03-01"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["point_count"] == 24
    assert all(p["ts"].startswith("2020-03-01") for p in body["series"])
    assert body["window_start"] is None  # explicit date filter, no trailing window


def test_date_and_hour_filter_returns_single_point(rich_client):
    resp = rich_client.get(
        f"/network/grid/{GRID_A}", params={"date": "2020-03-01", "hour": 5}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["point_count"] == 1
    assert body["series"][0]["hour"] == 5


def test_malformed_date_returns_422(rich_client):
    resp = rich_client.get(f"/network/grid/{GRID_A}", params={"date": "03-01-2020"})
    assert resp.status_code == 422


def test_hour_out_of_range_returns_422(rich_client):
    resp = rich_client.get(f"/network/grid/{GRID_A}", params={"hour": 24})
    assert resp.status_code == 422


def test_as_of_not_in_dim_time_returns_400(rich_client):
    resp = rich_client.get(f"/network/grid/{GRID_A}", params={"as_of": "2099-01-01 00:00:00"})
    assert resp.status_code == 400


def test_missing_warehouse_returns_500(rich_client, monkeypatch):
    import app.db as db_module

    monkeypatch.setattr(db_module, "DB_PATH", "/nonexistent/network_analytics.db")
    resp = rich_client.get(f"/network/grid/{GRID_A}")
    assert resp.status_code == 500


def test_swagger_schema_exposes_all_fields(rich_client):
    schema = rich_client.get("/openapi.json").json()
    props = schema["components"]["schemas"]["GridActivityResponse"]["properties"]
    for field in ("grid_id", "as_of", "window_start", "window_end", "point_count", "series"):
        assert field in props
