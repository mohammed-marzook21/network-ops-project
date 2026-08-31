"""
SP5 - Performance & Execution Behaviour: APPLIED DECISIONS
Phase 2, Network Operations Predictive Intelligence Project

This script applies ONLY the decisions actually justified by evidence
gathered in sp5_performance_diagnostics.py. See
docs/phase2/sp5_performance_observations.md for the full reasoning,
including the suggestion that was deliberately rejected.
"""

import os
os.environ["JAVA_HOME"] = r"C:\Program Files\Java\jdk-17"
os.environ["HADOOP_HOME"] = r"C:\network-ops-project\tools\hadoop"
os.environ["PATH"] = os.environ["JAVA_HOME"] + r"\bin;" + os.environ["HADOOP_HOME"] + r"\bin;" + os.environ["PATH"]

import glob
from pyspark.sql import SparkSession
from pyspark.sql.types import StructType, StructField, StringType, IntegerType, DoubleType
from pyspark.sql.functions import col, to_timestamp, when, lit, sum as spsum, coalesce

spark = SparkSession.builder.appName("SP5_AppliedDecisions").getOrCreate()
spark.sparkContext.setLogLevel("ERROR")

# ── DECISION: spark.sql.shuffle.partitions is intentionally NOT changed. ──
# Diagnostic 1 showed Exchange using hashpartitioning(grid_id, timestamp, 200)
# against only 15 source partitions -- a common "looks wrong" signal on a
# small local dataset. REJECTED as a change because Spark 3.5's Adaptive
# Query Execution (enabled by default) can already coalesce small
# post-shuffle partitions at runtime without any manual config. Overriding
# this manually adds a hardcoded number that would need to be revisited if
# the dataset grows (e.g. more days added later), for a benefit that isn't
# proven without first measuring whether AQE is already handling it.
print(f"AQE enabled: {spark.conf.get('spark.sql.adaptive.enabled')}")
print(f"AQE coalesce partitions: {spark.conf.get('spark.sql.adaptive.coalescePartitions.enabled')}")
print("shuffle.partitions left at default (200) -- see rejection reasoning above.\n")

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

clean_network_df = df

hourly_grid_summary = (
    clean_network_df.groupBy("grid_id", "timestamp")
    .agg(*[spsum(c).alias(c) for c in ACTIVITY_COLS])
)
hourly_grid_summary = hourly_grid_summary.withColumn("total_sms", col("sms_in") + col("sms_out"))
hourly_grid_summary = hourly_grid_summary.withColumn("total_calls", col("call_in") + col("call_out"))
hourly_grid_summary = hourly_grid_summary.withColumn(
    "total_activity", col("total_sms") + col("total_calls") + col("internet_activity")
)

# ── DECISION: cache hourly_grid_summary. ──────────────────────────────
# Diagnostics 3 and 4 showed a repeated .count() costs 5.35s uncached vs
# 1.49s cached (a 3.6x speedup on reuse). This DataFrame is reused 7+
# times downstream (SP4's two direct counts, plus five more actions on
# grid_activity_geo_df, which is built on top of it) -- without caching,
# Spark would re-read and re-aggregate all 7 raw CSVs on every single one
# of those calls. ACCEPTED because the reuse count justifies the one-time
# cost of populating the cache.
hourly_grid_summary = hourly_grid_summary.cache()
hourly_grid_summary.count()  # materialize the cache now, not on first incidental use

print(f"✅ hourly_grid_summary cached. Row count: {hourly_grid_summary.count()}")
print("   (this second .count() should be fast -- reading from cache, not recomputing)")

spark.stop()