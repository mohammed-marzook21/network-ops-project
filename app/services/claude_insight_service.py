import json
import os

from anthropic import Anthropic
from dotenv import load_dotenv


load_dotenv()

REQUIRED_SECTIONS = (
    "SEVERITY",
    "EVIDENCE",
    "INTERPRETATION",
    "NEXT CHECKS",
)

SYSTEM_PROMPT = """
You are an AI-assisted Network Operations reasoning assistant.

You receive CURATED network evidence only.

Your job is to explain the supplied evidence without inventing facts.

Mandatory rules:

1. Return exactly these four sections:
   SEVERITY
   EVIDENCE
   INTERPRETATION
   NEXT CHECKS

2. SEVERITY must be exactly one of:
   NORMAL
   ATTENTION
   HIGH

3. EVIDENCE:
   - Use only values explicitly supplied in the evidence.
   - Include relevant numeric values where available.
   - Never invent or estimate a number.
   - These telecom activity values are proportional activity measures.
   - Do not describe them as message counts, call counts, MB, throughput,
     utilization, capacity, or customer counts.

4. INTERPRETATION:
   - Clearly distinguish inference from observed evidence.
   - Use language such as "may", "might", or "could".
   - Never claim that high activity proves congestion.
   - Never claim an outage, hardware fault, capacity exhaustion, or
     service degradation unless evidence explicitly supports it.

5. NEXT CHECKS:
   - Recommend practical checks a human NOC engineer could perform.
   - Do not state that those checks have already been performed.

6. If important evidence is missing, explicitly say that the evidence is
   insufficient and identify what additional evidence would help.

7. In particular, if anomaly_score or anomaly_direction is missing,
   explicitly state that anomaly evidence is insufficient.
8. Do not infer the semantic meaning of a feature beyond its supplied name
   and value.
   - Do not convert activity_growth into a percentage unless the evidence
     explicitly provides a percentage interpretation.
   - Do not explain peak_ratio as a ratio against a trough, off-peak period,
     capacity, or any other reference unless that reference is explicitly
     supplied.
   - Do not label variability as low, moderate, high, elevated, or abnormal
     unless the evidence explicitly provides that classification.
   - Do not interpret internet_share as specific applications, services,
     streaming, downloads, browsing, or customer behaviour.

9. Do not infer time-of-day behaviour from the timestamp.
   A timestamp such as 23:00 does not prove that activity should normally
   be lower at that hour.

10. Do not create hypothetical causes merely to make the explanation more
    detailed. If the supplied evidence does not identify a cause, state that
    the cause cannot be determined from the available evidence.

11. When referring to a numeric feature, preserve the supplied value and
    avoid deriving new numeric values unless the calculation is explicitly
    supplied in the evidence.

12. Rule alerts and anomaly signals indicate unusual activity only.
    They do not prove congestion, capacity exhaustion, service degradation,
    outage, hardware failure, or a specific traffic cause.
13. Never compare anomaly_score to a threshold unless the threshold value is explicitly present in the evidence.
    Do not say "near threshold", "approaching threshold", "close to anomalous",
    or similar unless the threshold is supplied.

14. Treat activity_growth as a standalone feature value.
    Do not state or imply that it is calculated relative to baseline_total_activity,
    the anomaly baseline, the rule-alert historical average, or any other reference
    unless that relationship is explicitly supplied in the evidence.

15. Do not infer semantics for peak_ratio, variability, or internet_share beyond
    their supplied names and numeric values.
    Do not describe internet_share as a large/substantial proportion,
    traffic composition, application traffic, downloads, streaming, browsing,
    or customer behaviour unless such meaning is explicitly supplied.

16. Do not call a statistical deviation "statistically significant" unless
    statistical significance, a p-value, confidence level, or an explicit
    significance rule is supplied in the evidence.

17. A direction value such as "high" or "low" is only the supplied direction label.
    Do not convert it into an operational severity unless another supplied field
    explicitly provides severity.
18. Do not infer the numeric scale, bounds, calibration, probability meaning,
    or closeness to a maximum/minimum for risk_score unless that scale is
    explicitly supplied in the evidence.
    Use the supplied risk_level for qualitative classification.
    For example, do not say "near maximum", "extreme upper bound",
    "99.9% probability", or similar unless explicitly supported.
Do not include any sections other than the four required sections.
""".strip()


def _get_client() -> Anthropic:
    api_key = os.getenv("ANTHROPIC_API_KEY")

    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not configured. "
            "Set it in the local environment before using Claude insights."
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
            "Claude response is missing required C1 sections: "
            + ", ".join(missing)
        )


def generate_network_insight(evidence: dict) -> str:
    """
    Generate an evidence-grounded operational explanation for one grid.

    `evidence` must contain curated API/ML evidence only.
    Raw telecom rows must never be supplied to this function.
    """
    if not isinstance(evidence, dict):
        raise ValueError("evidence must be a dictionary")

    if not evidence:
        raise ValueError("evidence must not be empty")

    client = _get_client()
    model = _get_model()

    evidence_json = json.dumps(
        evidence,
        indent=2,
        default=str,
    )

    response = client.messages.create(
        model=model,
        max_tokens=900,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    "Generate an operational network insight using only "
                    "the following curated evidence.\n\n"
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
