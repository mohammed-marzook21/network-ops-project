"""
Builds a small, hand-computable SQLite fixture that mirrors the REAL
warehouse schema exactly:

    dim_time(time_key, ts, date, hour, day_of_week)
    dim_grid(grid_id, centroid_lat, centroid_lon, geometry_json)
    fact_network_activity(grid_id, time_key, sms_in, sms_out, call_in,
                           call_out, internet_activity, total_sms,
                           total_calls, total_activity)

Two days x two hours (00:00 and 01:00) so peak_hour (grouped by
hour-of-day, summed across ALL days up to as_of) is actually exercised --
a single day would never distinguish "peak hour of day" from "peak
timestamp".
"""
from __future__ import annotations

import os
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.main import app

DDL = """
CREATE TABLE dim_time (
    time_key INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,
    date TEXT NOT NULL,
    hour INTEGER NOT NULL,
    day_of_week TEXT NOT NULL
);

CREATE TABLE dim_grid (
    grid_id INTEGER PRIMARY KEY,
    centroid_lat REAL NOT NULL,
    centroid_lon REAL NOT NULL,
    geometry_json TEXT NOT NULL
);

CREATE TABLE fact_network_activity (
    grid_id INTEGER NOT NULL,
    time_key INTEGER NOT NULL,
    sms_in REAL NOT NULL,
    sms_out REAL NOT NULL,
    call_in REAL NOT NULL,
    call_out REAL NOT NULL,
    internet_activity REAL NOT NULL,
    total_sms REAL NOT NULL,
    total_calls REAL NOT NULL,
    total_activity REAL NOT NULL,
    FOREIGN KEY (grid_id) REFERENCES dim_grid(grid_id),
    FOREIGN KEY (time_key) REFERENCES dim_time(time_key)
);

CREATE TABLE grid_features (
    grid_id INTEGER PRIMARY KEY,
    avg_activity REAL NOT NULL,
    activity_growth REAL,
    active_hours INTEGER NOT NULL,
    peak_ratio REAL,
    variability REAL,
    internet_share REAL,
    feature_timestamp TEXT NOT NULL,
    data_quality_status TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    FOREIGN KEY (grid_id) REFERENCES dim_grid(grid_id)
);
"""

# time_key 1 = day1 hour0, 2 = day1 hour1, 3 = day2 hour0, 4 = day2 hour1
DIM_TIME_ROWS = [
    (1, "2020-01-01 00:00:00", "2020-01-01", 0, "Wednesday"),
    (2, "2020-01-01 01:00:00", "2020-01-01", 1, "Wednesday"),
    (3, "2020-01-02 00:00:00", "2020-01-02", 0, "Thursday"),
    (4, "2020-01-02 01:00:00", "2020-01-02", 1, "Thursday"),
]

DIM_GRID_ROWS = [
    (101, 45.46, 9.19, "{}"),
    (202, 45.47, 9.20, "{}"),
    (303, 45.48, 9.21, "{}"),
]

# (grid_id, time_key, total_activity) -- other fact columns are filled with
# a consistent placeholder split since only total_activity drives the KPIs.
FACT_ROWS = [
    (101, 1, 10.0),
    (101, 2, 50.0),
    (101, 3, 20.0),
    (101, 4, 5.0),
    (202, 1, 3.0),
    (202, 2, 3.0),
    (202, 3, 3.0),
    (202, 4, 3.0),
    (303, 1, 0.0),   # inactive at day1 hour0
    (303, 2, 1.0),
    (303, 3, 1.0),
    (303, 4, 1.0),
]

TS_BY_TIME_KEY = {row[0]: row[1] for row in DIM_TIME_ROWS}


@pytest.fixture()
def fixture_db_path(tmp_path):
    db_path = tmp_path / "test_network_analytics.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(DDL)
    conn.executemany(
        "INSERT INTO dim_time VALUES (?, ?, ?, ?, ?)", DIM_TIME_ROWS
    )
    conn.executemany(
        "INSERT INTO dim_grid VALUES (?, ?, ?, ?)", DIM_GRID_ROWS
    )
    conn.executemany(
        """INSERT INTO fact_network_activity
           (grid_id, time_key, sms_in, sms_out, call_in, call_out,
            internet_activity, total_sms, total_calls, total_activity)
           VALUES (?, ?, 0, 0, 0, 0, 0, 0, 0, ?)""",
        FACT_ROWS,
    )
    conn.commit()
    conn.close()
    return str(db_path)


@pytest.fixture()
def client(fixture_db_path, monkeypatch):
    # app.db.DB_PATH is read at call-time inside get_connection(), so
    # patching the module attribute is enough -- no need to touch the
    # WAREHOUSE_DB_PATH env var or restart anything.
    import app.db as db_module

    monkeypatch.setattr(db_module, "DB_PATH", fixture_db_path)
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# A second, isolated fixture for API2 (grid drill-down) and API3
# (hotspots/alerts) tests. Kept separate from the 4-row fixture above (and
# its own temp DB) so it can use a richer multi-day, multi-grid dataset
# without touching the API1 tests that depend on the small fixture's exact
# MAX(ts).
#
#   3 days x 24 hours (72 hourly intervals), 2 grids:
#     * GRID_A (4821) is flat at 100.0 total_activity every hour EXCEPT the
#       very last hour (which becomes the default as_of), where it spikes
#       to 5000.0 -- this is what makes it both the top hotspot and a
#       "high" severity alert.
#     * GRID_B (707) stays flat at 50.0 throughout -- a boring control
#       grid that should never appear in hotspots or alerts.
# ---------------------------------------------------------------------------
from datetime import datetime, timedelta  # noqa: E402

