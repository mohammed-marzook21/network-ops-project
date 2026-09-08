# C1 Model Selection Rationale

## Selected model
Claude Sonnet 4.6

Environment configuration:

ANTHROPIC_MODEL=claude-sonnet-4-6

## Reason for selection

Phase 7 C1 requires Claude to convert curated network evidence into a grounded
operational explanation containing exactly four sections:

- SEVERITY
- EVIDENCE
- INTERPRETATION
- NEXT CHECKS

The model must reason across potentially conflicting signals such as:

- current activity versus historical baseline,
- anomaly score and anomaly direction,
- rule-based alerts,
- engineered ML features,
- next-hour predictive risk.

At the same time, it must avoid unsupported conclusions such as congestion,
outage, capacity exhaustion, fault, or customer impact.

Claude Sonnet 4.6 was selected because it provides a practical balance between
reasoning quality, response latency, and API cost for repeated NOC-style
investigation requests.

## Quality

The task requires stronger reasoning than simple extraction or templating.
Claude must preserve the distinction between evidence and inference, explain
signal disagreements, and explicitly identify insufficient evidence.

During C1 validation, the model successfully handled examples where rule-based,
anomaly, and predictive-risk signals disagreed without treating them as
equivalent measurements.

## Latency

Operational NOC explanations are interactive rather than long-running offline
analysis. Sonnet provides sufficiently strong reasoning while avoiding the
higher latency expected from using the most computationally intensive model for
every investigation.

## Cost

C1 may generate explanations repeatedly for many grid investigations. Using a
high-quality general reasoning model provides a more sustainable cost profile
than selecting the most expensive model for every request.

The design also limits token usage by sending only curated evidence rather than
raw telecom activity rows.

## Operational constraint

The Claude response is an engineering-assistance layer, not a source of network
truth.

All numerical claims must originate from curated evidence produced by the
analytics and ML layers. Claude may interpret those signals and recommend human
checks, but it must not invent measurements or assert congestion, outage,
fault, capacity exhaustion, or service degradation unless those facts are
explicitly supported by supplied evidence.

## C1 validation

C1 was validated across multiple real grid scenarios including:

- a normal grid,
- a high rule-alert and high predictive-risk case,
- a strong current anomaly with low next-hour predictive risk,
- a high predictive-risk grid with no current rule alert,
- a normal high-activity grid.

The validation also removed anomaly evidence from a test case and confirmed that
Claude explicitly reported insufficient anomaly evidence instead of inventing
an anomaly assessment.
