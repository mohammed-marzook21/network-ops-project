"""
NP1 - Profile the Telecom Activity Dataset
Phase 1, Network Operations Predictive Intelligence Project
"""

import pandas as pd

# ── Step 1: Load the file ──────────────────────────────────────────
df = pd.read_csv("data/raw/sms-call-internet-mi-2013-11-01.csv")

print("Shape:", df.shape)
print("\nColumns:", df.columns.tolist())
print("\nData types:\n", df.dtypes)
print("\nFirst 5 rows:\n", df.head())

# ── Step 2: Rename to canonical schema ─────────────────────────────
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
df = df.rename(columns=RENAME_MAP)
print("\nRenamed columns:", df.columns.tolist())

# ── Step 3: Parse timestamp and verify cadence ─────────────────────
df["timestamp"] = pd.to_datetime(df["timestamp"])

unique_ts = sorted(df["timestamp"].unique())
print("\nNumber of distinct timestamps:", len(unique_ts))
print("First:", unique_ts[0], " Last:", unique_ts[-1])

gaps = pd.Series(unique_ts).diff().dropna()
print("All gaps are 1 hour?", (gaps == pd.Timedelta(hours=1)).all())

df["date"] = df["timestamp"].dt.date
df["hour"] = df["timestamp"].dt.hour
df["day_of_week"] = df["timestamp"].dt.day_name()

# ── Step 4: Data quality checks ────────────────────────────────────
print("\nMissing grid_id:", df["grid_id"].isnull().sum())
print("Missing timestamp:", df["timestamp"].isnull().sum())

activity_cols = ["sms_in", "sms_out", "call_in", "call_out", "internet_activity"]
print("\nNull counts per activity column:")
print(df[activity_cols].isnull().sum())

print("\nExact duplicate rows:", df.duplicated().sum())

print("\nNegative values per column:")
for col in activity_cols:
    print(f"  {col}: {(df[col] < 0).sum()}")

# ── Step 5: Confirm the raw grain (grid+hour has multiple country codes) ──
example = df[(df["grid_id"] == 1) & (df["timestamp"] == "2013-11-01 00:00:00")]
print("\nExample - grid 1 at midnight, multiple country_code rows:")
print(example[["grid_id", "timestamp", "country_code"] + activity_cols])

print("\nHow many country_code rows does grid 1 have across the whole day?")
print(df[df["grid_id"] == 1]["country_code"].nunique())

# ── Step 6: Derived total activity measures ────────────────────────
df["total_sms"] = df["sms_in"].fillna(0) + df["sms_out"].fillna(0)
df["total_calls"] = df["call_in"].fillna(0) + df["call_out"].fillna(0)
df["total_activity"] = df["total_sms"] + df["total_calls"] + df["internet_activity"].fillna(0)

print("\nDerived totals:\n", df[["grid_id", "timestamp", "total_sms", "total_calls", "total_activity"]].head())

# ── Step 7: Profiling facts ─────────────────────────────────────────
print("\n--- PROFILING FACTS ---")
print("Unique grids:", df["grid_id"].nunique())
print("Time range:", df["timestamp"].min(), "to", df["timestamp"].max())
print("Unique country codes:", df["country_code"].nunique())

busiest_hour = df.groupby("hour")["total_activity"].sum().idxmax()
print("Busiest hour of day:", busiest_hour)

busiest_grid = df.groupby("grid_id")["total_activity"].sum().idxmax()
print("Busiest grid:", busiest_grid)

print("\nNull counts per column:\n", df.isnull().sum())

print("\n✅ NP1 profiling complete.")