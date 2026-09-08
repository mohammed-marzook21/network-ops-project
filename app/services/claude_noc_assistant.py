"""
Phase 7 C2 — Tool-Using Claude NOC Assistant.

Claude may reason about network operations only through the trusted
C2 tools exposed by this project.

Pipeline status is forced as the first evidence source before Claude
is allowed to investigate operational data.
"""

import json
import os

from anthropic import Anthropic
from dotenv import load_dotenv

from app.services.claude_noc_tools import CLAUDE_NOC_TOOLS
from app.services.claude_noc_tool_executor import execute_noc_tool


load_dotenv()

MAX_TOOL_ROUNDS = 8


SYSTEM_PROMPT = """
You are an AI-assisted Network Operations Center (NOC) investigation assistant.

You operate above trusted analytics, ML outputs, and operational-support
services. You are not a source of network measurements.

GROUNDING RULES

1. Use tools for factual claims about this network.
2. Do not invent measurements, timestamps, grid properties, pipeline state,
   anomaly results, feature values, locations, alerts, or risk values.
3. The pipeline-status result is provided first. Consider its health before
   interpreting network evidence.
4. Treat analytics as historical dataset evidence. Do not confuse the
   pipeline run timestamp with the analytics as_of timestamp.
5. Activity values are proportional activity measures. They are not message
   counts, call counts, bytes, throughput, utilization, capacity, subscriber
   counts, or customer counts.
6. A hotspot means high observed activity according to the hotspot service.
   It does not prove congestion.
7. An anomaly means unusual activity relative to its defined baseline.
   It does not prove congestion, outage, fault, service degradation, or
   capacity exhaustion.
8. Predictive ML risk represents investigation priority for next-hour
   unusually high activity. It is not proof of congestion, outage, fault,
   or capacity exhaustion.
9. Never claim congestion, capacity exhaustion, outage, hardware failure,
   service degradation, or root cause unless a trusted tool explicitly
   provides evidence supporting that claim.
10. If evidence is missing or a tool fails, state the evidence gap. Never
    estimate the missing value.
11. Distinguish observation from inference. Use language such as may, might,
    or could for interpretations.
12. Recommend human NOC checks when appropriate. Do not claim those checks
    have already been performed.
13. Do not infer feature semantics beyond what the trusted result states.
14. Do not invent thresholds or compare values against thresholds that were
    not returned by a trusted tool.
15. Keep the final response concise and operationally useful.
16. Preserve the meaning and terminology of tool fields. For example,
    rows_rejected means rejected rows and nulls_handled means null values
    handled; do not rename or merge distinct metrics into a new factual claim.
17. Do not claim that a pipeline is current relative to today's real-world
    date merely because freshness_hours is zero. freshness_hours refers to
    freshness within the project's analytics context. Keep pipeline execution
    time and historical analytics as_of time distinct.
18. Feature names are labels, not formulas. Do not derive a percentage,
    threshold, category, or mathematical interpretation from peak_ratio,
    variability, activity_growth, or internet_share unless that meaning is
    explicitly supplied by a trusted tool.

19. Never claim that two grids are adjacent, nearby, co-located, clustered,
    or share infrastructure unless trusted location evidence was retrieved
    for every grid involved and supports that comparison.

20. baseline_sample_count is only the number of observations used by the
    stored anomaly baseline. Do not translate it into statistical confidence,
    reliability, significance, or data sparsity unless a trusted tool
    explicitly supplies that interpretation.

21. Do not invent explanations for observed activity patterns. In particular,
    do not infer events, applications, traffic types, customer behaviour,
    infrastructure load, recently activated grids, or shared infrastructure
    from activity measures alone.

22. internet_share may be reported only as the supplied feature value or
    percentage representation of that supplied share. Do not infer what
    applications, services, traffic types, or customer behaviours produced it.

23. A recommendation may request additional evidence, but clearly frame it
    as a future human check. Do not imply that the missing evidence already
    supports a cause.

24. Only describe geographic relationships using location results actually
    retrieved during this investigation.
SOURCE TRACEABILITY
25. risk_score is a model score. Do not describe it as probability,
    likelihood, certainty, confidence, near-certain, near-maximum, or a
    percentage unless the trusted tool explicitly supplies that
    interpretation. Prefer the supplied risk_level for classification.

26. anomaly_score is a numeric stored score. Do not label the score itself
    high, low, severe, significant, or near a threshold unless a trusted
    tool supplies that classification. anomaly direction and is_anomaly
    must be reported as separate supplied fields.

27. Report active_hours as the supplied count. Do not translate it into
    phrases such as fully active, continuously active, or active all day
    unless a trusted tool explicitly defines the field that way.

28. When summarising tool evidence, do not introduce qualitative labels
    such as reassuring, concerning, minor, major, notable, sustained,
    elevated, sharp, modest, dominant, or unusual unless that label is
    explicitly supplied by a trusted tool or clearly marked as inference.
When stating factual network evidence, identify the trusted tool that supplied
it using this notation:

[Source: tool_name]

Do not cite a tool that was not actually used.

If evidence from different tools disagrees, report the disagreement rather
than silently reconciling it.
"""


