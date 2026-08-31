"""
SP1 - Distributed Ingestion
Phase 2, Network Operations Predictive Intelligence Project

Loads all daily CSV files as one distributed Spark DataFrame,
using a manual schema (not inferSchema) and full traceability.
"""
import os
os.environ["JAVA_HOME"] = r"C:\Program Files\Java\jdk-17"
os.environ["HADOOP_HOME"] = r"C:\network-ops-project\tools\hadoop"
os.environ["PATH"] = os.environ["JAVA_HOME"] + r"\bin;" + os.environ["HADOOP_HOME"] + r"\bin;" + os.environ["PATH"]

# ── everything below this is unchanged ──
from pyspark.sql import SparkSession
from pyspark.sql.types import StructType, StructField, StringType, IntegerType, DoubleType
from pyspark.sql.functions import input_file_name, to_timestamp
# ...rest of the script stays exactly as before

# from pyspark.sql import SparkSession
# from pyspark.sql.types import StructType, StructField, StringType, IntegerType, DoubleType
# from pyspark.sql.functions import input_file_name, to_timestamp

# ── Step 1: Create a SparkSession ─────────────────────────────────
spark = SparkSession.builder.appName("SP1_DistributedIngestion").getOrCreate()
spark.sparkContext.setLogLevel("ERROR")  # quiet down Spark's noisy INFO logs

# ── Step 2: Define a manual schema (NOT inferSchema) ──────────────
# Why manual instead of inferSchema? inferSchema forces Spark to make
# an extra full pass over every file just to guess types, before the
# real pass that actually processes the data. On multi-file, multi-GB
# input that doubles I/O for no benefit, since we already know the
# schema from the Core Dataset Contract.
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

# ── Step 3: Read all daily files with the required glob pattern ──
# CRITICAL: use "-mi-" in the glob, never a looser pattern.
# A looser glob like "sms-call-internet-*.csv" would also match files
# from a different city (e.g. Trentino) whose CellIDs numerically
# overlap with Milan's — the read would succeed silently, roughly
# double your row count, and quietly halve geographic enrichment
# coverage later in SP4, with no error anywhere.
import glob

file_list = sorted(glob.glob("data/raw/sms-call-internet-mi-*.csv"))
print("Files found by Python's glob:", file_list)

raw_network_df = (
    spark.read
    .option("header", True)
    .schema(raw_schema)
    .csv(file_list)  # pass an explicit list instead of a wildcard string
    .withColumn("input_file_name", input_file_name())
)



# ── Step 4: Count rows, files, grids, country codes, hourly intervals ──
total_rows = raw_network_df.count()
file_count = raw_network_df.select("input_file_name").distinct().count()
unique_grids = raw_network_df.select("CellID").distinct().count()
country_code_categories = raw_network_df.select("countrycode").distinct().count()

ts_col = to_timestamp(raw_network_df["datetime"])
distinct_hourly_intervals = raw_network_df.select(ts_col.alias("ts")).distinct().count()

print("=== SP1 Ingestion Report ===")
print("Total rows:", total_rows)
print("File count:", file_count)
print("Unique grids:", unique_grids)
print("Country code categories:", country_code_categories)
print("Distinct hourly intervals:", distinct_hourly_intervals)

# ── Step 6: Inspect partition count ───────────────────────────────
num_partitions = raw_network_df.rdd.getNumPartitions()
print("Number of partitions:", num_partitions)
print(
    "Note: partition count affects how much parallel work Spark can do. "
    "Too few partitions relative to CPU cores under-utilizes the cluster; "
    "too many creates scheduling overhead. File layout (how many files, "
    "how large each is) directly drives this."
)

# ── Acceptance checks ──────────────────────────────────────────────
D = file_count  # number of files loaded
assert distinct_hourly_intervals == D * 24, (
    f"Expected {D * 24} distinct timestamps (D x 24), got {distinct_hourly_intervals}"
)

grid_bounds = raw_network_df.selectExpr("min(CellID) as min_id", "max(CellID) as max_id").collect()[0]
assert grid_bounds["min_id"] >= 1 and grid_bounds["max_id"] <= 10000, (
    f"grid_id out of range: {grid_bounds['min_id']} - {grid_bounds['max_id']}"
)

null_filename_count = raw_network_df.filter(raw_network_df.input_file_name.isNull()).count()
assert null_filename_count == 0, f"{null_filename_count} rows missing input_file_name"

print("\n✅ All SP1 acceptance criteria passed.")
print(f"   - Distinct timestamps ({distinct_hourly_intervals}) = D x 24 ({D} x 24)")
print(f"   - grid_id range: {grid_bounds['min_id']}-{grid_bounds['max_id']} (within 1-10000)")
print(f"   - Every row has a populated input_file_name")

spark.stop()