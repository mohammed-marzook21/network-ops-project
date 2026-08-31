"""
SP6 - Write Processed & Analytics Data
Phase 2, Network Operations Predictive Intelligence Project

Persists Spark outputs as Parquet (processed + analytics layers) and CSV
(dashboard layer), then validates the round-trip.

Environment-specific fixes applied (see docs/environment_known_issues.md):
- spark.driver.memory raised to 6g (default 1g caused OOM during aggregation)
- clean_network_df is NOT cached (reduces memory pressure; it's cheap enough
  to recompute per date-partition below)
- Writes use pandas+pyarrow instead of Spark's native writer (winutils.exe
  DLL error on this Windows machine breaks Spark's write-side file commit)
- Timestamps downcast to microsecond precision before writing (pyarrow
  defaults to nanosecond precision, which Spark's Parquet reader rejects)
- Round-trip reads target explicit files, not parent directories (avoids
  the same native Windows directory-listing crash seen in SP1)
"""

import os
os.environ["JAVA_HOME"] = r"C:\Program Files\Java\jdk-17"
os.environ["HADOOP_HOME"] = r"C:\network-ops-project\tools\hadoop"
os.environ["PATH"] = os.environ["JAVA_HOME"] + r"\bin;" + os.environ["HADOOP_HOME"] + r"\bin;" + os.environ["PATH"]

import glob
import shutil
import time
from pyspark.sql import SparkSession
from pyspark.sql.types import StructType, StructField, StringType, IntegerType, DoubleType
from pyspark.sql.functions import col, to_timestamp, when, lit, date_format, hour as spark_hour, coalesce, sum as spsum

spark = (
    SparkSession.builder
    .appName("SP6_WriteProcessedAnalytics")
    .config("spark.driver.memory", "6g")
    .getOrCreate()
)
spark.sparkContext.setLogLevel("ERROR")

RENAME_MAP = {
    "datetime": "timestamp", "CellID": "grid_id", "countrycode": "country_code",
    "smsin": "sms_in", "smsout": "sms_out", "callin": "call_in",
    "callout": "call_out", "internet": "internet_activity",
}
ACTIVITY_COLS = ["sms_in", "sms_out", "call_in", "call_out", "internet_activity"]

raw_schema = StructType([
    StructField("datetime", StringType(), True),
    StructField("CellID", IntegerType(), True),
    StructField("countrycode", IntegerType(), True),
    StructField("smsin", DoubleType(), True),
    StructField("smsout", DoubleType(), True),
    StructField("callin", DoubleType(), True),
    StructField("callout", DoubleType(), True),
    StructField("internet", DoubleType(), True),
])

# ── Rebuild clean_network_df and hourly_grid_summary (SP1-SP3 logic) ──
file_list = sorted(glob.glob("data/raw/sms-call-internet-mi-*.csv"))
raw_df = spark.read.option("header", True).schema(raw_schema).csv(file_list)

df = raw_df
for old, new in RENAME_MAP.items():
    df = df.withColumnRenamed(old, new)
df = df.withColumn("timestamp", to_timestamp(col("timestamp")))

neg_mask = None
for c in ACTIVITY_COLS:
    cond = coalesce((col(c) < 0), lit(False))
    neg_mask = cond if neg_mask is None else (neg_mask | cond)
df = df.filter(~(col("grid_id").isNull() | col("timestamp").isNull())).filter(~neg_mask)
for c in ACTIVITY_COLS:
    df = df.withColumn(c, when(col(c).isNull(), lit(0.0)).otherwise(col(c)))
df = df.withColumn("date", date_format(col("timestamp"), "yyyy-MM-dd"))

# NOTE: NOT cached -- clean_network_df is reused below (once for the
# aggregation, once per date-partition write), but caching all 15M rows
# in addition to the hourly_grid_summary cache caused an out-of-memory
# error during the aggregation on this machine's default Spark memory
# split. Recomputing it per-date instead is a safer memory trade-off.
clean_network_df = df
clean_count = clean_network_df.count()

