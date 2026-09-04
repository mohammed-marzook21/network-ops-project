"""
DE8 - Missing daily file check
Phase 3, Network Operations Predictive Intelligence Project

Compares which dates SHOULD have arrived (based on a start date and
"today") against what's actually present in landing/ or raw/. Warns
(does not fail the pipeline) if any expected date is absent -- missing
data can be backfilled later, so hard-failing an entire run over one
missing day would waste processing on days that DID arrive.
"""

import glob
import os
import re
from datetime import date, timedelta


def check_expected_files(landing_dir, raw_dir, start_date, end_date):
    """
    Returns a dict: {"missing_dates": [...], "present_dates": [...]}
    start_date/end_date are date objects, inclusive range.
    """
    expected_dates = []
    d = start_date
    while d <= end_date:
        expected_dates.append(d.isoformat())
        d += timedelta(days=1)

    present_dates = set()
    for directory in (landing_dir, raw_dir):
        for filepath in glob.glob(os.path.join(directory, "sms-call-internet-mi-*.csv")):
            match = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(filepath))
            if match:
                present_dates.add(match.group(1))

    missing_dates = [d for d in expected_dates if d not in present_dates]

    result = {
        "missing_dates": missing_dates,
        "present_dates": sorted(present_dates & set(expected_dates)),
    }
    return result