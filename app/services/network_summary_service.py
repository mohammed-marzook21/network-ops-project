"""
Network summary service layer.
Phase 4, Network Operations Predictive Intelligence Project

All actual SQL logic lives here, not in the route handler -- the route
should only ever call this function and translate its result/errors
into an HTTP response. This mirrors the same "thin orchestration layer,
real logic elsewhere" principle used throughout Phase 3 (DAGs calling
ingestion.py/telecom_pipeline.py rather than containing logic inline).

IMPORTANT: this queries fact_network_activity (the grid/hour analytics
layer, AFTER country-code aggregation) -- never any raw, country-code-
level data. There is no raw CSV access anywhere in this module.
"""

from app.db import get_connection


def get_effective_as_of(conn, requested_as_of=None):
    """
    Returns the as_of timestamp to actually use for a query. If the
    caller provided one, use it (after validating it exists in the
    data). Otherwise, default to MAX(ts) in dim_time -- NEVER a
    hardcoded date.
    """
    if requested_as_of is not None:
        exists = conn.execute(
            "SELECT 1 FROM dim_time WHERE ts = ? LIMIT 1", (requested_as_of,)
        ).fetchone()
        if not exists:
            raise ValueError(f"as_of value '{requested_as_of}' does not exist in the analytics layer")
        return requested_as_of

    row = conn.execute("SELECT MAX(ts) as max_ts FROM dim_time").fetchone()
    if row is None or row["max_ts"] is None:
        raise ValueError("No data available in the analytics layer to determine AS_OF")
    return row["max_ts"]


def get_network_summary(requested_as_of=None):
    """
    Computes the network summary KPIs as of a given timestamp (or the
    latest available timestamp if none is given). Every query here is
    bounded by as_of, so the response is always reproducible: calling
    this twice with the same explicit as_of always returns the same
    result, even as new data is added later.
    """
    conn = get_connection()
    try:
        as_of = get_effective_as_of(conn, requested_as_of)

        total_activity_row = conn.execute(
            """
            SELECT SUM(f.total_activity) as total_activity
            FROM fact_network_activity f
            JOIN dim_time t ON f.time_key = t.time_key
            WHERE t.ts <= ?
            """,
            (as_of,),
        ).fetchone()
        total_activity = total_activity_row["total_activity"] or 0.0

        active_grids_row = conn.execute(
            """
            SELECT COUNT(DISTINCT f.grid_id) as active_grids
            FROM fact_network_activity f
            JOIN dim_time t ON f.time_key = t.time_key
            WHERE t.ts <= ? AND f.total_activity > 0
            """,
            (as_of,),
        ).fetchone()
        active_grids = active_grids_row["active_grids"] or 0

        peak_hour_row = conn.execute(
            """
            SELECT t.hour as hour, SUM(f.total_activity) as hour_total
            FROM fact_network_activity f
            JOIN dim_time t ON f.time_key = t.time_key
            WHERE t.ts <= ?
            GROUP BY t.hour
            ORDER BY hour_total DESC
            LIMIT 1
            """,
            (as_of,),
        ).fetchone()
        peak_hour = peak_hour_row["hour"] if peak_hour_row else None

        top_grid_row = conn.execute(
            """
            SELECT f.grid_id as grid_id, SUM(f.total_activity) as grid_total
            FROM fact_network_activity f
            JOIN dim_time t ON f.time_key = t.time_key
            WHERE t.ts <= ?
            GROUP BY f.grid_id
            ORDER BY grid_total DESC
            LIMIT 1
            """,
            (as_of,),
        ).fetchone()
        top_grid = top_grid_row["grid_id"] if top_grid_row else None

        return {
            "total_activity": total_activity,
            "active_grids": active_grids,
            "peak_hour": peak_hour,
            "top_grid": top_grid,
            "as_of": as_of,
        }
    finally:
        conn.close()