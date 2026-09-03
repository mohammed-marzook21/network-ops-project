import argparse
import sqlite3
from pathlib import Path

import pandas as pd


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS fact_network_activity (
    grid_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    total_sms REAL NOT NULL DEFAULT 0,
    total_calls REAL NOT NULL DEFAULT 0,
    total_activity REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (grid_id, timestamp)
)
"""


def load_warehouse(analytics_file: str, db_path: str) -> dict:
    analytics_path = Path(analytics_file)
    database_path = Path(db_path)

    if not analytics_path.exists():
        raise FileNotFoundError(
            f"Analytics file not found: {analytics_path}"
        )

    database_path.parent.mkdir(parents=True, exist_ok=True)

    df = pd.read_parquet(analytics_path)

    required_columns = {
        "grid_id",
        "timestamp",
        "total_sms",
        "total_calls",
        "total_activity",
    }

    missing = required_columns - set(df.columns)
    if missing:
        raise ValueError(
            f"Analytics file is missing columns: {sorted(missing)}"
        )

    rows_in = len(df)

    # Enforce the expected warehouse grain before loading.
    duplicates = int(
        df.duplicated(subset=["grid_id", "timestamp"]).sum()
    )

    if duplicates:
        raise ValueError(
            f"Duplicate warehouse grain detected: {duplicates} rows"
        )

    with sqlite3.connect(database_path) as conn:
        conn.execute(CREATE_TABLE_SQL)

        rows_published = 0

        for row in df.itertuples(index=False):
            conn.execute(
                """
                INSERT INTO fact_network_activity (
                    grid_id,
                    timestamp,
                    total_sms,
                    total_calls,
                    total_activity
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(grid_id, timestamp)
                DO UPDATE SET
                    total_sms = excluded.total_sms,
                    total_calls = excluded.total_calls,
                    total_activity = excluded.total_activity
                """,
                (
                    int(row.grid_id),
                    str(row.timestamp),
                    float(row.total_sms),
                    float(row.total_calls),
                    float(row.total_activity),
                ),
            )
            rows_published += 1

        conn.commit()

        warehouse_rows = conn.execute(
            "SELECT COUNT(*) FROM fact_network_activity"
        ).fetchone()[0]

        as_of = conn.execute(
            "SELECT MAX(timestamp) FROM fact_network_activity"
        ).fetchone()[0]

    return {
        "rows_in": rows_in,
        "rows_published": rows_published,
        "warehouse_rows": warehouse_rows,
        "as_of": as_of,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--analytics-file", required=True)
    parser.add_argument("--db", required=True)
    args = parser.parse_args()

    result = load_warehouse(
        analytics_file=args.analytics_file,
        db_path=args.db,
    )

    print(result)


if __name__ == "__main__":
    main()
