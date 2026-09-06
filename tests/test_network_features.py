from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from tests.conftest import (
    AS_OF_RICH,
    GRID_A,
    GRID_B,
    GRID_C_NO_FEATURES,
    STALE_FEATURE_TS,
)

APP_ROOT = Path(__file__).resolve().parent.parent / "app"

REQUIRED_ML2_FIELDS = (
    "avg_activity",
    "activity_growth",
    "active_hours",
    "peak_ratio",
    "variability",
    "internet_share",
)


def test_fresh_grid_returns_stored_values_verbatim(rich_client):
    resp = rich_client.get(f"/network/grid/{GRID_A}/features")
    assert resp.status_code == 200
    body = resp.json()

    # These must come back EXACTLY as stored -- no recomputation happening
    # in the API layer.
    assert body["avg_activity"] == pytest.approx(100.5)
    assert body["activity_growth"] == pytest.approx(0.05)
    assert body["active_hours"] == 71
    assert body["peak_ratio"] == pytest.approx(45.0)
    assert body["variability"] == pytest.approx(1.2)
    assert body["internet_share"] == pytest.approx(0.6)
    assert body["feature_timestamp"] == AS_OF_RICH
    assert body["data_quality_status"] == "ok"
    assert body["row_count"] == 72


def test_fresh_grid_has_zero_feature_age(rich_client):
    resp = rich_client.get(f"/network/grid/{GRID_A}/features")
    body = resp.json()
    # GRID_A's stored feature_timestamp == the warehouse's current AS_OF
    assert body["feature_age_hours"] == pytest.approx(0.0)


def test_stale_grid_reports_nonzero_feature_age(rich_client):
    resp = rich_client.get(f"/network/grid/{GRID_B}/features")
    assert resp.status_code == 200
    body = resp.json()
    assert body["feature_timestamp"] == STALE_FEATURE_TS
    # STALE_FEATURE_TS is exactly 24 hours before AS_OF_RICH by construction
    assert body["feature_age_hours"] == pytest.approx(24.0)


@pytest.mark.parametrize("bad_grid_id", [0, 10001, -5])
def test_grid_id_outside_valid_range_returns_404(rich_client, bad_grid_id):
    resp = rich_client.get(f"/network/grid/{bad_grid_id}/features")
    assert resp.status_code == 404


def test_grid_with_no_stored_features_returns_clear_404_not_zeros(rich_client):
    """GRID_C_NO_FEATURES is a perfectly valid, known grid (present in
    dim_grid) that simply has no grid_features row yet -- e.g. the
    pipeline hasn't been (re)run since this grid started reporting. This
    must be a clear error, never fabricated/zeroed feature values."""
    resp = rich_client.get(f"/network/grid/{GRID_C_NO_FEATURES}/features")
    assert resp.status_code == 404
    assert "no stored features" in resp.json()["detail"].lower()


def test_missing_grid_features_table_returns_500(rich_client, monkeypatch):
    """If the feature pipeline has NEVER been run at all, grid_features
    doesn't exist as a table -- distinct from an existing-but-empty row,
    and should be a 500 (data source unavailable), not a 404."""
    import sqlite3

    import app.db as db_module

    real_path = db_module.DB_PATH
    conn = sqlite3.connect(real_path)
    conn.execute("DROP TABLE grid_features")
    conn.commit()
    conn.close()

    resp = rich_client.get(f"/network/grid/{GRID_A}/features")
    assert resp.status_code == 500


def test_missing_warehouse_file_returns_500(rich_client, monkeypatch):
    import app.db as db_module

    monkeypatch.setattr(db_module, "DB_PATH", "/nonexistent/network_analytics.db")
    resp = rich_client.get(f"/network/grid/{GRID_A}/features")
    assert resp.status_code == 500


def test_swagger_schema_exposes_all_ml2_fields(rich_client):
    schema = rich_client.get("/openapi.json").json()
    props = schema["components"]["schemas"]["GridFeaturesResponse"]["properties"]
    for field in REQUIRED_ML2_FIELDS + ("feature_timestamp", "data_quality_status", "row_count", "feature_age_hours"):
        assert field in props


# ---------------------------------------------------------------------------
# "The six feature names match ml/features.py exactly, character for
# character." ML2 doesn't exist yet, so this checks the placeholder
# pipeline and the API schema agree with EACH OTHER on the six names --
# once ML2 ships, re-run this same style of check against the real
# ml/features.py instead.
# ---------------------------------------------------------------------------
def test_placeholder_pipeline_and_api_schema_use_identical_field_names():
    ml_source = (Path(__file__).resolve().parent.parent / "ml" / "features_placeholder.py").read_text()
    model_source = (APP_ROOT / "models" / "network_features.py").read_text()

    for field in REQUIRED_ML2_FIELDS:
        assert field in ml_source, f"{field} missing from ml/features_placeholder.py"
        assert field in model_source, f"{field} missing from app/models/network_features.py"


# ---------------------------------------------------------------------------
# "No feature arithmetic exists in the API layer." Static check: the
# service/route files for API4 should contain no arithmetic operators
# applied to feature values -- only reads, comparisons, and the freshness
# calculation (which is explicitly NOT a "feature", it's request-time
# metadata about staleness, so it's allowed).
# ---------------------------------------------------------------------------
def test_no_feature_arithmetic_in_api_layer():
    """AST-based, not regex-based, so we don't false-positive on hyphens
    in docstrings/comments (e.g. "feature-serving route") -- we're
    looking for actual ast.BinOp nodes (+ - * /), not word characters
    that happen to sit near a dash."""
    route_path = APP_ROOT / "routes" / "network_features_route.py"
    tree = ast.parse(route_path.read_text())

    arithmetic_ops = (ast.Add, ast.Sub, ast.Mult, ast.Div)
    offending_nodes = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.BinOp) and isinstance(node.op, arithmetic_ops)
    ]
    assert not offending_nodes, (
        "Found arithmetic in network_features_route.py -- feature math belongs in "
        "ml/features_placeholder.py (or ml/features.py once ML2 ships), never in the route."
    )
