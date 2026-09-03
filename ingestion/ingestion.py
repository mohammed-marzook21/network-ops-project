"""
DE2 - Landing-to-Raw Ingestion Flow
Phase 3, Network Operations Predictive Intelligence Project

Reusable ingestion functions. These live OUTSIDE any Airflow DAG so they
can be tested independently and reused elsewhere (SP7, DE8), per the
trainer note in the guide: "Validation logic stays in reusable Python
functions rather than being buried in DAG code."

IMPORTANT: milano-grid.geojson is static reference data and NEVER passes
through this module. Nothing here touches data/reference/.
"""

import csv
import glob
import json
import os
from datetime import datetime

# ── Contract constants ───────────────────────────────────────────────
FILENAME_PATTERN = "sms-call-internet-mi-*.csv"
# The "-mi-" is mandatory. A looser glob (e.g. "sms-call-internet-*.csv")
# would also match files from a different city whose CellIDs numerically
# collide with Milan's, silently corrupting downstream processing.

REQUIRED_COLUMNS = [
    "datetime", "CellID", "countrycode",
    "smsin", "smsout", "callin", "callout", "internet",
]

MIN_ROW_COUNT = 1  # a file with 0 data rows is not usable


def detect_files(landing_dir):
    """
    Find candidate daily activity files in the landing zone.
    Uses the strict -mi- pattern; does NOT match milano-grid.geojson
    or anything else that isn't a daily activity file.
    """
    pattern = os.path.join(landing_dir, FILENAME_PATTERN)
    return sorted(glob.glob(pattern))


def validate_schema(filepath):
    """
    Check that the file has exactly the required columns.
    Returns (is_valid: bool, reason: str | None).
    """
    try:
        with open(filepath, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader, None)
    except Exception as e:
        return False, f"Could not read file: {e}"

    if header is None:
        return False, "File is empty (no header row)"

    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        return False, f"Missing required column(s): {', '.join(missing)}"

    extra = [c for c in header if c not in REQUIRED_COLUMNS]
    if extra:
        return False, f"Unexpected extra column(s): {', '.join(extra)}"

    return True, None


def validate_minimum_quality(filepath):
    """
    Check basic data quality: every timestamp parses, no negative
    activity values, and at least MIN_ROW_COUNT data rows exist.

    NOTE: this is a stricter, whole-file gate than SP2's per-row
    handling. SP2 quietly drops individual bad rows during Spark
    cleaning; this ingestion gate instead REJECTS THE ENTIRE FILE if
    any row fails, since a file with a structural problem shouldn't
    be allowed into 'raw' at all -- Spark should only ever see files
    that already passed a basic sanity check.

    Returns (is_valid: bool, reason: str | None, row_count: int).
    """
    activity_cols = ["smsin", "smsout", "callin", "callout", "internet"]
    row_count = 0

    try:
        with open(filepath, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for line_num, row in enumerate(reader, start=2):  # line 1 = header
                row_count += 1

                # Check timestamp parses
                try:
                    datetime.strptime(row["datetime"], "%Y-%m-%d %H:%M:%S")
                except (ValueError, KeyError):
                    return False, f"Malformed timestamp at line {line_num}: '{row.get('datetime')}'", row_count

                # Check no negative activity values (blank/missing is fine)
                for col in activity_cols:
                    val = row.get(col, "")
                    if val == "":
                        continue
                    try:
                        num = float(val)
                    except ValueError:
                        return False, f"Non-numeric value in '{col}' at line {line_num}: '{val}'", row_count
                    if num < 0:
                        return False, f"Negative value in '{col}' at line {line_num}: {num}", row_count

    except Exception as e:
        return False, f"Could not read file during quality check: {e}", row_count

    if row_count < MIN_ROW_COUNT:
        return False, f"File has {row_count} data rows, minimum is {MIN_ROW_COUNT}", row_count

    return True, None, row_count


def route_file(filepath, is_valid, raw_dir, rejected_dir):
    """
    Move the file to data/raw/ (if valid) or data/rejected/ (if not).
    The file's CONTENT is never modified -- only its location changes.
    Returns the new path.
    """
    os.makedirs(raw_dir, exist_ok=True)
    os.makedirs(rejected_dir, exist_ok=True)

    filename = os.path.basename(filepath)
    dest_dir = raw_dir if is_valid else rejected_dir
    dest_path = os.path.join(dest_dir, filename)

    os.rename(filepath, dest_path)
    return dest_path


def write_audit_record(log_path, filename, status, row_count, reason, processed_at):
    """
    Append one audit record (as a JSON line) to the ingestion log.
    Every file seen gets exactly one record, regardless of outcome.
    """
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    record = {
        "filename": filename,
        "status": status,  # "accepted" | "rejected" | "skipped_duplicate"
        "row_count": row_count,
        "reason": reason,
        "processed_at": processed_at,
    }
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    return record


def already_processed(filename, log_path):
    """
    Check the audit log to see if this exact filename was successfully
    processed in a previous run.

    Rejected files are NOT treated as duplicates so that a corrected
    version can be reprocessed.
    """
    if not os.path.exists(log_path):
        return False

    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            if (
                record.get("filename") == filename
                and record.get("status") == "accepted"
            ):
                return True

    return False
    """
    Check the audit log to see if this exact filename has already been
    successfully processed (accepted or rejected) in a previous run.
    Used to make re-running idempotent: re-processing an already-seen
    file should not silently duplicate it in raw/ or rejected/.
    """
    if not os.path.exists(log_path):
        return False
    with open(log_path, encoding="utf-8") as f:
        for line in f:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("filename") == filename and record.get("status") in ("accepted", "rejected"):
                return True
    return False


def process_file(filepath, raw_dir, rejected_dir, log_path):
    """
    Run the full pipeline for ONE file: idempotency check -> schema
    validation -> quality validation -> routing -> audit logging.
    This is the single function an Airflow task calls per file --
    all the actual logic lives here, not in the DAG.
    """
    filename = os.path.basename(filepath)
    processed_at = datetime.now().isoformat()

    if already_processed(filename, log_path):
        write_audit_record(log_path, filename, "skipped_duplicate", None,
                            "File was already processed in a previous run", processed_at)
        return {"filename": filename, "status": "skipped_duplicate"}

    schema_ok, schema_reason = validate_schema(filepath)
    if not schema_ok:
        dest = route_file(filepath, is_valid=False, raw_dir=raw_dir, rejected_dir=rejected_dir)
        write_audit_record(log_path, filename, "rejected", None, schema_reason, processed_at)
        return {"filename": filename, "status": "rejected", "reason": schema_reason, "path": dest}

    quality_ok, quality_reason, row_count = validate_minimum_quality(filepath)
    if not quality_ok:
        dest = route_file(filepath, is_valid=False, raw_dir=raw_dir, rejected_dir=rejected_dir)
        write_audit_record(log_path, filename, "rejected", row_count, quality_reason, processed_at)
        return {"filename": filename, "status": "rejected", "reason": quality_reason, "path": dest}

    dest = route_file(filepath, is_valid=True, raw_dir=raw_dir, rejected_dir=rejected_dir)
    write_audit_record(log_path, filename, "accepted", row_count, None, processed_at)
    return {"filename": filename, "status": "accepted", "row_count": row_count, "path": dest}