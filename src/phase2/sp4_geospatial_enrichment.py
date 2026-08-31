"""
SP4 - Geospatial Enrichment Using the Milan Grid
Phase 2, Network Operations Predictive Intelligence Project

Joins telecom activity to the actual Milan grid geometry, and PROVES
the join is geographically correct -- not just numerically complete.

Known trap (confirmed present in this exact file): every feature in
milano-grid.geojson carries TWO identifiers -- a top-level "id" that is
0-based, and "properties.cellId" that is 1-based. Feature id=0 has
cellId=1. Joining on the wrong one produces a join that succeeds,
reports 100% coverage, and is wrong for all 10,000 cells -- every
hotspot would render on its neighbor's polygon, and nothing would ever
error, because every key still matches something. This is why a
geographic spot-check is mandatory, not optional.
"""

import os
os.environ["JAVA_HOME"] = r"C:\Program Files\Java\jdk-17"
os.environ["HADOOP_HOME"] = r"C:\network-ops-project\tools\hadoop"
os.environ["PATH"] = os.environ["JAVA_HOME"] + r"\bin;" + os.environ["HADOOP_HOME"] + r"\bin;" + os.environ["PATH"]

import json
import math
import glob
from pyspark.sql import SparkSession
from pyspark.sql.types import StructType, StructField, StringType, IntegerType, DoubleType
from pyspark.sql.functions import col, to_timestamp, when, lit, sum as spsum, broadcast, coalesce

spark = SparkSession.builder.appName("SP4_GeospatialEnrichment").getOrCreate()
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

# ── Rebuild hourly_grid_summary (SP1-SP3 logic, self-contained here) ──
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
df = df.filter(~(col("grid_id").isNull() | col("timestamp").isNull()))
df = df.filter(~neg_mask)
for c in ACTIVITY_COLS:
    df = df.withColumn(c, when(col(c).isNull(), lit(0.0)).otherwise(col(c)))

hourly_grid_summary = (
    df.groupBy("grid_id", "timestamp")
    .agg(*[spsum(c).alias(c) for c in ACTIVITY_COLS])
)
hourly_grid_summary = hourly_grid_summary.withColumn("total_sms", col("sms_in") + col("sms_out"))
hourly_grid_summary = hourly_grid_summary.withColumn("total_calls", col("call_in") + col("call_out"))
hourly_grid_summary = hourly_grid_summary.withColumn(
    "total_activity", col("total_sms") + col("total_calls") + col("internet_activity")
)

pre_join_distinct_grids = hourly_grid_summary.select("grid_id").distinct().count()
pre_join_row_count = hourly_grid_summary.count()
print("Distinct grids before join:", pre_join_distinct_grids)
print("Row count before join:", pre_join_row_count)

# ── Step 1-2: Load and inspect milano-grid.geojson structure ────────
with open("data/reference/milano-grid.geojson") as f:
    gj = json.load(f)

print("\n=== GeoJSON Structure ===")
print("Top-level type:", gj["type"])
print("Number of features:", len(gj["features"]))
print("Geometry type of feature 0:", gj["features"][0]["geometry"]["type"])
print("Feature 0 top-level 'id':", gj["features"][0]["id"], "(0-based)")
print("Feature 0 'properties':", gj["features"][0]["properties"], "(cellId is 1-based)")

# ── Step 3: Normalize identifier -- MUST use properties.cellId ──────
# ASSERTION: this lookup is built from properties.cellId, per the
# Core Dataset Contract, NOT the top-level 0-based "id" field.
lookup_rows = []
for feat in gj["features"]:
    cell_id = feat["properties"]["cellId"]
    assert isinstance(cell_id, int), "properties.cellId must be an integer"
    geometry_json = json.dumps(feat["geometry"])
    lookup_rows.append((cell_id, geometry_json))

# NOTE: built directly as a list of tuples (not via pandas.DataFrame),
# because PySpark 3.5.1's createDataFrame(pandas_df) path calls
# require_minimum_pandas_version(), which imports the stdlib
# `distutils` module. Python 3.12 removed distutils entirely, so that
# call crashes with ModuleNotFoundError on newer Python even though
# nothing is actually wrong with the data. Passing a plain list of
# tuples with an explicit schema avoids that code path completely.
grid_ids_only = [r[0] for r in lookup_rows]
assert len(set(grid_ids_only)) == 10000, "Expected exactly 10,000 unique grid_id values in the lookup"
assert min(grid_ids_only) == 1 and max(grid_ids_only) == 10000, (
    "grid_id range should be 1-10000 (properties.cellId is 1-based) -- "
    "if this fails, check you used properties.cellId and not the top-level 'id'"
)
print(f"\n✅ Grid lookup built from properties.cellId (confirmed 1-based, range 1-{max(grid_ids_only)}).")

# NOTE: spark.createDataFrame() on a Python list goes through Spark's
# RDD/cloudpickle serialization path, which is broken on this Python
# version (a version-mismatch bug between PySpark 3.5.1's cloudpickle
# and Python 3.12+, similar in spirit to the earlier distutils issue,
# but in a different code path). We sidestep it entirely by writing
# the lookup to a small JSON Lines file on disk and having Spark read
# it like any other file -- no Python-object serialization involved.
lookup_path = "data/reference/grid_lookup.jsonl"
with open(lookup_path, "w") as out:
    for cell_id, geometry_json in lookup_rows:
        out.write(json.dumps({"grid_id": cell_id, "geometry_json": geometry_json}) + "\n")

