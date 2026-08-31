SP5 — Performance & Execution Behaviour: Observations

Phase 2, Network Operations Predictive Intelligence Project

Observation 1: Caching saves ~3.6x on repeated access, but only pays off with reuse

Evidence (from sp5_performance_diagnostics.py, Diagnostics 3 & 4):

Run	Time
Uncached, 1st .count()	5.98s
Uncached, 2nd .count()	5.35s
Cached, 1st .count() (populates cache)	8.54s
Cached, 2nd .count() (reads from cache)	1.49s

The fair comparison is uncached-2nd vs. cached-2nd (5.35s vs 1.49s) — both are "give me this result again" requests. The cached 1st call is slower than uncached, because it does the full computation plus stores the result; that upfront cost only pays off if the DataFrame is reused afterward.

Decision: ACCEPTED. hourly_grid_summary is reused 7+ times in SP4 alone (2 direct .count() calls, plus 5 more actions on grid_activity_geo_df, which is built on top of it). Without caching, Spark would re-read and re-aggregate all 7 raw CSVs on every one of those 7 calls. Caching is applied in sp5_applied_decisions.py.

Observation 2: Spark shuffles into 200 partitions regardless of source size

Evidence (from Diagnostic 1's explain() plan and Diagnostic 2's partition counts):

The Exchange step in the physical plan shows hashpartitioning(grid_id, timestamp, 200).
The actual source data (clean_network_df) only has 15 partitions.
200 is Spark's global default (spark.sql.shuffle.partitions), applied regardless of how much data is actually present.

Decision: REJECTED (no change made). Spark 3.5's Adaptive Query Execution (AQE) is enabled by default and can automatically coalesce small post-shuffle partitions at runtime, without any manual configuration. Manually overriding spark.sql.shuffle.partitions to match today's 15 source partitions would:

Hardcode a number that becomes stale the moment more data is added (e.g. future days' files), requiring the value to be revisited manually.
Solve a problem AQE may already be solving live, with no measured evidence the manual override does anything AQE isn't already doing.

Verified AQE is actually active in this environment (see sp5_applied_decisions.py output):

AQE enabled: true
AQE coalesce partitions: true

Given AQE is confirmed on, the manual override was rejected as unnecessary complexity without demonstrated benefit.

Observation 3: Column pruning has no effect on this dataset, because it's CSV

Evidence (from Diagnostic 5): two plans were compared — one selecting all columns before aggregating, one selecting only grid_id and sms_in first. Both plans show an identical ReadSchema, listing all 7 raw columns in both cases:

ReadSchema: struct<datetime:string,CellID:int,smsin:double,smsout:double,
callin:double,callout:double,internet:double>

Why: CSV is a row-based text format. Spark must parse an entire line before it can discard any column from it — there's no way to skip bytes for an unwanted column mid-row, the way there is with a columnar format like Parquet (where each column's data is stored contiguously and can be skipped entirely at the storage level). Selecting fewer columns earlier in the Python code changes what Spark's logical plan looks like, but not what bytes it physically reads from disk here.

Decision: NO ACTION — this isn't an accept/reject situation, it's a limitation of the file format itself. If this project later moves data into Parquet (a natural fit for Phase 3's processed/analytics layer), column pruning would become a real, measurable optimization worth re-testing.

Summary
#	Observation	Decision	Reason
1	Caching gives 3.6x speedup on reuse (5.35s → 1.49s)	Accepted	7+ reuses of hourly_grid_summary downstream justify the one-time cache cost
2	Shuffle partitions default to 200 vs. 15 source partitions	Rejected	AQE (confirmed enabled) likely already coalesces this at runtime; manual override adds stale hardcoding for unproven benefit
3	Column pruning doesn't reduce what's read from CSV	N/A (format limitation)	Would become relevant if/when this project moves to Parquet