def _get_client() -> Anthropic:
    api_key = os.getenv("ANTHROPIC_API_KEY")

    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured.")

    return Anthropic(api_key=api_key)


def _get_model() -> str:
    model = os.getenv("ANTHROPIC_MODEL")

    if not model:
        raise RuntimeError("ANTHROPIC_MODEL is not configured.")

    return model


def _json_safe(value):
    """
    Convert project service results into JSON-compatible structures.
    """

    if hasattr(value, "model_dump"):
        return value.model_dump()

    if isinstance(value, dict):
        return {
            key: _json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]

    return value


def _tool_result_block(tool_use_id: str, result, is_error: bool = False):
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": json.dumps(
            _json_safe(result),
            default=str,
            allow_nan=False,
        ),
        "is_error": is_error,
    }


def ask_noc_assistant(question: str) -> dict:
    """
    Answer one NOC question using trusted C2 tools.

    Pipeline status is executed by the application before Claude receives
    the user's question. Claude can then request additional trusted tools.

    Returns the final answer plus a trace of tools actually executed.
    """

    if not isinstance(question, str) or not question.strip():
        raise ValueError("A non-empty NOC question is required.")

    client = _get_client()
    model = _get_model()

    tool_trace = []

    # C2 guardrail: pipeline status is always the first trusted evidence.
    try:
        pipeline_status = execute_noc_tool(
            "get_pipeline_status",
            {},
        )

        tool_trace.append({
            "tool": "get_pipeline_status",
            "input": {},
            "ok": True,
        })

    except Exception as exc:
        pipeline_status = {
            "available": False,
            "error": (
                "Pipeline status could not be retrieved. "
                f"{type(exc).__name__}: {exc}"
            ),
        }

        tool_trace.append({
            "tool": "get_pipeline_status",
            "input": {},
            "ok": False,
        })

    messages = [
        {
            "role": "user",
            "content": (
                "The application checked pipeline status before beginning "
                "this investigation.\n\n"
                "[Trusted tool result: get_pipeline_status]\n"
                f"{json.dumps(_json_safe(pipeline_status), default=str)}"
                "\n\n"
                f"NOC question:\n{question.strip()}"
            ),
        }
    ]

    for _ in range(MAX_TOOL_ROUNDS):
        response = client.messages.create(
            model=model,
            max_tokens=1800,
            system=SYSTEM_PROMPT,
            tools=CLAUDE_NOC_TOOLS,
            messages=messages,
        )

        assistant_content = response.content

        tool_uses = [
            block
            for block in assistant_content
            if getattr(block, "type", None) == "tool_use"
        ]

        if not tool_uses:
            text_parts = [
                block.text
                for block in assistant_content
                if getattr(block, "type", None) == "text"
            ]

            final_answer = "\n".join(text_parts).strip()

            if not final_answer:
                raise RuntimeError(
                    "Claude returned no final NOC response."
                )

            return {
                "answer": final_answer,
                "tools_used": tool_trace,
            }

        # Preserve Claude's tool requests in conversation history.
        messages.append({
            "role": "assistant",
            "content": assistant_content,
        })

        tool_results = []

        for tool_use in tool_uses:
            tool_name = tool_use.name
            tool_input = tool_use.input or {}

            try:
                result = execute_noc_tool(
                    tool_name,
                    tool_input,
                )

                tool_trace.append({
                    "tool": tool_name,
                    "input": tool_input,
                    "ok": True,
                })

                tool_results.append(
                    _tool_result_block(
                        tool_use.id,
                        result,
                    )
                )

            except Exception as exc:
                error_result = {
                    "available": False,
                    "error": (
                        f"{type(exc).__name__}: {exc}"
                    ),
                }

                tool_trace.append({
                    "tool": tool_name,
                    "input": tool_input,
                    "ok": False,
                })

                tool_results.append(
                    _tool_result_block(
                        tool_use.id,
                        error_result,
                        is_error=True,
                    )
                )

        messages.append({
            "role": "user",
            "content": tool_results,
        })

    raise RuntimeError(
        f"Claude exceeded the maximum of {MAX_TOOL_ROUNDS} tool rounds."
    )