hourly_grid_summary = (
    clean_network_df.groupBy("grid_id", "timestamp")
    .agg(*[spsum(c).alias(c) for c in ACTIVITY_COLS])
)
hourly_grid_summary = hourly_grid_summary.withColumn("date", date_format(col("timestamp"), "yyyy-MM-dd"))
hourly_grid_summary = hourly_grid_summary.withColumn("hour", spark_hour(col("timestamp")))
hourly_grid_summary = hourly_grid_summary.withColumn("total_sms", col("sms_in") + col("sms_out"))
hourly_grid_summary = hourly_grid_summary.withColumn("total_calls", col("call_in") + col("call_out"))
hourly_grid_summary = hourly_grid_summary.withColumn(
    "total_activity", col("total_sms") + col("total_calls") + col("internet_activity")
)
hourly_grid_summary = hourly_grid_summary.cache()
hgs_count = hourly_grid_summary.count()

# Clean old outputs so this run isn't polluted by a previous attempt
shutil.rmtree("data/processed", ignore_errors=True)
shutil.rmtree("data/analytics", ignore_errors=True)

# ── Step 1-2: Write clean activity as Parquet, partitioned by date ─────
print("Writing data/processed/activity/ (Parquet, partitioned by date, via pandas+pyarrow)...")
dates = sorted([r["date"] for r in clean_network_df.select("date").distinct().collect()])
print(f"  {len(dates)} date partitions to write: {dates}")

for d in dates:
    t0 = time.time()
    part_pdf = clean_network_df.filter(col("date") == d).toPandas()
    part_pdf["timestamp"] = part_pdf["timestamp"].astype("datetime64[us]")
    out_dir = f"data/processed/activity/date={d}"
    os.makedirs(out_dir, exist_ok=True)
    part_pdf.to_parquet(f"{out_dir}/part-0.parquet", engine="pyarrow", index=False)
    print(f"  {d}: {len(part_pdf)} rows written in {time.time() - t0:.1f}s")

# ── Step 3: hourly_grid_summary as Parquet - NO geometry included ─────
# WHY no geometry here: this is a fact-shaped table (one row per
# grid+hour, ~1.68M rows). Geometry (the full Polygon coordinate list)
# is a STATIC property of a grid cell -- it doesn't change per hour. If
# geometry were duplicated into every one of these 1.68M rows, this file
# would store the exact same ~30-point polygon 168 times per grid cell
# for no reason. Geometry stays where it belongs: milano-grid.geojson,
# a single static reference file, joined in only when a specific
# consumer (e.g. a map-rendering API) actually needs it.
print("\nWriting data/analytics/hourly_grid_summary/ (Parquet, one row per grid+hour, no geometry)...")
os.makedirs("data/analytics/hourly_grid_summary", exist_ok=True)
hgs_pdf = hourly_grid_summary.toPandas()
hgs_pdf["timestamp"] = hgs_pdf["timestamp"].astype("datetime64[us]")
hgs_pdf.to_parquet("data/analytics/hourly_grid_summary/part-0.parquet", engine="pyarrow", index=False)
print(f"  {len(hgs_pdf)} rows written")

# ── Step 4: Dashboard summary as CSV (small, human-readable) ──────────
print("\nWriting data/analytics/dashboard_summary.csv...")
dashboard_pdf = hgs_pdf.groupby("date")["total_activity"].sum().reset_index()
dashboard_pdf.columns = ["date", "daily_total_activity"]
dashboard_pdf = dashboard_pdf.sort_values("date")
os.makedirs("data/analytics", exist_ok=True)
dashboard_pdf.to_csv("data/analytics/dashboard_summary.csv", index=False)
print(dashboard_pdf.to_string(index=False))

print("\nmilano-grid.geojson left as-is in data/reference/ (static, not touched by this job)")
print("\n✅ All writes complete.\n")