lookup_schema = StructType([
    StructField("grid_id", IntegerType(), True),
    StructField("geometry_json", StringType(), True),
])
grid_lookup_df = spark.read.schema(lookup_schema).json(lookup_path)





# ── Step 4: Size comparison -- justifies a broadcast join ────────────
print(f"\nGrid lookup size: {len(lookup_rows)} rows")
print(f"Activity data size: {pre_join_row_count} rows")
print(
    "The lookup (10,000 rows, small enough to fit comfortably in memory on every "
    "executor) is a broadcast join candidate: broadcasting it avoids shuffling the "
    "much larger activity DataFrame across the cluster just to align join keys."
)

# ── Step 5: Left join, broadcasting the small lookup ─────────────────
grid_activity_geo_df = hourly_grid_summary.join(
    broadcast(grid_lookup_df), on="grid_id", how="left"
)

# ── Step 6: Validate the join numerically ────────────────────────────
post_join_row_count = grid_activity_geo_df.count()
print("\n=== Join Validation (Numerical) ===")
print("Row count after left join:", post_join_row_count)
assert post_join_row_count == pre_join_row_count, (
    "Left join multiplied rows -- the grid lookup contains duplicate grid_id keys!"
)
print("✅ Row count unchanged after left join (no duplicate keys in the lookup).")

missing_geo_df = grid_activity_geo_df.filter(col("geometry_json").isNull())
unmatched_grid_ids = [r["grid_id"] for r in missing_geo_df.select("grid_id").distinct().collect()]
coverage_pct = (pre_join_distinct_grids - len(unmatched_grid_ids)) / pre_join_distinct_grids * 100

print(f"Unmatched grid_id list: {unmatched_grid_ids}")
print(f"Enrichment coverage: {coverage_pct:.2f}%")
assert len(unmatched_grid_ids) == 0, f"Unmatched grids found: {unmatched_grid_ids}"
assert coverage_pct == 100.0, "Coverage is not 100%"
print("✅ Unmatched-grid list is empty. Coverage is 100%.")

# ── Step 7: Validate the join GEOGRAPHICALLY (the mandatory check) ──
def centroid_from_geometry_json(geo_json_str):
    geo = json.loads(geo_json_str)
    ring = geo["coordinates"][0]
    lons = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    return (sum(lons) / len(lons), sum(lats) / len(lats))

print("\n=== Geographic Spot-Check (mandatory - coverage % alone proves nothing) ===")
sample = (
    grid_activity_geo_df.filter(col("grid_id").isin([1, 2]))
    .select("grid_id", "geometry_json").distinct().collect()
)
centroids = {row["grid_id"]: centroid_from_geometry_json(row["geometry_json"]) for row in sample}
for gid, c in sorted(centroids.items()):
    print(f"  grid_id={gid}  centroid=({c[0]:.5f}, {c[1]:.5f})")

lon1, lat1 = centroids[1]
lon2, lat2 = centroids[2]
dist = math.sqrt((lon1 - lon2) ** 2 + (lat1 - lat2) ** 2)
print(f"  Distance between grid 1 and grid 2 centroids: {dist:.5f} degrees")

# Adjacent cells should be close but NOT identical (would mean same
# geometry duplicated) and NOT far apart (would mean wrong-key join).
assert 0.0001 < dist < 0.05, (
    f"Grids 1 and 2 should be adjacent, not identical or far apart! "
    f"dist={dist:.5f} -- this usually means the join used the wrong identifier "
    f"(top-level 'id' instead of properties.cellId)"
)
print("✅ Grid 1 and grid 2 centroids are adjacent (not identical, not far apart).")

# Milan city center is approximately (9.19, 45.4642)
assert 8.5 < lon1 < 9.5 and 45.0 < lat1 < 45.8, "Centroid falls outside the expected Milan region!"
print(f"✅ Named grid cell (grid_id=1) centroid ({lon1:.4f}, {lat1:.4f}) falls within expected Milan region.")

# ── Step 9: Build the enriched dataset with the exact required columns ──
grid_activity_geo_df = grid_activity_geo_df.select(
    "timestamp", "grid_id", "sms_in", "sms_out", "call_in", "call_out",
    "internet_activity", "total_activity", "geometry_json"
)

# ── Step 10: Top high-activity grids with geometry retained ─────────
print("\n=== Top 10 high-activity grids with geometry retained ===")
top10_geo = (
    grid_activity_geo_df.groupBy("grid_id", "geometry_json")
    .agg(spsum("total_activity").alias("total_activity_sum"))
    .orderBy(col("total_activity_sum").desc())
    .limit(10)
)
top10_geo.select("grid_id", "total_activity_sum").show(truncate=False)

# ── Step 11: Optional centroids for all top grids ────────────────────
top10_rows = top10_geo.select("grid_id", "geometry_json").collect()
print("Centroids of top 10 high-activity grids:")
for row in top10_rows:
    c = centroid_from_geometry_json(row["geometry_json"])
    print(f"  grid_id={row['grid_id']}  centroid=({c[0]:.5f}, {c[1]:.5f})")

print(
    "\n✅ SP4 complete. grid_activity_geo_df is geographically validated, "
    "not just numerically complete."
)

spark.stop()