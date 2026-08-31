"""
NP3 - Rule-Based Network Activity Alert Generator
Phase 1, Network Operations Predictive Intelligence Project

Builds a within-day baseline per grid and flags HIGH_ACTIVITY,
ACTIVITY_SPIKE, and ACTIVITY_DROP against it.
"""

import os
import numpy as np
import pandas as pd

# ── Step 1: Load NP2's output ────────────────────────────────────
grid_hour_df = pd.read_csv(
    "outputs/phase1/np2/hourly_grid_summary.csv",
    parse_dates=["timestamp"]
)
print("Loaded grid/hour data:", grid_hour_df.shape)

# ── Step 2: Build the within-day baseline ────────────────────────
# For each grid, median total_activity across the day's 24 hours,
# EXCLUDING the hour currently being evaluated.
#
# Trap: do NOT group by (grid_id, hour) - with only 1 day of data
# each bucket would have exactly 1 observation (itself), so every
# deviation would be zero and all rules would fire nothing.

def add_within_day_baseline(df):
    df = df.sort_values(["grid_id", "timestamp"]).reset_index(drop=True)
    baselines = np.empty(len(df))

    for grid_id, idx in df.groupby("grid_id").indices.items():
        vals = df.loc[idx, "total_activity"].values
        for i in range(len(vals)):
            others = np.delete(vals, i)          # every hour except this one
            baselines[idx[i]] = np.median(others)

    df["baseline_activity"] = baselines
    return df

grid_hour_df = add_within_day_baseline(grid_hour_df)
print("Baseline computed.")

# Hand-check: baseline should change depending on which hour is excluded
sample = grid_hour_df[grid_hour_df["grid_id"] == 1][["timestamp", "total_activity", "baseline_activity"]]
print("\nSample check (grid 1):\n", sample.to_string())

# ── Step 3: Choose an activity floor ─────────────────────────────
# Grids with tiny daily totals produce meaningless ratios.
daily_totals_per_grid = grid_hour_df.groupby("grid_id")["total_activity"].sum()
ACTIVITY_FLOOR = daily_totals_per_grid.quantile(0.10)
print(f"\nActivity floor (10th percentile of daily totals): {ACTIVITY_FLOOR:.2f}")

# ── Step 4: Define and apply the three rules ─────────────────────
HIGH_ACTIVITY_RATIO = 1.5   # current hour is 50%+ above baseline
SPIKE_RATIO = 1.5           # current hour is 50%+ above the PRECEDING hour
DROP_RATIO = 0.5            # current hour is 50%+ below baseline

def classify_alerts(df, floor, daily_totals):
    df = df.sort_values(["grid_id", "timestamp"]).reset_index(drop=True)
    df["prev_activity"] = df.groupby("grid_id")["total_activity"].shift(1)

    low_grids = set(daily_totals[daily_totals < floor].index)
    df_f = df[~df["grid_id"].isin(low_grids)].copy()
    df_f = df_f[df_f["baseline_activity"] > 0]

    high = df_f[df_f["total_activity"] > df_f["baseline_activity"] * HIGH_ACTIVITY_RATIO].copy()
    high["alert_type"] = "HIGH_ACTIVITY"
    high["reason"] = high.apply(
        lambda r: f"Current activity {r.total_activity:.2f} is {r.total_activity/r.baseline_activity:.1f}x the within-day baseline {r.baseline_activity:.2f}",
        axis=1)

    spike = df_f[
        df_f["prev_activity"].notnull() & (df_f["prev_activity"] > 0) &
        (df_f["total_activity"] > df_f["prev_activity"] * SPIKE_RATIO)
    ].copy()
    spike["alert_type"] = "ACTIVITY_SPIKE"
    spike["reason"] = spike.apply(
        lambda r: f"Current activity {r.total_activity:.2f} is {r.total_activity/r.prev_activity:.1f}x the previous hour {r.prev_activity:.2f}",
        axis=1)

    drop = df_f[df_f["total_activity"] < df_f["baseline_activity"] * DROP_RATIO].copy()
    drop["alert_type"] = "ACTIVITY_DROP"
    drop["reason"] = drop.apply(
        lambda r: f"Current activity {r.total_activity:.2f} is only {r.total_activity/r.baseline_activity:.1f}x the within-day baseline {r.baseline_activity:.2f}",
        axis=1)

    alerts = pd.concat([high, spike, drop], ignore_index=True)
    alerts = alerts.rename(columns={"total_activity": "current_activity"})
    return alerts[["grid_id", "timestamp", "alert_type", "current_activity", "baseline_activity", "reason"]]

alerts_df = classify_alerts(grid_hour_df, ACTIVITY_FLOOR, daily_totals_per_grid)

print(f"\nTotal alerts: {len(alerts_df)}")
print(alerts_df["alert_type"].value_counts())

pct_alerting = len(alerts_df) / len(grid_hour_df) * 100
print(f"\n% of grid/hours with at least one alert: {pct_alerting:.2f}%")

print("\nTop 10 grids by alert count:")
print(alerts_df["grid_id"].value_counts().head(10))

# ── Step 5: Export ────────────────────────────────────────────────
output_dir = "outputs/phase1/np3"
os.makedirs(output_dir, exist_ok=True)
alerts_df.to_csv(f"{output_dir}/network_alerts.csv", index=False)
print(f"\nExported to {output_dir}/network_alerts.csv")

# ── Step 6: Verify grid_id values are all valid (1-10000) ─────────
assert alerts_df["grid_id"].min() >= 1 and alerts_df["grid_id"].max() <= 10000
print("\n✅ All alerted grid_id values are within 1-10000.")

# ── Step 7: Hand-check one alert against the raw hourly numbers ──
sample_alert = alerts_df.iloc[0]
gid = sample_alert["grid_id"]
print(f"\nHand-check for grid {gid} (alert type: {sample_alert['alert_type']}):")
print(grid_hour_df[grid_hour_df["grid_id"] == gid][["timestamp", "total_activity", "baseline_activity"]].to_string())

print("\n✅ NP3 alert generation complete.")