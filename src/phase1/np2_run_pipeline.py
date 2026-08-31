"""
NP2 - Run the UsageProcessor pipeline and validate it.
Phase 1, Network Operations Predictive Intelligence Project
"""

from np2_usage_processor import UsageProcessor

# ── Run the full pipeline ────────────────────────────────────────
processor = (
    UsageProcessor("data/raw/sms-call-internet-mi-2013-11-01.csv")
    .load_data()
    .clean_data()
    .derive_time_features()
    .aggregate_to_grid_time()
    .derive_activity_features()
    .compute_kpis()
)
stats = processor.export_summary()
print("\nFinal stats:", stats)

# ── Simple validations, one per method ───────────────────────────
def test_load_data():
    p = UsageProcessor("data/raw/sms-call-internet-mi-2013-11-01.csv").load_data()
    assert p.raw_df is not None
    assert len(p.raw_df) > 0

def test_clean_data_no_negatives():
    p = UsageProcessor("data/raw/sms-call-internet-mi-2013-11-01.csv").load_data().clean_data()
    assert (p.clean_df[UsageProcessor.ACTIVITY_COLS] < 0).sum().sum() == 0

def test_aggregate_no_duplicates():
    p = (UsageProcessor("data/raw/sms-call-internet-mi-2013-11-01.csv")
         .load_data().clean_data().derive_time_features().aggregate_to_grid_time())
    assert p.grid_time_df.duplicated(subset=["grid_id", "timestamp"]).sum() == 0

def test_aggregate_fewer_rows():
    p = (UsageProcessor("data/raw/sms-call-internet-mi-2013-11-01.csv")
         .load_data().clean_data().derive_time_features().aggregate_to_grid_time())
    assert len(p.grid_time_df) < len(p.clean_df)

def test_country_code_dropped():
    p = (UsageProcessor("data/raw/sms-call-internet-mi-2013-11-01.csv")
         .load_data().clean_data().derive_time_features().aggregate_to_grid_time())
    assert "country_code" not in p.grid_time_df.columns

test_load_data()
test_clean_data_no_negatives()
test_aggregate_no_duplicates()
test_aggregate_fewer_rows()
test_country_code_dropped()
print("\n✅ All NP2 validations passed.")