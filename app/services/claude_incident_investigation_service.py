import json
import os

from anthropic import Anthropic
from dotenv import load_dotenv


load_dotenv()

REQUIRED_SECTIONS = (
    "CURRENT EVIDENCE",
    "HISTORICAL EVIDENCE",
    "UNCERTAINTY",
)

SYSTEM_PROMPT = """
You are an AI-assisted Network Operations incident investigation assistant.

You must reason only from the evidence package supplied to you.

Return exactly these three sections:

CURRENT EVIDENCE
HISTORICAL EVIDENCE
UNCERTAINTY

Rules:

1. CURRENT EVIDENCE
   - State only what is supported by the current incident evidence.
   - Preserve supplied numeric values.
   - Do not invent or estimate numbers.
   - Treat telecom values as activity measures, not message counts,
     call counts, bytes, throughput, utilization, capacity, subscribers,
     or customer counts.

2. HISTORICAL EVIDENCE
   - Compare the current situation only with supplied historical evidence.
   - State whether similar or higher activity is supported by the supplied
     historical summaries.
   - Do not claim historical anomaly or predictive-risk behavior when
     historical_evidence_available is false.
   - A zero historical scored-interval count with evidence unavailable
     means historical ML evidence is missing, not that no prior event occurred.

3. UNCERTAINTY
   - Explicitly describe important evidence gaps.
   - Use pipeline status as evidence of data trustworthiness.
   - If rows_rejected is greater than zero, treat it as material.
   - If nulls_handled is greater than zero, treat it as material.
   - If freshness_hours indicates stale analytics, treat it as material.
   - If pipeline healthy is false, explain how that limits confidence in
     the supplied evidence.
   - If historical anomaly or risk evidence is unavailable, say so.

4. Never claim congestion, capacity exhaustion, outage, service degradation,
   hardware failure, or a specific root cause unless the evidence explicitly
   establishes it.

5. Current activity, anomaly signals, alerts and risk scores are investigation
   signals only. They do not prove congestion or operational failure.

6. Do not infer causes merely to make the investigation more detailed.

7. Do not restate raw rows. Summarize the evidence relevant to the question.

8. Keep pipeline run_timestamp and analytics as_of distinct.
   A pipeline execution timestamp must not be treated as the timestamp of
   the historical network activity.
9. Do not assign qualitative labels to numeric features unless that label
   is explicitly supplied.
   - Do not call activity_growth slight, large, improving, declining, or
     similar merely from its numeric sign or magnitude.
   - Do not call variability low, moderate, high, elevated, or abnormal.
   - Do not call internet_share low, high, dominant, substantial, or infer
     applications, services, or customer behaviour.

10. Treat peak_ratio only as a supplied feature named "peak_ratio".
    Do not state what its numerator, denominator, comparison period, or
    operational meaning is unless explicitly supplied.

11. Treat risk_score only as a supplied model score.
    Do not describe it as a probability, likelihood, confidence, certainty,
    percentage chance, or similarity to model training examples.
    Use risk_level only for the supplied qualitative classification.

12. Do not compare anomaly_score with a threshold unless an explicit
    anomaly threshold is supplied in the evidence.
    Use is_anomaly and anomaly_direction exactly as supplied.

13. Do not describe historical activity intervals as anomaly-scored,
    risk-scored, or ML-scored intervals.
    Activity history and persisted ML-score history are separate evidence
    sources.

14. Do not make statistical-quality judgments from baseline_sample_count
    alone. You may report the sample count as a limitation in available
    historical depth, but do not claim that it is reliable, unreliable,
    sufficient, or insufficient unless an explicit rule is supplied.

15. Simple comparisons directly supported by supplied numbers are allowed,
    such as current activity being below a supplied historical average or
    lying between a supplied minimum and maximum. Do not infer an
    operational cause from those comparisons.
Do not include any sections other than the three required sections.
""".strip()


def _get_client() -> Anthropic:
    api_key = os.getenv("ANTHROPIC_API_KEY")

    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not configured."
        )

    return Anthropic(api_key=api_key)


def _get_model() -> str:
    model = os.getenv("ANTHROPIC_MODEL")

    if not model:
        raise RuntimeError(
            "ANTHROPIC_MODEL is not configured."
        )

    return model


def _validate_response(text: str) -> None:
    missing = [
        section
        for section in REQUIRED_SECTIONS
        if section not in text
    ]

    if missing:
        raise RuntimeError(
            "Claude response is missing required C3 sections: "
            + ", ".join(missing)
        )


def investigate_incident(
    evidence: dict,
    question: str,
) -> str:
    """
    Run the C3 incident investigation using the supplied context package.
    """
    if not isinstance(evidence, dict) or not evidence:
        raise ValueError("evidence must be a non-empty dictionary")

    if not question or not question.strip():
        raise ValueError("question must not be empty")

    client = _get_client()
    model = _get_model()

    evidence_json = json.dumps(
        evidence,
        indent=2,
        default=str,
    )

    response = client.messages.create(
        model=model,
        max_tokens=1200,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    f"{question.strip()}\n\n"
                    "Use only the following supplied evidence package.\n\n"
                    f"{evidence_json}"
                ),
            }
        ],
    )

    if not response.content:
        raise RuntimeError("Claude returned an empty response.")

    text = response.content[0].text.strip()

    _validate_response(text)

    return text