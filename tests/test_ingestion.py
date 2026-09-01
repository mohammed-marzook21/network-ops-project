"""
DE2 - Tests for the ingestion module.
Phase 3, Network Operations Predictive Intelligence Project

Run with: pytest tests/test_ingestion.py -v
"""

import json
import os
import shutil
import pytest
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ingestion.ingestion import (
    detect_files, validate_schema, validate_minimum_quality,
    route_file, write_audit_record, already_processed, process_file,
)


@pytest.fixture
def tmp_dirs(tmp_path):
    """Create a fresh landing/raw/rejected/logs structure for each test."""
    landing = tmp_path / "landing"
    raw = tmp_path / "raw"
    rejected = tmp_path / "rejected"
    logs = tmp_path / "logs"
    landing.mkdir()
    raw.mkdir()
    rejected.mkdir()
    logs.mkdir()
    return {
        "landing": str(landing), "raw": str(raw),
        "rejected": str(rejected), "log_path": str(logs / "ingestion_log.jsonl"),
    }


def write_csv(path, header, rows):
    with open(path, "w", newline="") as f:
        f.write(",".join(header) + "\n")
        for row in rows:
            f.write(",".join(str(v) for v in row) + "\n")


VALID_HEADER = ["datetime", "CellID", "countrycode", "smsin", "smsout", "callin", "callout", "internet"]


def make_valid_rows(n=5):
    return [
        [f"2013-11-08 {h:02d}:00:00", 1, 39, 1.1, 0.9, 0.5, 0.3, 10.5]
        for h in range(n)
    ]


# ── detect_files ──────────────────────────────────────────────────────

def test_detect_files_matches_pattern(tmp_dirs):
    write_csv(os.path.join(tmp_dirs["landing"], "sms-call-internet-mi-2013-11-08.csv"), VALID_HEADER, make_valid_rows())
    found = detect_files(tmp_dirs["landing"])
    assert len(found) == 1
    assert "sms-call-internet-mi-2013-11-08.csv" in found[0]


def test_detect_files_ignores_geojson(tmp_dirs):
    write_csv(os.path.join(tmp_dirs["landing"], "sms-call-internet-mi-2013-11-08.csv"), VALID_HEADER, make_valid_rows())
    with open(os.path.join(tmp_dirs["landing"], "milano-grid.geojson"), "w") as f:
        f.write('{"type": "FeatureCollection", "features": []}')
    found = detect_files(tmp_dirs["landing"])
    assert len(found) == 1
    assert all("geojson" not in f for f in found)


def test_detect_files_rejects_looser_pattern(tmp_dirs):
    """A different-city file must NOT be picked up just because it's a CSV."""
    write_csv(os.path.join(tmp_dirs["landing"], "sms-call-internet-trentino-2013-11-08.csv"), VALID_HEADER, make_valid_rows())
    found = detect_files(tmp_dirs["landing"])
    assert len(found) == 0


# ── validate_schema ───────────────────────────────────────────────────

def test_valid_schema_passes(tmp_dirs):
    path = os.path.join(tmp_dirs["landing"], "f.csv")
    write_csv(path, VALID_HEADER, make_valid_rows())
    ok, reason = validate_schema(path)
    assert ok is True
    assert reason is None


def test_missing_column_fails_schema(tmp_dirs):
    path = os.path.join(tmp_dirs["landing"], "f.csv")
    header_missing_internet = [c for c in VALID_HEADER if c != "internet"]
    rows = [[f"2013-11-08 {h:02d}:00:00", 1, 39, 1.1, 0.9, 0.5, 0.3] for h in range(3)]
    write_csv(path, header_missing_internet, rows)
    ok, reason = validate_schema(path)
    assert ok is False
    assert "internet" in reason


# ── validate_minimum_quality ─────────────────────────────────────────

def test_valid_quality_passes(tmp_dirs):
    path = os.path.join(tmp_dirs["landing"], "f.csv")
    write_csv(path, VALID_HEADER, make_valid_rows())
    ok, reason, row_count = validate_minimum_quality(path)
    assert ok is True
    assert reason is None
    assert row_count == 5


def test_malformed_timestamp_fails_quality(tmp_dirs):
    path = os.path.join(tmp_dirs["landing"], "f.csv")
    rows = make_valid_rows()
    rows[2][0] = "NOT-A-DATE"  # break the 3rd row's timestamp
    write_csv(path, VALID_HEADER, rows)
    ok, reason, row_count = validate_minimum_quality(path)
    assert ok is False
    assert "timestamp" in reason.lower()


def test_negative_activity_value_fails_quality(tmp_dirs):
    path = os.path.join(tmp_dirs["landing"], "f.csv")
    rows = make_valid_rows()
    rows[1][3] = -5.0  # negative smsin
    write_csv(path, VALID_HEADER, rows)
    ok, reason, row_count = validate_minimum_quality(path)
    assert ok is False
    assert "negative" in reason.lower()


def test_empty_file_fails_quality(tmp_dirs):
    path = os.path.join(tmp_dirs["landing"], "f.csv")
    write_csv(path, VALID_HEADER, [])
    ok, reason, row_count = validate_minimum_quality(path)
    assert ok is False
    assert row_count == 0


