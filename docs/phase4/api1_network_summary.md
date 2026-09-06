# API1 — `GET /network/summary`

Top-level NOC KPIs, computed **cumulatively** over all analytics-layer data
up to and including the effective `as_of` timestamp.

## Query parameters

| name    | type   | required | notes                                                                                     |
|---------|--------|----------|----------------------------------------------------------------------------------------------|
| `as_of` | string | no       | Must exactly match an existing `dim_time.ts` value if provided. Defaults to `MAX(ts)` in `dim_time`. |

`as_of` is validated against `dim_time` before use — a value that doesn't
exist in the data (including malformed strings) returns `400`, not a
silent fallback and not a 500.

## Response — `NetworkSummaryResponse`

| field            | type  | meaning                                                                 |
|------------------|-------|--------------------------------------------------------------------------|
| `total_activity` | float | `SUM(total_activity)` across every grid/hour row with `ts <= as_of`      |
| `active_grids`   | int   | Distinct `grid_id` with `total_activity > 0` at any point up to `as_of` |
| `peak_hour`      | int   | The hour-of-day (0–23) with the highest `total_activity` summed across **all days** up to `as_of` — not a single timestamp |
| `top_grid`       | int   | The `grid_id` with the highest summed `total_activity` up to `as_of`    |
| `as_of`          | str   | Effective reporting timestamp this response was computed against        |

## Window definition

This is **cumulative-to-date**, not a trailing window: every KPI is
computed over `WHERE t.ts <= :as_of`, so the reporting window always
starts at the beginning of the analytics layer's history and grows as
`as_of` moves forward. `peak_hour` in particular is "which hour of the day
has historically been busiest so far", built by grouping on `dim_time.hour`
(0–23) rather than a specific timestamp — that's why the example value is
`17`, not a full datetime.

## Data source

Reads exclusively from `fact_network_activity` joined to `dim_time`
(the analytics layer, already aggregated past raw country-code granularity
in Phase 1–3). Never touches raw/country-code-level rows — there is no
raw-CSV access anywhere in `network_summary_service.py`.

## Errors

| status | when                                                                              |
|--------|-------------------------------------------------------------------------------------|
| 400    | `as_of` provided but doesn't match any `dim_time.ts` value (includes malformed strings) |
| 500    | The warehouse database file is missing/unreadable (`FileNotFoundError` from `db.py`)    |

## Equivalent hand-run SQL

```sql
-- total_activity
SELECT SUM(f.total_activity)
FROM fact_network_activity f JOIN dim_time t ON f.time_key = t.time_key
WHERE t.ts <= :as_of;

-- active_grids
SELECT COUNT(DISTINCT f.grid_id)
FROM fact_network_activity f JOIN dim_time t ON f.time_key = t.time_key
WHERE t.ts <= :as_of AND f.total_activity > 0;

-- peak_hour (hour-of-day, not a timestamp)
SELECT t.hour, SUM(f.total_activity) AS hour_total
FROM fact_network_activity f JOIN dim_time t ON f.time_key = t.time_key
WHERE t.ts <= :as_of
GROUP BY t.hour ORDER BY hour_total DESC LIMIT 1;

-- top_grid
SELECT f.grid_id, SUM(f.total_activity) AS grid_total
FROM fact_network_activity f JOIN dim_time t ON f.time_key = t.time_key
WHERE t.ts <= :as_of
GROUP BY f.grid_id ORDER BY grid_total DESC LIMIT 1;
```

## Known local-environment note

`app/db.py`'s default `DB_PATH` originally resolved one directory level
too high (`C:\warehouse\...` instead of `C:\network-ops-project\warehouse\...`)
because of an extra `os.path.dirname()` call. Fixed to:

```python
os.path.join(os.path.dirname(os.path.dirname(__file__)), "warehouse", "network_analytics.db")
```

## Acceptance criteria status

- [x] Response matches a hand-run SQL query on every field (see `tests/test_network_summary.py`, hand-computed against a fixture built from the real `dim_time`/`dim_grid`/`fact_network_activity` schema).
- [x] Every successful response includes the effective `as_of`.
- [x] No date literal appears anywhere in `app/db.py` or `app/services/network_summary_service.py` (statically verified by `test_no_hardcoded_date_literals_in_logic_code`). Note: the Swagger example dates in `models/network_summary.py` and the `Query(description=...)` text in the route are documentation strings, not logic, and are intentionally excluded from this check.
- [x] Swagger renders `NetworkSummaryResponse` correctly (`/docs`, verified via `/openapi.json`).

## Suggested follow-up (not blocking)

`NetworkSummaryResponse.Config` uses the Pydantic v1-style class-based
config, which raises a deprecation warning under Pydantic v2 and will stop
working under v3. Low priority now, worth a one-line fix before this
project is handed off long-term:

```python
from pydantic import BaseModel, ConfigDict, Field

class NetworkSummaryResponse(BaseModel):
    model_config = ConfigDict(json_schema_extra={...})
```
