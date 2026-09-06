# API3 — `GET /network/hotspots` & `GET /network/alerts`

Two distinct rules, deliberately kept separate:

- **Hotspots** = the current highest-activity grids network-wide, at the single hour `== as_of`. A ranking, not an anomaly detector.
- **Alerts** = the NP3 rule-based anomaly rule: each grid's activity at `as_of` compared against **its own** historical mean/std (computed over every hour strictly *before* `as_of` — leave-one-out, so a genuine spike doesn't dilute its own baseline). No ML model is involved yet — this is the "rules" half of the rules-to-ML evolution ML6 will complete later.

## Query parameters (both endpoints)

| name       | type   | default | notes                                                          |
|------------|--------|---------|------------------------------------------------------------------|
| `limit`    | int    | 20      | 1–1000                                                            |
| `severity` | string | none    | Hotspots: filters on `status` (currently only `"elevated"` exists). Alerts: filters on `severity` (`"high"` or `"medium"`). |
| `as_of`    | string | latest  | Must exist in `dim_time` if provided.                             |

## `GET /network/hotspots` response — `HotspotsResponse`

```json
{
  "as_of": "2013-11-07 23:00:00",
  "count": 20,
  "hotspots": [
    {
      "grid_id": 5161,
      "ts": "2013-11-07 23:00:00",
      "hour": 23,
      "total_activity": 82634.11,
      "status": "elevated",
      "reason": "Ranked #1 by total network activity at this hour.",
      "risk_score": null,
      "risk_level": null,
      "model_version": null
    }
  ]
}
```
Ordered by `total_activity DESC, grid_id ASC` — the `grid_id` tiebreaker is what makes repeated identical requests return an identical order even when activity values tie.

## `GET /network/alerts` response — `AlertsResponse`

```json
{
  "as_of": "2013-11-07 23:00:00",
  "count": 4,
  "alerts": [
    {
      "grid_id": 5161,
      "ts": "2013-11-07 23:00:00",
      "hour": 23,
      "total_activity": 82634.11,
      "baseline_activity": 19042.55,
      "severity": "high",
      "reason": "Activity is 3.4 standard deviations above this grid's historical average (19042.6).",
      "risk_score": null,
      "risk_level": null,
      "model_version": null
    }
  ]
}
```
`severity` thresholds: z ≥ 3.0 → `"high"`, z ≥ 2.0 → `"medium"`, below that → not returned at all. Ordered by z-score descending, `grid_id` ascending tiebreak.

## Why `risk_score` / `risk_level` / `model_version` are already there, always null

ML6 will eventually populate these from a trained model. Because they're already present and nullable, adding real values later is a **pure addition** to the contract — no field renames, no shape changes, nothing the React client has to change to keep working. `tests/test_network_intelligence.py::test_adding_a_future_nullable_field_does_not_break_parsing` demonstrates this directly: it defines a hypothetical future schema with one *more* optional field than the server currently sends, and confirms the real response still parses cleanly against it.

## The word "congestion"

Does not appear anywhere in these two files, the Pydantic schemas, or the OpenAPI output — enforced by `test_hotspots_word_congestion_never_appears` / `test_alerts_word_congestion_never_appears`, which scan both the live JSON response and the full `/openapi.json` schema text.

## Errors

| status | when                                              |
|--------|---------------------------------------------------|
| 400    | `as_of` provided but not present in `dim_time`     |
| 500    | warehouse database file missing/unreadable         |

## Acceptance criteria status

- [x] `limit` is respected exactly.
- [x] "congestion" appears nowhere in response, schema, or docs.
- [x] Adding a nullable `risk_score`-style field later would not break an existing client — demonstrated with a test using a hypothetical expanded schema.
- [x] Results are ordered deterministically (grid_id tiebreak on both endpoints).

## Manual validation (run against the real warehouse)

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/network/hotspots?limit=5"
Invoke-RestMethod "http://127.0.0.1:8000/network/alerts"
```
Cross-check the top hotspot's `grid_id`/`total_activity` against:
```sql
SELECT f.grid_id, f.total_activity
FROM fact_network_activity f JOIN dim_time t ON f.time_key = t.time_key
WHERE t.ts = '2013-11-07 23:00:00'   -- use your real as_of
ORDER BY f.total_activity DESC LIMIT 5;
```

## Known limitation, worth knowing before you rely on this

The alerts rule computes a per-grid baseline over the grid's **entire** history up to `as_of`, not a day-of-week/hour-matched baseline. A grid that's naturally busy every Friday evening will alert every Friday evening indefinitely, since "Friday evening busy" never becomes part of its own "normal" if the naive overall mean is always pulled down by quieter hours. This is fine for a first rule-based pass (matches the lab's "initially serve the rule-based alerts" framing) but is exactly the kind of limitation ML6's real model should improve on — worth flagging in your own writeup as an intentional simplification, not an oversight.
