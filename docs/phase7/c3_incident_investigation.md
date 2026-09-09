# C3 Incident Investigation Report

## Incident

**Grid:** 4821  
**Analytics timestamp:** 2013-11-07 23:00:00  
**Investigation question:** Determine what is true now, whether the supplied
history shows this has happened before, and what remains uncertain.

---

## CURRENT EVIDENCE

Current total activity is **254.9675**, compared with the supplied
baseline total activity of **387.7731**.

The current anomaly evidence reports:

- anomaly_score: **-1.7291263469844511**
- anomaly_direction: **low**
- is_anomaly: **false**
- baseline_sample_count: **6**

The supplied anomaly reason states that the activity is within the expected
historical range for this grid at the same hour of day.

No rule-based alerts are currently supplied for Grid 4821.

Current predictive evidence reports:

- risk_score: **0.020920419025418798**
- risk_level: **low**
- model_version: **ml3-logreg-v1**

The risk score is an investigation-priority signal and is not interpreted as
a probability or as proof of congestion, outage, fault, or capacity exhaustion.

The preceding 24 completed activity intervals have:

- average total activity: **360.7345958333333**
- minimum total activity: **136.5792**
- maximum total activity: **666.7446**

---

## HISTORICAL EVIDENCE

There are **167 historical activity intervals** before the current incident
timestamp.

Across those intervals:

- average total activity: **340.39020658682637**
- minimum total activity: **119.8158**
- maximum total activity: **765.1382**

The current activity of **254.9675** lies within the supplied historical
activity range. Therefore, activity at or below the current level has been
observed previously.

Historical anomaly evidence cannot be evaluated from the persisted anomaly
snapshot because there are no anomaly-score records before the current
timestamp.

Historical predictive-risk evidence is also unavailable because the persisted
risk-score table contains only the current scoring snapshot.

These evidence gaps must not be interpreted as proof that no previous anomaly
or elevated-risk event occurred.

---

## UNCERTAINTY

The current real pipeline status is healthy:

- all recorded pipeline tasks succeeded
- rows_rejected: **0**
- nulls_handled: **0**
- freshness_hours: **0.0**

The pipeline execution timestamp belongs to the processing run and must remain
separate from the historical analytics timestamp of
**2013-11-07 23:00:00**.

Historical ML evidence remains incomplete because the anomaly and risk tables
are latest-snapshot stores rather than historical score stores.

The evidence does not establish congestion, capacity exhaustion, outage,
hardware failure, service degradation, or a specific root cause.

---

## Dumped vs Curated Context Experiment

The same Grid 4821 investigation question, Claude model, and grounding rules
were used for both context strategies.

| Context strategy | Characters |
|---|---:|
| Dumped | 33,552 |
| Curated | 2,517 |
| Reduction | 31,035 |
| Curated / Dumped ratio | 0.075 |

The curated package reduced context size by approximately **92.5%**.

The dumped package included additional information such as the complete
24-point aggregated activity response, location, network summary, and a large
hotspot response.

The curated package instead retained the evidence directly relevant to the
incident question and supplied summarized recent and historical activity.

The curated response could therefore use the 167-interval historical summary
to determine that the current activity level was within the previously
observed range.

The dumped response did not receive that purpose-built historical summary and
reported that it could not make the same historical comparison.

This demonstrates that adding more context does not necessarily improve an
incident investigation. Selecting and summarizing evidence can produce a
smaller and more relevant reasoning context.

---

## Pipeline Trust Experiment

A second experiment replaced only the pipeline-status portion of the curated
context with synthetic unhealthy evidence. The real DE7 status was not
modified.

Synthetic evidence included:

- healthy: **false**
- quality_check: **failed**
- rows_rejected: **12**
- nulls_handled: **8**
- freshness_hours: **6.0**

Claude materially changed the UNCERTAINTY section and treated these conditions
as limitations on confidence in the supplied evidence.

This demonstrates that pipeline quality is being used as investigation
evidence rather than being included as unused metadata.

---

## Conclusion

For Grid 4821, the supplied evidence shows that current activity is within the
range previously observed in the available activity history.

The current interval is not marked as an anomaly, no rule alert is supplied,
and the predictive risk level is low.

However, historical anomaly and predictive-risk comparisons cannot be made
because historical ML scoring snapshots are unavailable.

The investigation does not provide evidence sufficient to claim congestion,
outage, capacity exhaustion, hardware failure, service degradation, or a
specific root cause.

The C3 experiment also demonstrates that curated, summarized context can be
substantially smaller while being more useful for the specific investigation
question than a broad dump of available evidence.