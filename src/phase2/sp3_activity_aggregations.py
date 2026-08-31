"""
SP3 - Network Activity Aggregations
Phase 2, Network Operations Predictive Intelligence Project

Collapses country-code-level records to grid/hour grain and builds
the canonical downstream analytics tables: hourly_grid_summary,
daily_traffic_summary, and a hotspot ranking.

TRAINER NOTE (from the guide): this is the single most important
validation checkpoint in the whole program. A wrong grain here silently
inflates every later KPI, model score, API response, and dashboard
number. The zero-duplicates assertion below is not optional.
"""

import os
os.environ["JAVA_HOME"] = r"C:\Program Files\Java\jdk-17"
os.environ["HADOOP_HOME"] = r"C:\network-ops-project\tools\hadoop"
os.environ["PATH"] = os.environ["JAVA_HOME"] + r"\bin;" + os.environ["HADOOP_HOME"] + r"\bin;" + os.environ["PATH"]

import glob
from pyspark.sql import SparkSession
from pyspark.sql.types import StructType, StructField, StringType, IntegerType, DoubleType
from pyspark.sql.functions import (
    col, to_timestamp, when, lit, date_format, hour as spark_hour,
    coalesce, sum as spsum
)

spark = SparkSession.builder.appName("SP3_ActivityAggregations").getOrCreate()
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

# ── Rebuild clean_network_df (same as SP2 - kept self-contained here) ──
file_list = sorted(glob.glob("data/raw/sms-call-internet-mi-*.csv"))
D = len(file_list)
raw_df = spark.read.option("header", True).schema(raw_schema).csv(file_list)

df = raw_df
for old, new in RENAME_MAP.items():
    df = df.withColumnRenamed(old, new)
df = df.withColumn("timestamp", to_timestamp(col("timestamp")))

neg_mask = None
for c in ACTIVITY_COLS:
    cond = coalesce((col(c) < 0), lit(False))
    neg_mask = cond if neg_mask is None else (neg_mask | cond)
df = df.filter(~(col("grid_id").isNull() | col("timestamp").isNull()))
df = df.filter(~neg_mask)

for c in ACTIVITY_COLS:
    df = df.withColumn(c, when(col(c).isNull(), lit(0.0)).otherwise(col(c)))

clean_network_df = df
clean_count = clean_network_df.count()

# ── Step 1: Collapse country_code rows to one row per grid + hour ──
# This is the mandatory, non-delegable grain transition. We're summing
# the raw activity measures ACROSS country_code, which is why
# country_code disappears from the output entirely.
hourly_grid_summary = (
    clean_network_df
    .groupBy("grid_id", "timestamp")
    .agg(
        spsum("sms_in").alias("sms_in"),
        spsum("sms_out").alias("sms_out"),
        spsum("call_in").alias("call_in"),
        spsum("call_out").alias("call_out"),
        spsum("internet_activity").alias("internet_activity"),
    )
)

# ── Step 2: Derive date/hour + composite indicators ─────────────────
hourly_grid_summary = hourly_grid_summary.withColumn("date", date_format(col("timestamp"), "yyyy-MM-dd"))
hourly_grid_summary = hourly_grid_summary.withColumn("hour", spark_hour(col("timestamp")))
hourly_grid_summary = hourly_grid_summary.withColumn("total_sms", col("sms_in") + col("sms_out"))
hourly_grid_summary = hourly_grid_summary.withColumn("total_calls", col("call_in") + col("call_out"))
hourly_grid_summary = hourly_grid_summary.withColumn(
    "total_activity", col("total_sms") + col("total_calls") + col("internet_activity")
)
hourly_grid_summary = hourly_grid_summary.withColumn(
    "internet_share",
    when(col("total_activity") > 0, col("internet_activity") / col("total_activity")).otherwise(lit(0.0))
)

hgs_count = hourly_grid_summary.count()

# ── MANDATORY ASSERTION: zero duplicates on (grid_id, timestamp) ────
# This must be in the code, not just checked interactively once.
dupe_count = (
    hourly_grid_summary.groupBy("grid_id", "timestamp").count()
    .filter(col("count") > 1)
    .count()
)
if dupe_count != 0:
    spark.stop()
    raise AssertionError(
        f"GRAIN VIOLATION: {dupe_count} duplicate (grid_id, timestamp) rows found "
        f"in hourly_grid_summary. This must be fixed before any downstream lab runs, "
        f"since it would silently inflate every later KPI, model score, and dashboard number."
    )
print(f"✅ Zero duplicates confirmed on (grid_id, timestamp). Checked {hgs_count} rows.")

# ── Remaining acceptance checks ──────────────────────────────────────
print("\n=== SP3 Aggregation Report ===")
print("clean_network_df rows:", clean_count)
print("hourly_grid_summary rows:", hgs_count)
print(f"Max possible rows (D x 24 x 10000): {D * 24 * 10000}")

assert hgs_count < clean_count, "hourly_grid_summary must have fewer rows than clean_network_df"
assert hgs_count <= D * 24 * 10000, "hourly_grid_summary exceeds the max possible row count"
assert "country_code" not in hourly_grid_summary.columns, "country_code leaked into hourly_grid_summary"
print("✅ Row count is strictly less than clean_network_df, and within D x 24 x 10000.")
print("✅ country_code is absent from hourly_grid_summary.")

# ── Hand-check: grid 1, Nov 1 at midnight ────────────────────────────
print("\n=== Hand-check: grid 1, 2013-11-01 00:00:00 ===")
hourly_grid_summary.filter(
    (col("grid_id") == 1) & (col("timestamp") == "2013-11-01 00:00:00")
).show(truncate=False)

# ── daily_traffic_summary: daily activity per grid ───────────────────
daily_traffic_summary = (
    hourly_grid_summary
    .groupBy("grid_id", "date")
    .agg(spsum("total_activity").alias("daily_total_activity"))
)

# ── Top 10 high-activity grids for Nov 1 (call these "hotspots", ────
# NOT "congested" -- no capacity/utilization data exists in this project)
print("\n=== Top 10 high-activity grids (hotspots), 2013-11-01 ===")
top10 = (
    daily_traffic_summary
    .filter(col("date") == "2013-11-01")
    .orderBy(col("daily_total_activity").desc())
    .limit(10)
)
top10.show(truncate=False)

# ── Peak activity hour (across the whole dataset) ────────────────────
peak_hour_df = (
    hourly_grid_summary.groupBy("hour")
    .agg(spsum("total_activity").alias("total_activity_at_hour"))
    .orderBy(col("total_activity_at_hour").desc())
)
print("\n=== Peak activity hour (all days combined) ===")
peak_hour_df.show(5, truncate=False)

print("\n✅ SP3 complete. hourly_grid_summary is the canonical downstream analytics table.")

spark.stop()