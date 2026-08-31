"""
Network Operations Predictive Intelligence - Reusable Spark ETL Job

Runs the full SP1-SP6 pipeline (read -> clean -> aggregate -> enrich ->
write) as a single, configurable, fail-fast job. See
docs/phase2/sp7_job_contract.md for the documented input/output contract.
"""

import os
os.environ["JAVA_HOME"] = r"C:\Program Files\Java\jdk-17"
os.environ["HADOOP_HOME"] = r"C:\network-ops-project\tools\hadoop"
os.environ["PATH"] = os.environ["JAVA_HOME"] + r"\bin;" + os.environ["HADOOP_HOME"] + r"\bin;" + os.environ["PATH"]

import argparse
import glob
import json
import logging
import shutil
import sys
from datetime import datetime

from pyspark.sql import SparkSession
from pyspark.sql.types import StructType, StructField, StringType, IntegerType, DoubleType
from pyspark.sql.functions import (
    col, to_timestamp, when, lit, date_format, hour as spark_hour,
    coalesce, sum as spsum, broadcast
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("telecom_pipeline")

RENAME_MAP = {
    "datetime": "timestamp", "CellID": "grid_id", "countrycode": "country_code",
    "smsin": "sms_in", "smsout": "sms_out", "callin": "call_in",
    "callout": "call_out", "internet": "internet_activity",
}
ACTIVITY_COLS = ["sms_in", "sms_out", "call_in", "call_out", "internet_activity"]

RAW_SCHEMA = StructType([
    StructField("datetime", StringType(), True),
    StructField("CellID", IntegerType(), True),
    StructField("countrycode", IntegerType(), True),
    StructField("smsin", DoubleType(), True),
    StructField("smsout", DoubleType(), True),
    StructField("callin", DoubleType(), True),
    StructField("callout", DoubleType(), True),
    StructField("internet", DoubleType(), True),
])


def read_raw(spark, input_dir):
    """
    Read all daily telecom CSVs from input_dir using Python's own glob
    (not Spark's, which crashes with a native Windows IO error on this
    machine -- see SP1) and a manual schema (not inferSchema, to avoid a
    redundant full pass over every file). Fails fast with a clear
    message and non-zero exit if no matching files are found.
    """
    file_list = sorted(glob.glob(os.path.join(input_dir, "sms-call-internet-mi-*.csv")))
    if not file_list:
        logger.error(f"FATAL: no daily activity files found in '{input_dir}' "
                      f"(expected pattern: sms-call-internet-mi-*.csv)")
        sys.exit(1)

    logger.info(f"Found {len(file_list)} input file(s): {[os.path.basename(f) for f in file_list]}")
    raw_df = spark.read.option("header", True).schema(RAW_SCHEMA).csv(file_list)
    input_rows = raw_df.count()
    logger.info(f"input_rows={input_rows}")
    return raw_df, input_rows, file_list


def clean(raw_df):
    """
    Rename to canonical schema, cast timestamp, reject bad-identifier and
    negative-activity rows, fill null activity with 0. See SP2.

    Uses coalesce(cond, lit(False)) when building the negative-value mask
    -- without it, Spark SQL's three-valued logic treats NULL comparisons
    as NULL (not False), and NOT NULL is still NULL, which .filter()
    silently treats as "exclude the row". This previously discarded ~87%
    of rows with no error, no warning, no failed assertion.
    """
    df = raw_df
    for old, new in RENAME_MAP.items():
        df = df.withColumnRenamed(old, new)
    df = df.withColumn("timestamp", to_timestamp(col("timestamp")))

    input_rows = df.count()

    bad_id_mask = col("grid_id").isNull() | col("timestamp").isNull()
    rejected_ids = df.filter(bad_id_mask).count()
    df = df.filter(~bad_id_mask)

    neg_mask = None
    for c in ACTIVITY_COLS:
        cond = coalesce((col(c) < 0), lit(False))
        neg_mask = cond if neg_mask is None else (neg_mask | cond)
    rejected_neg = df.filter(neg_mask).count()
    df = df.filter(~neg_mask)

    nulls_handled = sum(df.filter(col(c).isNull()).count() for c in ACTIVITY_COLS)
    for c in ACTIVITY_COLS:
        df = df.withColumn(c, when(col(c).isNull(), lit(0.0)).otherwise(col(c)))

    df = df.withColumn("date", date_format(col("timestamp"), "yyyy-MM-dd"))

    rejected_rows = rejected_ids + rejected_neg
    output_rows = df.count()
    assert output_rows == input_rows - rejected_rows, "Row accounting mismatch in clean()!"

    logger.info(f"rejected_rows={rejected_rows}")
    logger.info(f"nulls_handled={nulls_handled}")

    return df, rejected_rows, nulls_handled


def aggregate(clean_df):
    """
    Collapse country_code rows to one row per grid_id + timestamp.
    Country-code aggregation happens HERE, before any grid/hour
    operational analytics -- enrich() below only ever receives
    already-aggregated data, never raw country-code-level rows.
    Includes the mandatory zero-duplicates assertion, which HALTS the
    job (not just warns) if the grain is ever violated -- a grain error
    here would silently inflate every downstream KPI. See SP3.
    """
    hourly_grid_summary = (
        clean_df.groupBy("grid_id", "timestamp")
        .agg(*[spsum(c).alias(c) for c in ACTIVITY_COLS])
    )
    hourly_grid_summary = hourly_grid_summary.withColumn("date", date_format(col("timestamp"), "yyyy-MM-dd"))
    hourly_grid_summary = hourly_grid_summary.withColumn("hour", spark_hour(col("timestamp")))
    hourly_grid_summary = hourly_grid_summary.withColumn("total_sms", col("sms_in") + col("sms_out"))
    hourly_grid_summary = hourly_grid_summary.withColumn("total_calls", col("call_in") + col("call_out"))
    hourly_grid_summary = hourly_grid_summary.withColumn(
        "total_activity", col("total_sms") + col("total_calls") + col("internet_activity")
    )

    dupe_count = (
        hourly_grid_summary.groupBy("grid_id", "timestamp").count()
        .filter(col("count") > 1)
        .count()
    )
    if dupe_count != 0:
        logger.error(f"FATAL: grain violation - {dupe_count} duplicate (grid_id, timestamp) rows")
        sys.exit(1)

    # Cached because reused downstream: enrich() and write_outputs() both
    # consume this same DataFrame. See SP5 for the caching-decision
    # evidence (reuse count justifies the one-time cache cost here).
    hourly_grid_summary = hourly_grid_summary.cache()
    output_rows = hourly_grid_summary.count()
    logger.info(f"aggregate_output_rows={output_rows}")

    return hourly_grid_summary


def enrich(hourly_grid_summary, reference_dir, spark):
    """
    Join grid geometry from the static milano-grid.geojson reference
    file, for map-rendering consumers. Uses properties.cellId (1-based),
    NOT the top-level 'id' field (0-based) -- joining on the wrong one
    would succeed silently, report 100% coverage, and place every grid
    on its neighbor's polygon. See SP4.

    Geometry is enriched here as a distinct output, but is NOT written
    into hourly_grid_summary itself in write_outputs() -- geometry is a
    static property of a grid cell, not a per-hour fact, so duplicating
    it into ~1.7M analytics rows would be wasteful and wrong.
    """
    geojson_path = os.path.join(reference_dir, "milano-grid.geojson")
    with open(geojson_path) as f:
        gj = json.load(f)

    lookup_rows = [(feat["properties"]["cellId"], json.dumps(feat["geometry"])) for feat in gj["features"]]

    # Written to a file and read back via spark.read (rather than
    # spark.createDataFrame on a Python list) to avoid a PySpark
    # 3.5.1 / Python 3.12+ cloudpickle serialization bug on this
    # environment. See docs/environment_known_issues.md, Issue #4.
    lookup_path = os.path.join(reference_dir, "grid_lookup_temp.jsonl")
    with open(lookup_path, "w") as out:
        for cell_id, geometry_json in lookup_rows:
            out.write(json.dumps({"grid_id": cell_id, "geometry_json": geometry_json}) + "\n")

    lookup_schema = StructType([
        StructField("grid_id", IntegerType(), True),
        StructField("geometry_json", StringType(), True),
    ])
    # NOTE: path passed as a single-item LIST, not a bare string.
    # spark.read.json(single_path) internally checks whether that path
    # is a file or a directory before reading it -- that check routes
    # through the same broken native Windows/Hadoop IO layer behind
    # SP1's glob crash and SP6's directory-read crash, and silently
    # resolved to zero rows here (with no error raised), which caused
    # ALL 10,000 grids to fail geometry matching on a full pipeline run.
    # Passing an explicit list of known files (the same pattern already
    # proven reliable for CSV reads throughout this project) sidesteps
    # that check entirely.
    grid_lookup_df = spark.read.schema(lookup_schema).json([lookup_path])

    enriched_df = hourly_grid_summary.join(broadcast(grid_lookup_df), on="grid_id", how="left")

    missing = enriched_df.filter(col("geometry_json").isNull()).select("grid_id").distinct().count()
    if missing > 0:
        logger.warning(f"{missing} grid_id(s) have no matching geometry")

    logger.info("enrich_complete=true")
    return enriched_df


def write_outputs(clean_df, hourly_grid_summary, output_dir):
    """
    Write processed activity (partitioned by date, Parquet) and
    analytics outputs (hourly_grid_summary Parquet, dashboard CSV).

    Uses pandas+pyarrow instead of Spark's native writer -- Spark's
    write-side file commit fails on this Windows machine with a
    winutils.exe DLL error that could not be resolved (see
    docs/environment_known_issues.md, Issue #5). Timestamps are
    downcast to microsecond precision before writing because pyarrow
    defaults to nanosecond precision, which Spark's Parquet reader
    rejects outright (Issue #6).
    """
    processed_dir = os.path.join(output_dir, "processed", "activity")
    analytics_dir = os.path.join(output_dir, "analytics")
    shutil.rmtree(processed_dir, ignore_errors=True)
    shutil.rmtree(analytics_dir, ignore_errors=True)

    dates = sorted([r["date"] for r in clean_df.select("date").distinct().collect()])
    for d in dates:
        part_pdf = clean_df.filter(col("date") == d).toPandas()
        part_pdf["timestamp"] = part_pdf["timestamp"].astype("datetime64[us]")
        out_dir = os.path.join(processed_dir, f"date={d}")
        os.makedirs(out_dir, exist_ok=True)
        part_pdf.to_parquet(os.path.join(out_dir, "part-0.parquet"), engine="pyarrow", index=False)

    hgs_out_dir = os.path.join(analytics_dir, "hourly_grid_summary")
    os.makedirs(hgs_out_dir, exist_ok=True)
    # NOTE: select only the non-geometry columns here -- geometry lives
    # in the enrich() output, not in this fact-shaped analytics table.
    hgs_no_geo = hourly_grid_summary.select(
        "grid_id", "timestamp", "sms_in", "sms_out", "call_in", "call_out",
        "internet_activity", "date", "hour", "total_sms", "total_calls", "total_activity"
    )
    hgs_pdf = hgs_no_geo.toPandas()
    hgs_pdf["timestamp"] = hgs_pdf["timestamp"].astype("datetime64[us]")
    hgs_pdf.to_parquet(os.path.join(hgs_out_dir, "part-0.parquet"), engine="pyarrow", index=False)

    dashboard_pdf = hgs_pdf.groupby("date")["total_activity"].sum().reset_index()
    dashboard_pdf.columns = ["date", "daily_total_activity"]
    dashboard_pdf = dashboard_pdf.sort_values("date")
    os.makedirs(analytics_dir, exist_ok=True)
    dashboard_pdf.to_csv(os.path.join(analytics_dir, "dashboard_summary.csv"), index=False)

    output_rows = len(hgs_pdf)
    logger.info(f"output_rows={output_rows}")
    return output_rows


def main():
    parser = argparse.ArgumentParser(description="Network Ops telecom pipeline (SP1-SP6 consolidated)")
    parser.add_argument("--input-dir", required=True, help="Directory containing raw daily CSV files")
    parser.add_argument("--output-dir", required=True, help="Directory to write processed/analytics outputs")
    parser.add_argument("--reference-dir", required=True, help="Directory containing milano-grid.geojson")
    args = parser.parse_args()

    start_time = datetime.now()
    logger.info(f"job_start={start_time.isoformat()}")
    logger.info(f"input_dir={args.input_dir}")
    logger.info(f"output_dir={args.output_dir}")
    logger.info(f"reference_dir={args.reference_dir}")

    status = "FAILED"
    try:
        spark = (
            SparkSession.builder
            .appName("TelecomPipeline")
            .config("spark.driver.memory", "6g")
            .getOrCreate()
        )
        spark.sparkContext.setLogLevel("ERROR")

        raw_df, input_rows, file_list = read_raw(spark, args.input_dir)
        clean_df, rejected_rows, nulls_handled = clean(raw_df)
        hourly_grid_summary = aggregate(clean_df)
        enriched_df = enrich(hourly_grid_summary, args.reference_dir, spark)
        output_rows = write_outputs(clean_df, hourly_grid_summary, args.output_dir)

        status = "SUCCESS"
    except SystemExit:
        raise
    except Exception as e:
        logger.error(f"FATAL: unhandled exception: {e}")
        status = "FAILED"
    finally:
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        logger.info(f"job_end={end_time.isoformat()}")
        logger.info(f"duration_seconds={duration:.1f}")
        logger.info(f"status={status}")

    if status != "SUCCESS":
        sys.exit(1)


if __name__ == "__main__":
    main()