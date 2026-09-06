"""
Shared AS_OF resolution helper.
Phase 4, Network Operations Predictive Intelligence Project

Used by API2 (grid drill-down) and API3 (hotspots/alerts) so both derive
"the current reporting instant" the same way. API1's own copy in
network_summary_service.py is left untouched on purpose -- it's already
tested and shipped; this file exists so we don't duplicate the same
logic a third and fourth time.
"""
from datetime import datetime, timedelta


def get_effective_as_of(conn, requested_as_of=None):
    """
    Returns the as_of timestamp to actually use. If the caller provided
    one, validate it exists in dim_time and use it. Otherwise default to
    MAX(ts) in dim_time -- NEVER a hardcoded date.
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


def window_start_before(as_of_ts: str, hours: int) -> str:
    """Returns the timestamp `hours` hourly intervals before as_of_ts,
    inclusive -- i.e. the start of a trailing window ending at as_of_ts.
    """
    dt = datetime.strptime(as_of_ts, "%Y-%m-%d %H:%M:%S")
    start = dt - timedelta(hours=hours - 1)
    return start.strftime("%Y-%m-%d %H:%M:%S")
