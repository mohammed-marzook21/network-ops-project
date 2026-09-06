"""
Hand-computed expectations for the fixture in conftest.py.

Layout (grid, time_key, total_activity):
    101: [1]=10   [2]=50   [3]=20   [4]=5
    202: [1]=3    [2]=3    [3]=3    [4]=3
    303: [1]=0    [2]=1    [3]=1    [4]=1
    time_key 1 = day1 hour0, 2 = day1 hour1, 3 = day2 hour0, 4 = day2 hour1

get_network_summary is CUMULATIVE: every KPI is computed over
"WHERE ts <= as_of" -- i.e. all history up to and including as_of, not a
trailing window. peak_hour groups by hour-OF-DAY across all days in range.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from tests.conftest import TS_BY_TIME_KEY

APP_ROOT = Path(__file__).resolve().parent.parent / "app"

AS_OF_FULL = TS_BY_TIME_KEY[4]   # "2020-01-02 01:00:00" -- latest ts, default AS_OF
AS_OF_DAY1_ONLY = TS_BY_TIME_KEY[2]  # "2020-01-01 01:00:00" -- time_key 1,2 only


def test_default_as_of_matches_hand_computed_summary(client):
    resp = client.get("/network/summary")
    assert resp.status_code == 200
    body = resp.json()

    # total_activity = 10+50+20+5 + 3*4 + 0+1+1+1 = 85 + 12 + 3 = 100
    assert body["total_activity"] == pytest.approx(100.0)
    # all three grids have >=1 row with total_activity > 0 somewhere in range
    assert body["active_grids"] == 3
    # hour0 total = 10+20+3+3+0+1 = 37 ; hour1 total = 50+5+3+3+1+1 = 63 -> peak is hour 1
    assert body["peak_hour"] == 1
    # grid totals: 101=85, 202=12, 303=3 -> top is 101
    assert body["top_grid"] == 101
    # default as_of must be MAX(ts) in dim_time
    assert body["as_of"] == AS_OF_FULL


def test_explicit_as_of_narrows_the_cumulative_window(client):
    resp = client.get("/network/summary", params={"as_of": AS_OF_DAY1_ONLY})
    assert resp.status_code == 200
    body = resp.json()

    # only time_key 1,2 qualify now (ts <= day1 hour1)
    # total_activity = 10+50 + 3+3 + 0+1 = 60+6+1 = 67
    assert body["total_activity"] == pytest.approx(67.0)
    assert body["active_grids"] == 3  # 303 still has hour1=1 > 0
    # hour0 = 10+3+0 = 13 ; hour1 = 50+3+1 = 54 -> peak hour 1
    assert body["peak_hour"] == 1
    # grid totals: 101=60, 202=6, 303=1 -> top 101
    assert body["top_grid"] == 101
    assert body["as_of"] == AS_OF_DAY1_ONLY


def test_explicit_as_of_is_reproducible_across_calls(client):
    params = {"as_of": AS_OF_DAY1_ONLY}
    first = client.get("/network/summary", params=params).json()
    second = client.get("/network/summary", params=params).json()
    assert first == second


def test_every_successful_response_includes_effective_as_of(client):
    for params in ({}, {"as_of": AS_OF_DAY1_ONLY}, {"as_of": AS_OF_FULL}):
        resp = client.get("/network/summary", params=params)
        assert resp.status_code == 200
        assert resp.json().get("as_of")


def test_as_of_not_present_in_dim_time_returns_400(client):
    """The service validates as_of against dim_time and raises ValueError
    for anything not present -- the route maps that to 400, not 404 or 500.
    This also covers malformed/garbage as_of strings, since they'll never
    match a real ts either."""
    resp = client.get("/network/summary", params={"as_of": "2099-01-01 00:00:00"})
    assert resp.status_code == 400

    resp2 = client.get("/network/summary", params={"as_of": "not-a-timestamp"})
    assert resp2.status_code == 400


def test_missing_warehouse_file_returns_clear_500(client, monkeypatch):
    import app.db as db_module

    monkeypatch.setattr(db_module, "DB_PATH", "/nonexistent/path/network_analytics.db")
    resp = client.get("/network/summary")
    assert resp.status_code == 500
    assert "unavailable" in resp.json()["detail"].lower()


def test_swagger_schema_exposes_all_required_fields(client):
    schema = client.get("/openapi.json").json()
    props = schema["components"]["schemas"]["NetworkSummaryResponse"]["properties"]
    for field in ("total_activity", "active_grids", "peak_hour", "top_grid", "as_of"):
        assert field in props


# ---------------------------------------------------------------------------
# Static check: "no date literal in the endpoint or service code."
# Applied to the files that actually contain query/business logic
# (db.py, network_summary_service.py). Deliberately NOT applied to
# models/network_summary.py or the route's Query(description=...) text --
# those are Swagger example/documentation strings, not values the logic
# depends on, and a documented example date is expected there.
# ---------------------------------------------------------------------------
DATE_LITERAL_RE = re.compile(r"\b(19|20)\d{2}-\d{2}-\d{2}\b")


@pytest.mark.parametrize(
    "module_path",
    [
        APP_ROOT / "db.py",
        APP_ROOT / "services" / "network_summary_service.py",
    ],
)
def test_no_hardcoded_date_literals_in_logic_code(module_path):
    source = module_path.read_text()
    tree = ast.parse(source)
    literal_strings = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    offenders = [s for s in literal_strings if DATE_LITERAL_RE.search(s)]
    assert not offenders, f"Found hardcoded date-like literal(s) in {module_path}: {offenders}"