# ── route_file ────────────────────────────────────────────────────────

def test_route_valid_file_goes_to_raw(tmp_dirs):
    path = os.path.join(tmp_dirs["landing"], "f.csv")
    write_csv(path, VALID_HEADER, make_valid_rows())
    dest = route_file(path, is_valid=True, raw_dir=tmp_dirs["raw"], rejected_dir=tmp_dirs["rejected"])
    assert os.path.exists(dest)
    assert tmp_dirs["raw"] in dest
    assert not os.path.exists(path)  # moved, not copied


def test_route_invalid_file_goes_to_rejected(tmp_dirs):
    path = os.path.join(tmp_dirs["landing"], "f.csv")
    write_csv(path, VALID_HEADER, make_valid_rows())
    dest = route_file(path, is_valid=False, raw_dir=tmp_dirs["raw"], rejected_dir=tmp_dirs["rejected"])
    assert os.path.exists(dest)
    assert tmp_dirs["rejected"] in dest


def test_routed_file_content_unchanged(tmp_dirs):
    path = os.path.join(tmp_dirs["landing"], "f.csv")
    write_csv(path, VALID_HEADER, make_valid_rows())
    with open(path) as f:
        original_content = f.read()
    dest = route_file(path, is_valid=True, raw_dir=tmp_dirs["raw"], rejected_dir=tmp_dirs["rejected"])
    with open(dest) as f:
        moved_content = f.read()
    assert original_content == moved_content


# ── end-to-end process_file ──────────────────────────────────────────

def test_process_file_valid_end_to_end(tmp_dirs):
    path = os.path.join(tmp_dirs["landing"], "sms-call-internet-mi-2013-11-08.csv")
    write_csv(path, VALID_HEADER, make_valid_rows())
    result = process_file(path, tmp_dirs["raw"], tmp_dirs["rejected"], tmp_dirs["log_path"])
    assert result["status"] == "accepted"
    assert result["row_count"] == 5
    assert os.path.exists(os.path.join(tmp_dirs["raw"], "sms-call-internet-mi-2013-11-08.csv"))

    with open(tmp_dirs["log_path"]) as f:
        record = json.loads(f.readline())
    assert record["status"] == "accepted"
    assert record["filename"] == "sms-call-internet-mi-2013-11-08.csv"


def test_process_file_invalid_end_to_end(tmp_dirs):
    path = os.path.join(tmp_dirs["landing"], "sms-call-internet-mi-2013-11-09.csv")
    header_missing_internet = [c for c in VALID_HEADER if c != "internet"]
    rows = [[f"2013-11-09 {h:02d}:00:00", 1, 39, 1.1, 0.9, 0.5, 0.3] for h in range(3)]
    write_csv(path, header_missing_internet, rows)
    result = process_file(path, tmp_dirs["raw"], tmp_dirs["rejected"], tmp_dirs["log_path"])
    assert result["status"] == "rejected"
    assert "internet" in result["reason"]
    assert os.path.exists(os.path.join(tmp_dirs["rejected"], "sms-call-internet-mi-2013-11-09.csv"))

    with open(tmp_dirs["log_path"]) as f:
        record = json.loads(f.readline())
    assert record["status"] == "rejected"
    assert "internet" in record["reason"]


def test_reprocessing_same_file_does_not_duplicate(tmp_dirs):
    path = os.path.join(tmp_dirs["landing"], "sms-call-internet-mi-2013-11-08.csv")
    write_csv(path, VALID_HEADER, make_valid_rows())
    result1 = process_file(path, tmp_dirs["raw"], tmp_dirs["rejected"], tmp_dirs["log_path"])
    assert result1["status"] == "accepted"

    # Simulate the same file being dropped into landing again
    write_csv(path, VALID_HEADER, make_valid_rows())
    result2 = process_file(path, tmp_dirs["raw"], tmp_dirs["rejected"], tmp_dirs["log_path"])
    assert result2["status"] == "skipped_duplicate"

    # Only ONE copy should exist in raw/, not two
    raw_files = os.listdir(tmp_dirs["raw"])
    assert raw_files.count("sms-call-internet-mi-2013-11-08.csv") == 1


def test_reference_geojson_never_touched(tmp_dirs):
    """Sanity check: nothing in this module ever writes to a reference folder."""
    ref_dir = os.path.dirname(tmp_dirs["landing"]) + "/reference"
    os.makedirs(ref_dir, exist_ok=True)
    geojson_path = os.path.join(ref_dir, "milano-grid.geojson")
    with open(geojson_path, "w") as f:
        f.write('{"type": "FeatureCollection", "features": []}')

    path = os.path.join(tmp_dirs["landing"], "sms-call-internet-mi-2013-11-08.csv")
    write_csv(path, VALID_HEADER, make_valid_rows())
    process_file(path, tmp_dirs["raw"], tmp_dirs["rejected"], tmp_dirs["log_path"])

    with open(geojson_path) as f:
        content_after = f.read()
    assert content_after == '{"type": "FeatureCollection", "features": []}'