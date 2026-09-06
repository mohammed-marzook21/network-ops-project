# API4 — `GET /network/grid/{grid_id}/features`

Serves the stored ML feature vector for one grid. **This endpoint only
reads — it never computes a feature.**

## ⚠️ Status: ML2 has not been built yet

The real feature-engineering pipeline (`ml/features.py`, produced by the
ML2 lab) doesn't exist in this project yet. What you have instead:

- **`ml/features_placeholder.py`** — computes real (not fabricated)
  feature values from your actual `fact_network_activity`/`dim_time`
  data, using the exact schema and column names ML2 is supposed to
  produce. Run it once to populate `grid_features`.
- **API4 reads `grid_features` exactly as if it were ML2's real output.**
  When ML2 is eventually built, it only needs to write to the same table
  with the same column names — **this API, its route, its service, and
  its Pydantic model do not need to change at all.**

Treat `ml/features_placeholder.py` as scaffolding to delete once ML2
ships, not as a deliverable in its own right.

## Path parameter

| name      | type | notes                                                          |
|-----------|------|--------------------------------------------------------------------|
| `grid_id` | int  | 1–10000. Outside that range, or missing from `dim_grid` → 404.     |

## Response — `GridFeaturesResponse`

| field                 | type          | meaning                                                              |
|-----------------------|---------------|--------------------------------------------------------------------------|
| `grid_id`             | int           |                                                                        |
| `avg_activity`        | float         | Mean `total_activity` across all observed hours                       |
| `activity_growth`     | float\|null   | (avg on last observed date − avg on first observed date) / avg on first |
| `active_hours`        | int           | Count of hours with `total_activity > 0`                              |
| `peak_ratio`          | float\|null   | `max(total_activity) / avg_activity`                                  |
| `variability`         | float\|null   | Coefficient of variation (`std / mean`) of `total_activity`            |
| `internet_share`      | float\|null   | `avg(internet_activity) / avg(total_activity)`                        |
| `feature_timestamp`   | string        | The `AS_OF` the stored snapshot reflects                              |
| `data_quality_status` | string        | `"ok"` or `"insufficient_data"` (< 24 observed hours)                  |
| `row_count`           | int           | Number of fact rows this snapshot was computed from                   |
| `feature_age_hours`   | float         | Hours between `feature_timestamp` and the warehouse's **current** AS_OF — computed live at request time, not stored |

The six fields `avg_activity`, `activity_growth`, `active_hours`,
`peak_ratio`, `variability`, `internet_share` are the exact ML2 feature
set named in the lab spec, character-for-character. **Once ML2 is built
for real, re-verify these still match `ml/features.py`'s actual column
names** — `tests/test_network_features.py::test_placeholder_pipeline_and_api_schema_use_identical_field_names`
only proves the placeholder and this API agree with *each other*, not
that they'll agree with the real ML2 output. This is a known follow-up,
not something already guaranteed.

## Errors

| status | when                                                                       |
|--------|--------------------------------------------------------------------------------|
| 404    | `grid_id` outside 1–10000, or missing from `dim_grid`                          |
| 404    | `grid_id` valid but has no row in `grid_features` yet (pipeline hasn't run for it) |
| 500    | `grid_features` table doesn't exist at all (pipeline never run), or warehouse file missing |

Note the two distinct 404 cases are deliberately both 404 (not 404 vs
some other code) because from the caller's point of view both mean "no
feature data available for this grid_id" — but they're raised by
different exceptions internally (`UnknownGridError` vs
`FeaturesNotFoundError`) so you can tell them apart in logs/tests if
needed.

## Data source

`grid_features` only. **No arithmetic on feature values happens in the
route or service** — enforced by an AST-based static test
(`test_no_feature_arithmetic_in_api_layer`) that parses the route file
and fails if it finds any `+ - * /` operator at all. The only computed
value in the whole response is `feature_age_hours`, which is explicitly
request-time staleness metadata, not a feature.

## Setting this up on your machine

```powershell
cd C:\network-ops-project
python -m ml.features_placeholder
```
This populates `grid_features` for every grid that has at least one row
in `fact_network_activity`. Grids with zero activity rows get no
`grid_features` row at all (so requesting their features correctly 404s
as "no stored features" rather than fabricating zeros).

Re-run this script any time `fact_network_activity` gets new data — until
ML2 automates it, `feature_age_hours` will just keep growing for every
grid until you do.

## Acceptance criteria status

- [x] The six feature names match the lab spec's names exactly, character for character.
- [x] No feature arithmetic exists in the API layer (route/service) — statically verified.
- [x] Response includes `feature_timestamp` and a freshness indicator (`feature_age_hours`).
- [x] A grid with no stored features returns a clear error rather than zeros.
- [ ] **Not yet verifiable**: "match `ml/features.py` exactly" — there is no real `ml/features.py` yet. Re-check this once ML2 ships.
