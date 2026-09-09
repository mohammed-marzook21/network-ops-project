# C3 Context Engineering Checklist

## Purpose

This checklist defines how historical network evidence should be selected,
summarized, and supplied to Claude for incident investigation.

## Evidence Selection

- [x] Use curated analytics and service outputs only.
- [x] Do not expose raw source telecom rows to Claude.
- [x] Include the current grid and incident timestamp.
- [x] Include current activity and supplied baseline evidence.
- [x] Include current anomaly evidence when available.
- [x] Include current predictive-risk evidence when available.
- [x] Include current rule alerts when available.
- [x] Include pipeline status for data-trust assessment.

## Historical Context

- [x] Summarize recent history before adding it to active context.
- [x] Keep the current incident interval out of historical summaries.
- [x] Summarize older activity history rather than dumping individual rows.
- [x] Distinguish activity history from persisted ML-score history.
- [x] Never interpret zero historical ML rows as zero historical incidents.
- [x] Explicitly mark unavailable historical anomaly evidence.
- [x] Explicitly mark unavailable historical predictive-risk evidence.

## Context Reduction

- [x] Remove evidence that does not help answer the incident question.
- [x] Avoid network-wide summaries unless required by the investigation.
- [x] Avoid large hotspot lists unless directly relevant.
- [x] Avoid location evidence unless geographic reasoning is required.
- [x] Prefer summaries over repeated hourly observations.

## Grounding Rules

- [x] Never invent numeric values.
- [x] Treat telecom values as activity measures.
- [x] Do not claim congestion from activity, anomaly, alert, or risk evidence.
- [x] Do not infer capacity exhaustion, outage, fault, or root cause without evidence.
- [x] Do not convert risk_score into probability or confidence.
- [x] Do not invent anomaly thresholds.
- [x] Do not invent semantics for peak_ratio, variability, or internet_share.
- [x] Keep observed evidence separate from inference.

## Pipeline Trust

- [x] Include pipeline healthy/unhealthy status.
- [x] Treat rejected rows as material uncertainty.
- [x] Treat handled nulls as material uncertainty.
- [x] Treat stale analytics as material uncertainty.
- [x] Treat failed quality checks as material uncertainty.
- [x] Keep pipeline execution timestamp separate from analytics as_of.

## C3 Experiment Results

- Dumped context size: 33,552 characters.
- Curated context size: 2,517 characters.
- Context reduction: 31,035 characters (~92.5%).
- Curated/dumped ratio: 0.075.
- The same Grid 4821 investigation question was used for both runs.
- The same Claude model and grounding rules were used for both runs.
- Curated context retained the historical activity summary needed to answer
  whether similar activity levels had occurred before.
- Dumped context contained substantially more unrelated network evidence but
  lacked the purpose-built 167-interval historical activity summary.
- Removing irrelevant context therefore changed the usefulness and focus of
  the investigation.
- With healthy pipeline evidence, Claude reported no supplied pipeline-quality
  concern.
- With synthetic unhealthy pipeline evidence, UNCERTAINTY materially changed
  to account for rejected rows, handled nulls, stale analytics, and a failed
  quality check.

## Validation

- 24 recent completed intervals are summarized rather than dumped.
- 167 historical activity intervals exist before the current Grid 4821 interval.
- Historical anomaly evidence is unavailable in the persisted snapshot table.
- Historical predictive-risk evidence is unavailable in the persisted snapshot table.
- Missing historical ML evidence is represented as an evidence gap.
- Healthy and unhealthy pipeline scenarios produce materially different
  uncertainty assessments.
- Full automated test suite: 124 passed, 6 warnings.