GRID_A = 4821
GRID_B = 707
GRID_C_NO_FEATURES = 555  # exists in dim_grid, deliberately has NO grid_features row
_RICH_DAYS = 3
_RICH_HOURS_PER_DAY = 24
_RICH_START = datetime(2020, 3, 1, 0, 0, 0)
_WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


def _build_rich_dim_time_rows():
    rows = []
    time_key = 1
    for d in range(_RICH_DAYS):
        day_dt = _RICH_START + timedelta(days=d)
        for h in range(_RICH_HOURS_PER_DAY):
            ts_dt = day_dt + timedelta(hours=h)
            rows.append(
                (
                    time_key,
                    ts_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    ts_dt.strftime("%Y-%m-%d"),
                    h,
                    _WEEKDAYS[ts_dt.weekday()],
                )
            )
            time_key += 1
    return rows


DIM_TIME_ROWS_RICH = _build_rich_dim_time_rows()
TOTAL_HOURS = _RICH_DAYS * _RICH_HOURS_PER_DAY  # 72
_LAST_TIME_KEY = TOTAL_HOURS
AS_OF_RICH = DIM_TIME_ROWS_RICH[-1][1]  # ts of the final hour -- default AS_OF
STALE_FEATURE_TS = DIM_TIME_ROWS_RICH[-25][1]  # exactly 24 hours before AS_OF_RICH

# Feature rows are inserted directly (not derived by running the placeholder
# pipeline against the fact rows above) -- API4's job is to SERVE stored
# features correctly, not to recompute them, so these tests deliberately
# decouple "is the serving/freshness/error logic correct" from "is the
# placeholder pipeline's math correct" (that's validated separately, by
# hand, against the real warehouse).
GRID_FEATURES_ROWS = [
    # grid_id, avg_activity, activity_growth, active_hours, peak_ratio,
    # variability, internet_share, feature_timestamp, data_quality_status, row_count
    (GRID_A, 100.5, 0.05, 71, 45.0, 1.2, 0.6, AS_OF_RICH, "ok", 72),          # fresh
    (GRID_B, 50.0, 0.0, 72, 1.0, 0.0, 0.5, STALE_FEATURE_TS, "ok", 72),       # 24h stale
]


# Small deterministic variation per hour-of-day so GRID_A's baseline has
# genuine, realistic non-zero variance (a perfectly flat baseline makes
# the z-score undefined -- real telecom activity is never that flat).
_GRID_A_HOURLY_VARIATION = [
    -6, -3, 0, 3, 6, 3, 0, -3, -6, -3, 0, 3, 6, 3, 0, -3,
    -6, -3, 0, 3, 6, 3, 0, -3,
]


def _build_rich_fact_rows():
    rows = []
    for time_key, ts, date, hour, day_of_week in DIM_TIME_ROWS_RICH:
        is_last_hour = time_key == _LAST_TIME_KEY
        if is_last_hour:
            grid_a_value = 5000.0  # the deliberate spike
        else:
            grid_a_value = 100.0 + _GRID_A_HOURLY_VARIATION[hour]
        rows.append((GRID_A, time_key, grid_a_value))
        rows.append((GRID_B, time_key, 50.0))
    return rows


FACT_ROWS_RICH = _build_rich_fact_rows()


@pytest.fixture()
def rich_db_path(tmp_path):
    db_path = tmp_path / "test_network_analytics_rich.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(DDL)
    conn.executemany("INSERT INTO dim_time VALUES (?, ?, ?, ?, ?)", DIM_TIME_ROWS_RICH)
    conn.executemany(
        "INSERT INTO dim_grid VALUES (?, ?, ?, ?)",
        [
            (GRID_A, 45.46, 9.19, "{}"),
            (GRID_B, 45.47, 9.20, "{}"),
            (GRID_C_NO_FEATURES, 45.48, 9.21, "{}"),
        ],
    )
    conn.executemany(
        """INSERT INTO fact_network_activity
           (grid_id, time_key, sms_in, sms_out, call_in, call_out,
            internet_activity, total_sms, total_calls, total_activity)
           VALUES (?, ?, 0, 0, 0, 0, 0, 0, 0, ?)""",
        FACT_ROWS_RICH,
    )
    conn.executemany(
        """INSERT INTO grid_features
           (grid_id, avg_activity, activity_growth, active_hours, peak_ratio,
            variability, internet_share, feature_timestamp, data_quality_status, row_count)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        GRID_FEATURES_ROWS,
    )
    conn.commit()
    conn.close()
    return str(db_path)


@pytest.fixture()
def rich_client(rich_db_path, monkeypatch):
    import app.db as db_module

    monkeypatch.setattr(db_module, "DB_PATH", rich_db_path)
    with TestClient(app) as c:
        yield c