# ── Step 5: Round-trip validation (reading back WITH Spark) ────────────
# Read each partition FILE explicitly, not the parent directory -- Spark's
# native directory-listing call is broken on this machine (same root
# cause as SP1's glob crash). Re-attach 'date' manually since we're
# bypassing Spark's automatic partition discovery.
print("=== Round-Trip Validation ===")

from pyspark.sql.functions import lit as spark_lit

partition_files = sorted(glob.glob("data/processed/activity/date=*/part-0.parquet"))
print(f"Reading back {len(partition_files)} partition files explicitly...")

readback_parts = []
for f in partition_files:
    date_val = f.replace("\\", "/").split("date=")[1].split("/")[0]
    part = spark.read.parquet(f).withColumn("date", spark_lit(date_val))
    readback_parts.append(part)

readback_clean = readback_parts[0]
for part in readback_parts[1:]:
    readback_clean = readback_clean.unionByName(part)

readback_clean_count = readback_clean.count()
print(f"clean_network_df: wrote {clean_count} rows, read back {readback_clean_count}")
assert readback_clean_count == clean_count, "Round-trip row count mismatch on clean_network_df!"
print("✅ Row count matches after round-trip.")

readback_hgs = spark.read.parquet("data/analytics/hourly_grid_summary/part-0.parquet")
readback_hgs_count = readback_hgs.count()
print(f"hourly_grid_summary: wrote {hgs_count} rows, read back {readback_hgs_count}")
assert readback_hgs_count == hgs_count, "Round-trip row count mismatch on hourly_grid_summary!"
print("✅ Row count matches after round-trip.")

dupe_count = (
    readback_hgs.groupBy("grid_id", "timestamp").count()
    .filter(col("count") > 1)
    .count()
)
assert dupe_count == 0, f"GRAIN VIOLATION after round-trip: {dupe_count} duplicates found!"
print("✅ Zero duplicates on (grid_id, timestamp) confirmed AFTER round-trip.")

assert "geometry_json" not in readback_hgs.columns and "geometry" not in readback_hgs.columns
print("✅ No geometry column present in hourly_grid_summary (confirmed after read-back).")

print("\nSchema after round-trip:")
readback_hgs.printSchema()

# ── Step 6: File size comparison (CSV source vs Parquet output) ───────
print("\n=== File Size Comparison ===")

def get_dir_size_bytes(path):
    total = 0
    for dirpath, _, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            total += os.path.getsize(fp)
    return total

raw_csv_bytes = sum(os.path.getsize(f) for f in file_list)
parquet_bytes = get_dir_size_bytes("data/processed/activity")

raw_mb = raw_csv_bytes / (1024 * 1024)
parquet_mb = parquet_bytes / (1024 * 1024)
ratio = raw_csv_bytes / parquet_bytes if parquet_bytes > 0 else float("inf")

print(f"Raw CSV total size (7 files): {raw_mb:.1f} MB")
print(f"Parquet output size (data/processed/activity/): {parquet_mb:.1f} MB")
print(f"Compression ratio: {ratio:.2f}x smaller as Parquet")
print(
    "\nWHY Parquet is smaller: Parquet is a columnar, binary format with "
    "built-in compression (typically Snappy by default). Storing each "
    "column contiguously lets the compressor exploit repeated values "
    "within a column (e.g. many rows sharing the same grid_id or date) "
    "far more effectively than a row-based text format like CSV, which "
    "stores every value as literal text with no columnar locality."
)
print(
    "\nWHY Parquet suits processed/analytics layers but not the raw zone: "
    "the raw zone should preserve exactly what arrived, in the format it "
    "arrived in, for traceability and reproducibility. The processed and "
    "analytics layers are internally-generated, reused repeatedly by "
    "downstream jobs -- that's exactly where columnar compression and "
    "predicate/column pruning (both Parquet features) pay off most."
)

print(f"\n✅ SP6 complete. Partition layout verifiable at data/processed/activity/date=*/")

spark.stop()
