"""
DE6 - Load hourly_grid_summary into the star schema.
Phase 3, Network Operations Predictive Intelligence Project
"""

import json
import sqlite3

import pandas as pd

DB_PATH = "network_analytics.db"
SCHEMA_PATH  = "warehouse/schema.sql"
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

GEOJSON_PATH = (
    PROJECT_ROOT
    / "data"
    / "reference"
    / "milano-grid.geojson"
)

HOURLY_SUMMARY_PATH = (
    PROJECT_ROOT
    / "data"
    / "phase2_output"
    / "analytics"
    / "hourly_grid_summary"
)

DB_PATH = PROJECT_ROOT / "warehouse" / "network_analytics.db"

SCHEMA_PATH = PROJECT_ROOT / "warehouse" / "schema.sql"

TIMESTAMP_COLUMN = "timestamp"
HOURLY_SUMMARY_PATH = (
    PROJECT_ROOT
    / "data"
    / "phase2_output"
    / "analytics"
    / "hourly_grid_summary"
    / "part-0.parquet"
)


def compute_centroid(geometry):
    ring = geometry["coordinates"][0]
    lons = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    return sum(lons) / len(lons), sum(lats) / len(lats)


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # ── Step 1: Apply schema ────────────────────────────────────────
    with open(SCHEMA_PATH) as f:
        cur.executescript(f.read())
    print("Schema applied.")

    # ── Step 2: Populate dim_grid ONCE from the static reference ────
    with open(GEOJSON_PATH) as f:
        gj = json.load(f)

    grid_rows = []
    for feat in gj["features"]:
        grid_id = feat["properties"]["cellId"]  # 1-based, NOT the 0-based 'id'
        lon, lat = compute_centroid(feat["geometry"])
        geometry_json = json.dumps(feat["geometry"])
        grid_rows.append((grid_id, lat, lon, geometry_json))

    cur.executemany(
        "INSERT INTO dim_grid (grid_id, centroid_lat, centroid_lon, geometry_json) VALUES (?, ?, ?, ?)",
        grid_rows,
    )
    conn.commit()
    print(f"dim_grid populated: {len(grid_rows)} rows")

    # ── Step 3: Load hourly_grid_summary ─────────────────────────────
    hgs = pd.read_parquet(HOURLY_SUMMARY_PATH)
    hgs["timestamp"] = pd.to_datetime(hgs["timestamp"])

    # ── Step 4: Populate dim_time (one row per distinct hour) ───────
    distinct_hours = hgs[["timestamp"]].drop_duplicates().copy()
    distinct_hours["time_key"] = distinct_hours["timestamp"].dt.strftime("%Y%m%d%H").astype(int)
    distinct_hours["date"] = distinct_hours["timestamp"].dt.strftime("%Y-%m-%d")
    distinct_hours["hour"] = distinct_hours["timestamp"].dt.hour
    distinct_hours["day_of_week"] = distinct_hours["timestamp"].dt.day_name()
    distinct_hours["ts"] = distinct_hours["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")

    time_rows = list(
        distinct_hours[["time_key", "ts", "date", "hour", "day_of_week"]].itertuples(index=False, name=None)
    )
    cur.executemany(
        "INSERT INTO dim_time (time_key, ts, date, hour, day_of_week) VALUES (?, ?, ?, ?, ?)",
        time_rows,
    )
    conn.commit()
    print(f"dim_time populated: {len(time_rows)} rows")

    # ── Step 5: Populate fact_network_activity ───────────────────────
    hgs["time_key"] = hgs["timestamp"].dt.strftime("%Y%m%d%H").astype(int)

    fact_cols = ["grid_id", "time_key", "sms_in", "sms_out", "call_in", "call_out",
                 "internet_activity", "total_sms", "total_calls", "total_activity"]
    fact_rows = list(hgs[fact_cols].itertuples(index=False, name=None))

    cur.executemany(
        f"INSERT INTO fact_network_activity ({', '.join(fact_cols)}) "
        f"VALUES ({', '.join(['?'] * len(fact_cols))})",
        fact_rows,
    )
    conn.commit()
    print(f"fact_network_activity populated: {len(fact_rows)} rows")

    conn.close()
    print("\n✅ Load complete.")


if __name__ == "__main__":
    main()