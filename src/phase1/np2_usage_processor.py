"""
NP2 - Build the UsageProcessor Class
Phase 1, Network Operations Predictive Intelligence Project

Turns the one-off NP1 exploration into a reusable, testable class.
"""

import logging
import os
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


class UsageProcessor:
    """
    Loads, cleans, aggregates, and summarizes one day of Milan telecom
    activity data. Each step is its own method so it can be tested
    independently and ported to PySpark later without changing the logic.
    """

    RENAME_MAP = {
        "datetime": "timestamp",
        "CellID": "grid_id",
        "countrycode": "country_code",
        "smsin": "sms_in",
        "smsout": "sms_out",
        "callin": "call_in",
        "callout": "call_out",
        "internet": "internet_activity",
    }

    ACTIVITY_COLS = ["sms_in", "sms_out", "call_in", "call_out", "internet_activity"]
    REQUIRED_RAW_COLS = list(RENAME_MAP.keys())

    def __init__(self, source):
        """
        source: a file path (str) OR an already-loaded pandas DataFrame.
        """
        self.source = source
        self.raw_df = None        # untouched, exactly as loaded
        self.clean_df = None      # canonical names, null policy applied
        self.grid_time_df = None  # one row per grid + hour (country_code aggregated away)
        self.kpi_df = None        # daily and grid-level KPI summaries

        self._stats = {"input_rows": 0, "rows_rejected": 0, "nulls_handled": 0, "output_rows": 0}

    # ── 1. load_data ─────────────────────────────────────────────
    def load_data(self):
        if isinstance(self.source, pd.DataFrame):
            self.raw_df = self.source.copy()
        else:
            self.raw_df = pd.read_csv(self.source)

        missing_cols = [c for c in self.REQUIRED_RAW_COLS if c not in self.raw_df.columns]
        if missing_cols:
            raise ValueError(f"Missing required raw columns: {missing_cols}")

        self._stats["input_rows"] = len(self.raw_df)
        logger.info(f"Loaded {self._stats['input_rows']} raw rows")
        return self

    # ── 2. clean_data ────────────────────────────────────────────
    def clean_data(self):
        df = self.raw_df.rename(columns=self.RENAME_MAP).copy()

        # Reject rows with missing identifiers - these can't be placed anywhere
        bad_id_mask = df["grid_id"].isnull() | df["timestamp"].isnull()
        rejected_ids = bad_id_mask.sum()
        df = df[~bad_id_mask]

        # Reject rows with negative activity values (defensive check)
        neg_mask = (df[self.ACTIVITY_COLS] < 0).any(axis=1)
        rejected_neg = neg_mask.sum()
        df = df[~neg_mask]

        # Curated-layer null policy: a blank activity value means
        # "no activity of that type happened" -> treat as 0.
        # This is applied ONLY here, never to self.raw_df.
        nulls_before = df[self.ACTIVITY_COLS].isnull().sum().sum()
        df[self.ACTIVITY_COLS] = df[self.ACTIVITY_COLS].fillna(0)

        df["timestamp"] = pd.to_datetime(df["timestamp"])

        self._stats["rows_rejected"] = int(rejected_ids + rejected_neg)
        self._stats["nulls_handled"] = int(nulls_before)

        logger.info(
            f"Cleaned data: rejected {self._stats['rows_rejected']} rows, "
            f"filled {self._stats['nulls_handled']} null activity values"
        )

        self.clean_df = df
        return self

    # ── 3. derive_time_features ──────────────────────────────────
    def derive_time_features(self):
        df = self.clean_df
        df["date"] = df["timestamp"].dt.date
        df["hour"] = df["timestamp"].dt.hour
        df["day_of_week"] = df["timestamp"].dt.day_name()
        self.clean_df = df
        logger.info("Derived date, hour, day_of_week")
        return self

    # ── 4. aggregate_to_grid_time (the most important step) ──────
    def aggregate_to_grid_time(self):
        df = self.clean_df

        grouped = (
            df.groupby(["grid_id", "timestamp", "date", "hour", "day_of_week"])[self.ACTIVITY_COLS]
            .sum()
            .reset_index()
        )

        dupes = grouped.duplicated(subset=["grid_id", "timestamp"]).sum()
        if dupes > 0:
            raise RuntimeError(f"Aggregation failed - {dupes} duplicate (grid_id, timestamp) rows found")

        self._stats["output_rows"] = len(grouped)
        logger.info(
            f"Aggregated to grid/hour grain: {len(grouped)} rows "
            f"(input to this step had {len(df)} rows)"
        )

        self.grid_time_df = grouped
        return self

    # ── 5. derive_activity_features ──────────────────────────────
    def derive_activity_features(self):
        df = self.grid_time_df
        df["total_sms"] = df["sms_in"] + df["sms_out"]
        df["total_calls"] = df["call_in"] + df["call_out"]
        df["total_activity"] = df["total_sms"] + df["total_calls"] + df["internet_activity"]
        self.grid_time_df = df
        logger.info("Derived total_sms, total_calls, total_activity")
        return self

    # ── 6. compute_kpis ───────────────────────────────────────────
    def compute_kpis(self):
        df = self.grid_time_df

        daily_summary = (
            df.groupby("date")["total_activity"]
            .agg(total_activity="sum", avg_activity="mean", peak_activity="max")
            .reset_index()
        )

        grid_summary = (
            df.groupby("grid_id")["total_activity"]
            .agg(total_activity="sum", avg_activity="mean", peak_activity="max")
            .reset_index()
            .sort_values("total_activity", ascending=False)
        )

        self.kpi_df = {"daily_summary": daily_summary, "grid_summary": grid_summary}
        logger.info("Computed daily and grid-level KPI summaries")
        return self

    # ── 7. export_summary ─────────────────────────────────────────
    def export_summary(self, output_dir="outputs/phase1/np2"):
        os.makedirs(output_dir, exist_ok=True)

        self.grid_time_df.to_csv(f"{output_dir}/hourly_grid_summary.csv", index=False)
        self.kpi_df["daily_summary"].to_csv(f"{output_dir}/daily_summary.csv", index=False)
        self.kpi_df["grid_summary"].to_csv(f"{output_dir}/grid_summary.csv", index=False)

        logger.info(f"Exported outputs to {output_dir}/")
        logger.info(f"Final stats: {self._stats}")
        return self._stats