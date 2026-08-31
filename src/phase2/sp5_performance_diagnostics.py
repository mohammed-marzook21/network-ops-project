"""
SP5 - Performance & Execution Behaviour: DIAGNOSTIC TOOLKIT
Phase 2, Network Operations Predictive Intelligence Project

This script does NOT apply any optimizations. It only gathers evidence
(explain() plans, timing numbers, partition counts) so you can decide
what to change yourself and document your reasoning.
"""
import os
os.environ["JAVA_HOME"] = r"C:\Program Files\Java\jdk-17"
os.environ["HADOOP_HOME"] = r"C:\network-ops-project\tools\hadoop"
os.environ["PATH"] = os.environ["JAVA_HOME"] + r"\bin;" + os.environ["HADOOP_HOME"] + r"\bin;" + os.environ["PATH"]

import glob
import time
from pyspark.sql import SparkSession
from pyspark.sql.types import StructType, StructField, StringType, IntegerType, DoubleType
from pyspark.sql.functions import col, to_timestamp, when, lit, sum as spsum, coalesce

spark = SparkSession.builder.appName("SP5_Diagnostics").getOrCreate()
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
hourly_grid_summary = hourly_grid_summary.withColumn(
    "total_activity",
    col("sms_in") + col("sms_out") + col("call_in") + col("call_out") + col("internet_activity")
)

# ============ DIAGNOSTIC 1: explain() on the hotspot aggregation ============
print("=" * 70)
print("DIAGNOSTIC 1: Physical plan for hourly_grid_summary aggregation")
print("=" * 70)
hourly_grid_summary.explain(mode="formatted")
print(
    "\nWHAT TO LOOK FOR: find the 'Exchange' step. It shows "
    "'hashpartitioning(grid_id, timestamp, N)' for some N. That N is how "
    "many partitions Spark shuffled your data into for the aggregation. "
    "Compare it to how many partitions your SOURCE data has (Diagnostic 2)."
)

# ============ DIAGNOSTIC 2: partition counts ============
print("\n" + "=" * 70)
print("DIAGNOSTIC 2: Partition counts")
print("=" * 70)
print("clean_network_df partitions:", clean_network_df.rdd.getNumPartitions())
print("hourly_grid_summary partitions:", hourly_grid_summary.rdd.getNumPartitions())
print(
    "\nWHAT TO LOOK FOR: is the aggregation's partition count close to your "
    "source partition count, or much larger/smaller? A local machine with a "
    "handful of CPU cores doesn't benefit from hundreds of tiny partitions - "
    "each partition has scheduling overhead, and too many small partitions "
    "on too few cores just means more overhead for no more parallelism."
)

# ============ DIAGNOSTIC 3: timing WITHOUT caching, same action twice ============
print("\n" + "=" * 70)
print("DIAGNOSTIC 3: Repeated action timing WITHOUT caching")
print("=" * 70)
t0 = time.time()
count1 = hourly_grid_summary.count()
t1 = time.time()
print(f"First .count() (no cache): {count1} rows in {t1 - t0:.2f}s")

t0 = time.time()
count2 = hourly_grid_summary.count()
t1 = time.time()
print(f"Second .count() (no cache): {count2} rows in {t1 - t0:.2f}s")
print(
    "\nWHAT TO LOOK FOR: are the two timings roughly the same, even though "
    "nothing changed between them? If so, that's evidence Spark is re-reading "
    "and re-computing the ENTIRE lineage (all 7 CSVs -> clean -> aggregate) "
    "from scratch every single time, because Spark is lazy and doesn't "
    "remember results unless you tell it to."
)

# ============ DIAGNOSTIC 4: same timing test, this time cached ============
print("\n" + "=" * 70)
print("DIAGNOSTIC 4: Repeated action timing WITH caching")
print("=" * 70)
cached_df = hourly_grid_summary.cache()

t0 = time.time()
count3 = cached_df.count()  # this triggers the actual caching
t1 = time.time()
print(f"First .count() (populates cache): {count3} rows in {t1 - t0:.2f}s")

t0 = time.time()
count4 = cached_df.count()
t1 = time.time()
print(f"Second .count() (reads from cache): {count4} rows in {t1 - t0:.2f}s")
print(
    "\nWHAT TO LOOK FOR: compare this second number to Diagnostic 3's second "
    "number. Caching should make the SECOND access much faster, since Spark "
    "isn't recomputing the lineage. The FIRST cached access is often similar "
    "or even slightly slower than uncached, because it still has to compute "
    "the result AND store it - the benefit only shows up on reuse."
)

# ============ DIAGNOSTIC 5: column pruning comparison ============
print("\n" + "=" * 70)
print("DIAGNOSTIC 5: Column pruning - plan comparison")
print("=" * 70)
print("--- Plan WITHOUT column selection (all columns) ---")
clean_network_df.groupBy("grid_id").agg(spsum("total_sms").alias("x") if "total_sms" in clean_network_df.columns else spsum("sms_in").alias("x")).explain()

narrow_df = clean_network_df.select("grid_id", "sms_in")
print("\n--- Plan WITH column selection (only grid_id, sms_in) BEFORE aggregating ---")
narrow_df.groupBy("grid_id").agg(spsum("sms_in").alias("x")).explain()
print(
    "\nWHAT TO LOOK FOR: check the 'ReadSchema' or 'Output' line in the Scan "
    "csv step of each plan. Does selecting fewer columns before the "
    "aggregation change which columns Spark actually reads from disk?"
)

spark.stop()