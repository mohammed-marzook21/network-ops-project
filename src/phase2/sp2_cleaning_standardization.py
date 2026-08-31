"""
SP2 - Cleaning & Standardization
Phase 2, Network Operations Predictive Intelligence Project

Produces a trusted distributed DataFrame (clean_network_df) and validates
it is semantically equivalent to the NP1/NP2 pandas rules on a shared day.
"""

import os
os.environ["JAVA_HOME"] = r"C:\Program Files\Java\jdk-17"
os.environ["HADOOP_HOME"] = r"C:\network-ops-project\tools\hadoop"
os.environ["PATH"] = os.environ["JAVA_HOME"] + r"\bin;" + os.environ["HADOOP_HOME"] + r"\bin;" + os.environ["PATH"]

import glob
import pandas as pd
from pyspark.sql import SparkSession
from pyspark.sql.types import StructType, StructField, StringType, IntegerType, DoubleType
from pyspark.sql.functions import (
    col, to_timestamp, when, lit, date_format, hour as spark_hour, coalesce, sum as spsum
)

spark = SparkSession.builder.appName("SP2_CleaningStandardization").getOrCreate()
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

# ── Step 1: Load all files (Python glob, not Spark's, per SP1 fix) ────
file_list = sorted(glob.glob("data/raw/sms-call-internet-mi-*.csv"))
raw_df = spark.read.option("header", True).schema(raw_schema).csv(file_list)

# ── Step 2: Rename to canonical schema ─────────────────────────────
df = raw_df
for old, new in RENAME_MAP.items():
    df = df.withColumnRenamed(old, new)

# ── Step 3: Cast timestamp, verify cadence still holds ─────────────
df = df.withColumn("timestamp", to_timestamp(col("timestamp")))
input_count = df.count()

distinct_hours = df.select("timestamp").distinct().count()
print(f"Distinct timestamps across all files: {distinct_hours} (expect {len(file_list)} x 24 = {len(file_list)*24})")
assert distinct_hours == len(file_list) * 24, "Hourly cadence broken across files!"

# ── Step 4: Quarantine bad rows ─────────────────────────────────────
bad_id_df = df.filter(col("grid_id").isNull() | col("timestamp").isNull())
rejected_ids = bad_id_df.count()
df_clean = df.filter(~(col("grid_id").isNull() | col("timestamp").isNull()))

# IMPORTANT: coalesce nulls to False before combining conditions.
# Without this, `col(c) < 0` on a NULL value returns NULL (not False) in
# Spark SQL's three-valued logic, and `~neg_mask` on that NULL is also
# NULL -- which `filter()` silently treats as "exclude the row". Since
# most rows have at least one null activity value, this bug would have
# silently discarded ~87% of all rows without raising any error.
neg_mask = None
for c in ACTIVITY_COLS:
    cond = coalesce((col(c) < 0), lit(False))
    neg_mask = cond if neg_mask is None else (neg_mask | cond)

rejected_neg = df_clean.filter(neg_mask).count()
df_clean = df_clean.filter(~neg_mask)

# ── Step 5: Profile blanks, then apply curated-layer null-to-zero rule ──
nulls_handled = 0
for c in ACTIVITY_COLS:
    nulls_handled += df_clean.filter(col(c).isNull()).count()

for c in ACTIVITY_COLS:
    df_clean = df_clean.withColumn(c, when(col(c).isNull(), lit(0.0)).otherwise(col(c)))

# ── Step 6: Derive date, hour, day_of_week ──────────────────────────
df_clean = df_clean.withColumn("date", date_format(col("timestamp"), "yyyy-MM-dd"))
df_clean = df_clean.withColumn("hour", spark_hour(col("timestamp")))
df_clean = df_clean.withColumn("day_of_week", date_format(col("timestamp"), "EEEE"))

# ── Step 7: Derived totals (originals retained, not dropped) ───────
# total_activity is a project-defined composite indicator (SMS + calls +
# internet proportional activity, NOT a literal unit) -- not a
# standard telecom metric, so it must always be labeled as such.
df_clean = df_clean.withColumn("total_sms", col("sms_in") + col("sms_out"))
df_clean = df_clean.withColumn("total_calls", col("call_in") + col("call_out"))
df_clean = df_clean.withColumn(
    "total_activity", col("total_sms") + col("total_calls") + col("internet_activity")
)

output_count = df_clean.count()

# ── Report (rejected-row count and null-handled count kept separate) ──
print("\n=== SP2 Cleaning Report ===")
print("Input rows:", input_count)
print("Rejected - missing grid_id/timestamp:", rejected_ids)
print("Rejected - negative activity value:", rejected_neg)
print("Null activity values handled (set to 0):", nulls_handled)
print("Output rows (clean_network_df):", output_count)

assert output_count == input_count - rejected_ids - rejected_neg, "Row accounting mismatch!"
print("✅ Row accounting checks out (input - rejected = output).")

clean_network_df = df_clean  # this is the lab's required output name

# ── Step 8: REQUIRED comparison test - Spark vs pandas on Nov 1 ────
print("\n=== Pandas vs Spark Comparison Test (Nov 1, 2013) ===")

spark_nov1 = clean_network_df.filter(col("date") == "2013-11-01")
spark_rows = spark_nov1.count()
spark_total = spark_nov1.agg(spsum("total_activity")).collect()[0][0]

pdf = pd.read_csv("data/raw/sms-call-internet-mi-2013-11-01.csv")
pdf = pdf.rename(columns=RENAME_MAP)
for c in ACTIVITY_COLS:
    pdf[c] = pdf[c].fillna(0)
pdf["total_sms"] = pdf["sms_in"] + pdf["sms_out"]
pdf["total_calls"] = pdf["call_in"] + pdf["call_out"]
pdf["total_activity"] = pdf["total_sms"] + pdf["total_calls"] + pdf["internet_activity"]

pandas_rows = len(pdf)
pandas_total = pdf["total_activity"].sum()

print("Spark rows:", spark_rows, " Pandas rows:", pandas_rows)
print("Spark total_activity sum:", spark_total)
print("Pandas total_activity sum:", pandas_total)
print("Difference:", abs(spark_total - pandas_total))

assert spark_rows == pandas_rows, "Row count mismatch between Spark and pandas!"
assert abs(spark_total - pandas_total) < 0.01, "total_activity mismatch between Spark and pandas!"
print("\n✅ Spark and pandas implementations are semantically equivalent for Nov 1.")

spark.stop()