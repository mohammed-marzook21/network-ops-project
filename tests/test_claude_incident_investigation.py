from app.services.claude_incident_investigation_service import (
    REQUIRED_SECTIONS,
    SYSTEM_PROMPT,
    _validate_response,
)


def test_c3_requires_exact_three_sections():
    assert REQUIRED_SECTIONS == (
        "CURRENT EVIDENCE",
        "HISTORICAL EVIDENCE",
        "UNCERTAINTY",
    )


def test_valid_c3_response_passes_validation():
    text = """
CURRENT EVIDENCE
Current evidence here.

HISTORICAL EVIDENCE
Historical evidence here.

UNCERTAINTY
Uncertainty here.
"""

    _validate_response(text)


def test_missing_c3_section_fails_validation():
    text = """
CURRENT EVIDENCE
Current evidence here.

HISTORICAL EVIDENCE
Historical evidence here.
"""

    try:
        _validate_response(text)
        assert False, "Expected RuntimeError"
    except RuntimeError as exc:
        assert "UNCERTAINTY" in str(exc)


def test_prompt_requires_pipeline_quality_in_uncertainty():
    assert "rows_rejected" in SYSTEM_PROMPT
    assert "nulls_handled" in SYSTEM_PROMPT
    assert "freshness_hours" in SYSTEM_PROMPT
    assert "pipeline healthy is false" in SYSTEM_PROMPT


def test_prompt_protects_historical_ml_evidence_gap():
    assert "historical_evidence_available is false" in SYSTEM_PROMPT
    assert "missing, not that no prior event occurred" in SYSTEM_PROMPT


def test_prompt_prohibits_congestion_claims():
    assert "Never claim congestion" in SYSTEM_PROMPT


def test_prompt_protects_risk_score_semantics():
    assert "Treat risk_score only as a supplied model score" in SYSTEM_PROMPT
    assert "probability" in SYSTEM_PROMPT


def test_prompt_protects_anomaly_threshold():
    assert "Do not compare anomaly_score with a threshold" in SYSTEM_PROMPT


def test_prompt_separates_pipeline_and_analytics_time():
    assert "Keep pipeline run_timestamp and analytics as_of distinct" in SYSTEM_PROMPT