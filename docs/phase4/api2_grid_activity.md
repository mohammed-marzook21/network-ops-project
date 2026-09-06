# API2 — `GET /network/grid/{grid_id}`

Hourly activity drill-down for one grid.

## Path parameter

| name      | type | notes                                                              |
|-----------|------|----------------------------------------------------------------------|
| `grid_id` | int  | Valid range 1–10000. Anything outside that range, or missing from `dim_grid`, returns 404. |

## Query parameters

| name    | type   | required | notes                                                                 |
|---------|--------|----------|--------------------------------------------------------------------------|
| `date`  | string | no       | e.g. `2013-11-03`. Returns that whole day (all matching hours).          |
| `hour`  | int    | no       | 0–23. Combine with `date` to select exactly one point.                   |
| `as_of` | string | no       | Upper bound for all filters. Defaults to `MAX(ts)` in `dim_time`.        |

### Filter precedence
1. **`date` given** (optionally with `hour`) → returns exactly that date (or that single hour within it), bounded above by `as_of`.
2. **`hour` given alone** → that hour-of-day across every date up to `as_of`.
3. **Neither given** → the trailing **24** hourly intervals ending at (and including) `as_of` — the default window, same convention API1 uses internally.

## Response — `GridActivityResponse`

| field          | type          | meaning                                                        |
|----------------|---------------|-------------------------------------------------------------------|
| `grid_id`      | int           | Echoes the requested grid                                      |
| `as_of`        | string        | Effective upper-bound timestamp used                            |
| `window_start` | string\|null  | Start of the trailing window. **Null** when an explicit `date`/`hour` filter was used instead. |
| `window_end`   | string        | Always equals `as_of`                                          |
| `point_count`  | int           | Number of points in `series`                                    |
| `series`       | array         | One entry per hour, ordered ascending by `ts`                   |

Each `series` item: `ts`, `hour`, `sms_activity` (= `total_sms`), `call_activity` (= `total_calls`), `internet_activity`, `total_activity` — all read directly from `fact_network_activity`, no arithmetic performed in the API layer.

## Errors

| status | when                                                                    |
|--------|--------------------------------------------------------------------------|
| 404    | `grid_id` outside 1–10000, or not present in `dim_grid`                  |
| 422    | malformed `date` (not `YYYY-MM-DD`) or `hour` outside 0–23                |
| 400    | `as_of` provided but not present in `dim_time`                           |
| 500    | warehouse database file missing/unreadable                               |

## Data source

`fact_network_activity` joined to `dim_time` only. One grid has exactly one row per hourly interval — this endpoint never exposes country-code-level rows as separate grid observations (there is no raw/country-code table in this schema at all; the real warehouse already stores pre-aggregated grid/hour totals).

## Acceptance criteria status

- [x] Grid 4821 returns exactly 24 points for the default window (verified against a synthetic 72-hour fixture; **you should also spot-check this against your real warehouse** — see manual validation below).
- [x] `grid_id` 0 and 10001 both return 404 (parametrized test also covers -5 and 999999).
- [x] No timestamp appears twice in a single response.
- [x] Values match the warehouse exactly for a spot-checked hour (fields are passed straight through, no computed arithmetic to drift).

## Manual validation (run this yourself against the real warehouse)

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/network/grid/4821"
```
Then compare the first and last `series` entries against:
```sql
SELECT t.ts, t.hour, f.total_sms, f.total_calls, f.internet_activity, f.total_activity
FROM fact_network_activity f JOIN dim_time t ON f.time_key = t.time_key
WHERE f.grid_id = 4821
ORDER BY t.ts DESC LIMIT 24;
```
(reverse the order to compare against the ascending API response).
