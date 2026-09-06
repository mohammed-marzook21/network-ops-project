"""
Database connection helper.
Phase 4, Network Operations Predictive Intelligence Project
"""

import os
import sqlite3

DB_PATH = os.environ.get(
    "WAREHOUSE_DB_PATH",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "warehouse", "network_analytics.db"),
)


def get_connection():
    """
    Returns a new SQLite connection. Raises FileNotFoundError if the
    database doesn't exist, so callers can turn this into a clear 500
    error rather than a confusing low-level SQLite error.
    """
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"Warehouse database not found at {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn