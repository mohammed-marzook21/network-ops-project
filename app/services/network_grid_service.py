"""
Grid activity drill-down service layer.
Phase 4, Network Operations Predictive Intelligence Project

Reads exclusively from fact_network_activity (the grid/hour analytics
layer, already aggregated past country-code granularity) joined to
dim_time. One grid has exactly one record per hourly interval -- this
module never exposes country-code-level rows as if they were separate
grid observations.
"""
from app.db import get_connection
from app.services.time_utils import get_effective_as_of, window_start_before

MIN_GRID_ID = 1
MAX_GRID_ID = 10000
DEFAULT_WINDOW_HOURS = 24


class UnknownGridError(Exception):
    """grid_id is outside the valid range, or missing from dim_grid."""


def get_grid_activity(grid_id, date=None, hour=None, requested_as_of=None):
    """
    Returns the hourly activity series for one grid.

    Filter precedence:
      - `date` given (optionally with `hour`): returns exactly that
        date (optionally narrowed to one hour), bounded above by as_of.
      - `hour` given alone: returns that hour-of-day across every date
        up to as_of.
      - neither given: the trailing DEFAULT_WINDOW_HOURS hourly
        intervals ending at (and including) as_of -- the default window.

    grid_id outside 1-10000, or not present in dim_grid, raises
    UnknownGridError (-> 404). An as_of that doesn't exist in dim_time
    raises ValueError (-> 400), same convention as API1.
    """
    if grid_id < MIN_GRID_ID or grid_id > MAX_GRID_ID:
        raise UnknownGridError(
            f"grid_id {grid_id} is outside the valid range {MIN_GRID_ID}-{MAX_GRID_ID}"
        )

    conn = get_connection()
    try:
        exists = conn.execute(
            "SELECT 1 FROM dim_grid WHERE grid_id = ? LIMIT 1", (grid_id,)
        ).fetchone()
        if not exists:
            raise UnknownGridError(f"grid_id {grid_id} was not found in dim_grid")

        as_of = get_effective_as_of(conn, requested_as_of)

        params = [grid_id]
        where_clauses = ["f.grid_id = ?"]
        window_start = None

        if date is not None:
            where_clauses.append("t.date = ?")
            params.append(date)
            if hour is not None:
                where_clauses.append("t.hour = ?")
                params.append(hour)
            where_clauses.append("t.ts <= ?")
            params.append(as_of)
        elif hour is not None:
            where_clauses.append("t.hour = ?")
            params.append(hour)
            where_clauses.append("t.ts <= ?")
            params.append(as_of)
        else:
            window_start = window_start_before(as_of, DEFAULT_WINDOW_HOURS)
            where_clauses.append("t.ts BETWEEN ? AND ?")
            params.extend([window_start, as_of])

        sql = f"""
            SELECT
                t.ts as ts,
                t.hour as hour,
                f.total_sms as sms_activity,
                f.total_calls as call_activity,
                f.internet_activity as internet_activity,
                f.total_activity as total_activity
            FROM fact_network_activity f
            JOIN dim_time t ON f.time_key = t.time_key
            WHERE {' AND '.join(where_clauses)}
            ORDER BY t.ts ASC
        """
        rows = conn.execute(sql, params).fetchall()
        series = [dict(row) for row in rows]

        return {
            "grid_id": grid_id,
            "as_of": as_of,
            "window_start": window_start,
            "window_end": as_of,
            "point_count": len(series),
            "series": series,
        }
    finally:
        conn.close()
