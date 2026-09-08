import pytest

from app.services import claude_insight_service


def test_validate_response_accepts_required_sections():
    response = """
SEVERITY
NORMAL

EVIDENCE
Grid ID: 4821

INTERPRETATION
No anomaly is established.

NEXT CHECKS
Review additional evidence.
"""

    claude_insight_service._validate_response(response)


def test_validate_response_rejects_missing_section():
    response = """
SEVERITY
NORMAL

EVIDENCE
Grid ID: 4821

INTERPRETATION
No anomaly is established.
"""

    with pytest.raises(RuntimeError):
        claude_insight_service._validate_response(response)
    


def test_generate_network_insight_rejects_empty_evidence():
    with pytest.raises(ValueError):
        claude_insight_service.generate_network_insight({})


def test_generate_network_insight_rejects_non_dict_evidence():
    with pytest.raises(ValueError):
        claude_insight_service.generate_network_insight(None)