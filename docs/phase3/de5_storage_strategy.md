DE5 — Storage Strategy & Data Zones Contract
Decisions by Mohammed Marzook, documented by Claude
Zone-by-Zone Storage Strategy
Zone	Format	Write Mode	Retention	Partitioning
data/landing/	CSV (as-arrived)	Transient — files removed once routed by ingestion (DE2)	N/A (nothing stays here)	None
data/raw/	CSV (unchanged)	Append — new daily files added, never overwritten	Keep forever — immutable audit trail	None (flat, one file per day)
data/rejected/	CSV (unchanged)	Append — one file per rejected input	Keep forever — needed to debug why a file failed	None
data/reference/	GeoJSON (static)	Overwrite only on the rare occasion the underlying grid changes; never touched by daily runs	Keep forever (it's one small static file)	Not date-partitioned — it's not a daily artifact
data/processed/	Parquet	Target: append new date partitions without touching existing ones. Current reality: full overwrite every run — see Known Limitation below	Keep forever	Date-partitioned (date=YYYY-MM-DD/)
data/analytics/	Parquet (current) / SQL warehouse (target, DE6)	Same append/overwrite tension as processed — see Known Limitation	Keep forever	Not partitioned by date today; DE6 may change this
logs/	JSON Lines (audit log)	Append — one record per file processed, ever	Keep forever — small, valuable history	None
Why raw is retained unchanged (immutable)

If raw data were ever modified or deleted after acceptance, it becomes impossible to re-derive processed/ and analytics/ from scratch if a bug is ever found in the Spark cleaning/aggregation logic. Raw is the one layer that must always be trustworthy enough to replay history from — every other layer can theoretically be deleted and rebuilt from raw, but raw itself has nothing to rebuild from if it's lost or altered.

Why the GeoJSON is static reference data, not a daily artifact

milano-grid.geojson describes the physical shape of Milan's grid cells — a property of the city, not a property of any single day's activity. It doesn't arrive daily, doesn't need daily validation, and partitioning it by date would be meaningless (there's no "November 8th version" of Milan's geography). It is loaded once and reused by every run, which is exactly why DE1 kept it in a separate reference zone from the start.

⚠️ Known Limitation: processed/ and analytics/ don't yet honor "append"

Target design: each pipeline run should only process newly arrived raw files and add a new date-partition to processed/, leaving prior partitions untouched — this is what "append" means for a partitioned Parquet layer.

Current reality: telecom_pipeline.py's write_outputs() function calls shutil.rmtree() on the entire processed/ and analytics/ directories at the start of every run, then reprocesses every file currently sitting in data/raw/ from scratch. This was a reasonable simplification while the pipeline only handled a handful of files (Phase 2's 7-day dataset), but it does not match the append semantics documented above, and it will become progressively more expensive as raw/ grows over time (since raw/ is append-only and kept forever).

This is documented here as a known gap, not silently ignored. A future iteration (naturally fitting into DE6 or DE7's incremental pipeline work) would change telecom_pipeline.py to:

Only read raw files newer than the last successful run, and
Write only the new date-partition(s) to processed/, without deleting or touching existing partitions.
Directory Structure
data/
├── landing/                          # transient - files pass through
├── raw/                              # immutable, append-only, kept forever
│   └── sms-call-internet-mi-YYYY-MM-DD.csv
├── rejected/                         # append-only, kept forever
│   └── sms-call-internet-mi-YYYY-MM-DD.csv
├── reference/                        # static, NOT date-partitioned
│   └── milano-grid.geojson
├── processed/
│   └── activity/
│       └── date=YYYY-MM-DD/          # date-partitioned Parquet
│           └── part-0.parquet
└── analytics/
    ├── hourly_grid_summary/
    │   └── part-0.parquet
    └── dashboard_summary.csv

logs/
└── ingestion_log.jsonl               # append-only, kept forever
Append vs Overwrite — reviewed per layer, not one blanket rule
Layer	Semantics	Reasoning
raw, rejected, logs	Append	These are historical records — overwriting would destroy audit trail
reference	Overwrite (rare, manual)	Only changes if Milan's grid itself changes, which is not a daily event
processed, analytics	Append (target) / Overwrite (current)	See Known Limitation above — this is the one zone where the current implementation and the intended design genuinely differ