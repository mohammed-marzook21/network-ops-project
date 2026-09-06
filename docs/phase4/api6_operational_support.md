# API6 - Operational Support Endpoints

## Phase 4 -  Network Operations Predictive Intelligence Project

API6 provides operational evidence sources for the Network Operations
Assistant and the Claude phase.

These endpoints are sanctioned evidence sources. The assistant must use
these APIs to retrieve current pipeline health and grid location evidence
rather than narrating information from memory.

---

# 1. Pipeline Status

## GET `/pipeline/status`

### Business Question

**Can I trust this data right now?**

### Data Source

This endpoint reads the machine-readable pipeline status record generated
by the DE7 `quality_check` task.

The endpoint reads the DE7 status record directly and does not independently
recompute pipeline execution metrics. This ensures there is one source of
truth for pipeline operational status.

### Response Evidence

The endpoint returns:

- `healthy`
- `reasons`
- `run_id`
- `run_timestamp`
- `per_task_status`
- `rows_in`
- `rows_rejected`
- `nulls_handled`
- `rows_published`
- `as_of`
- `freshness_hours`

### Healthy Status

The top-level `healthy` field allows an operations assistant or other
caller to quickly determine whether the latest pipeline result can be
considered healthy.

When `healthy` is `false`, the `reasons` list explains why the pipeline
is considered unhealthy.

Examples of unhealthy conditions include:

- A pipeline task did not complete successfully.
- No per-task status is available.
- No rows were published.
- The pipeline status record is missing `AS_OF`.
- The pipeline `AS_OF` does not match the latest analytics timestamp.
- The analytics layer cannot provide a timestamp for freshness validation.

### Claude Phase Evidence

The Claude Network Operations Assistant must use:

```text
GET /pipeline/status