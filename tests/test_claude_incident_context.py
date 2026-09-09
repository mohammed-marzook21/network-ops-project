from copy import deepcopy

from app.services.claude_incident_context_service import (
    build_curated_incident_context,
    get_historical_evidence_summary,
    get_recent_history_summary,
)


def test_recent_history_is_aggregated():
    result = get_recent_history_summary(
        4821,
        "2013-11-07 23:00:00",
    )

    assert result["interval_count"] == 24
    assert "rows" not in result
    assert "records" not in result


def test_historical_activity_excludes_current_interval():
    result = get_historical_evidence_summary(
        4821,
        "2013-11-07 23:00:00",
    )

    assert result["activity_history"]["interval_count"] == 167


def test_missing_historical_ml_is_explicit():
    result = get_historical_evidence_summary(
        4821,
        "2013-11-07 23:00:00",
    )

    assert (
        result["anomaly_history"]["historical_evidence_available"]
        is False
    )
    assert (
        result["predictive_risk_history"][
            "historical_evidence_available"
        ]
        is False
    )


def test_curated_context_contains_pipeline_trust():
    context = build_curated_incident_context(4821)

    assert context["pipeline_status"]["healthy"] is True
    assert context["context_notes"]["raw_activity_rows_included"] is False
    assert context["context_notes"]["history_is_summarized"] is True


def test_unhealthy_pipeline_context_materially_differs():
    context = build_curated_incident_context(4821)
    unhealthy = deepcopy(context)

    unhealthy["pipeline_status"] = {
        "healthy": False,
        "rows_rejected": 12,
        "nulls_handled": 8,
        "freshness_hours": 6.0,
        "per_task_status": {
            "quality_check": "failed",
        },
    }

    assert context["pipeline_status"]["healthy"] is True
    assert unhealthy["pipeline_status"]["healthy"] is False
    assert unhealthy["pipeline_status"]["rows_rejected"] > 0
    assert unhealthy["pipeline_status"]["nulls_handled"] > 0
    assert unhealthy["pipeline_status"]["freshness_hours"] > 0
    assert (
        unhealthy["pipeline_status"]["per_task_status"]["quality_check"]
        == "failed"
    )
