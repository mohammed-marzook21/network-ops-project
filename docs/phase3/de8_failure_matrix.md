DE8 — Network Pipeline Reliability Challenge
Failure Handling Matrix
Investigation Method

Per the guide's explicit instruction, no code was changed until each fault type was first investigated against the ACTUAL existing DE2/DE3/DE7 codebase. Observed behavior below is evidence from real test runs, not assumption.

Failure Handling Matrix
#	Fault Type	Action	Evidence Source
1	Missing daily file	WARN	New: check_expected_files() — compares expected date range against what's actually present in landing/raw, logs missing dates without failing the pipeline
2	Duplicate ingestion attempt	CONTINUE	OBSERVED: ingestion.py's already_processed() returns skipped_duplicate for any filename already logged as accepted
3	Malformed timestamp	REJECT	OBSERVED: validate_minimum_quality() returns "Malformed timestamp at line X: '...'"
4	Negative activity value	REJECT	OBSERVED: validate_minimum_quality() returns "Negative value in 'col' at line X: ..."
5	Missing/unexpected column	REJECT	OBSERVED: validate_schema() returns "Missing required column(s): ..." or "Unexpected extra column(s): ..."
6	Partially corrupt file	REJECT	OBSERVED (tested live): a file with valid rows, then genuinely garbled bytes mid-file, then more valid rows, was correctly caught by the existing malformed-timestamp check — no new code required, confirmed by test, not assumed
7	Spark job failure	FAIL	OBSERVED: DE7's live test (bad reference dir) — run_spark_job fails, load_warehouse is skipped (never runs on stale data), quality_check still writes a FAILED status record
Why "missing daily file" is WARN, not FAIL

(This is the one judgment call in this matrix that's genuinely mine to defend, not something already implemented — worth being ready to explain: hard-failing an entire pipeline run because one day's file is absent would also block processing of every OTHER day that DID arrive correctly. Missing data can be backfilled later once the file shows up; losing a day's worth of otherwise-good processing over it is a worse outcome than a logged warning.)

Three Implemented Controls, Demonstrated Live
REJECT — malformed timestamp, negative value, and missing column all demonstrated via validate_schema()/validate_minimum_quality() test runs (see test_de8_faults.py).
CONTINUE — duplicate ingestion attempt demonstrated via DE7's held-back-file test (re-dropping an already-accepted filename).
FAIL — Spark job failure demonstrated via DE7's bad-reference-dir test, with quality_check still producing a distinguishable status record.
Safe Rerun Demonstration

See DE7's idempotency test: warehouse row count before and after a forced-failure-then-fix-then-rerun cycle remained consistent, with the mandatory (grid_id, timestamp) duplicate-grain check returning 0 both times.

Each Failure Produces a Distinguishable Status Record

DE7's quality_check_task writes task_status (per-task state) into every status record — a REJECT-heavy run shows process_files still success but with rejected files counted in rows_rejected, while a Spark FAIL run shows run_spark_job: failed and load_warehouse: skipped explicitly, making every fault type distinguishable by inspecting the record alone, without reading raw logs.