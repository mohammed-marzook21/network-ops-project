# ML1 — Feature and Target Sheet

## 1. Prediction Unit

Each prediction represents:

- one `grid_id`
- at one prediction timestamp `t`

The model uses only information available up to and including `t`.

The model predicts whether the same grid will experience high activity in the next hourly interval `t+1`.

---

## 2. Time Boundary

Feature window:

    timestamps <= t

Target interval:

    timestamp = t+1

Nothing from `t+1` may be used in the feature calculation.

`feature_timestamp` always records `t`.

---

## 3. Concrete Example

For example:

    grid_id = 4821

    feature_timestamp = 2013-11-07 22:00:00

All six features are calculated using only historical data ending at:

    2013-11-07 22:00:00

The target is determined from the next interval:

    2013-11-07 23:00:00

Therefore:

    features -> history through 22:00

    label -> activity at 23:00

The 23:00 activity value must never contribute to the features calculated for 22:00.

---

## 4. Feature Set

The model uses the same six engineered feature names exposed by API4.

### avg_activity

Meaning:

Average total network activity over the approved trailing feature window ending at `t`.

Time rule:

Only observations at timestamps <= `t` may contribute.

---

### activity_growth

Meaning:

Change in recent activity relative to an earlier baseline window.

Conceptually:

    recent average - baseline average
    ---------------------------------
             baseline average

The exact recent and baseline window lengths will be approved in ML2.

Time rule:

Both windows must occur entirely at or before `t`.

---

### active_hours

Meaning:

Number of hourly intervals in the trailing feature window where activity is greater than zero.

Time rule:

Only hours <= `t`.

---

### peak_ratio

Meaning:

Ratio between the maximum activity and average activity in the trailing window.

Conceptually:

    peak_activity
    -------------
    avg_activity

Division-by-zero behaviour must be handled explicitly.

Time rule:

Only observations <= `t`.

---

### variability

Meaning:

Variation in total activity across the trailing feature window.

A standard deviation or equivalent approved variability measure may be used.

Time rule:

Only observations <= `t`.

---

### internet_share

Meaning:

The proportion of activity represented by internet activity.

Conceptually:

    internet_activity
    -----------------
     total_activity

Division-by-zero behaviour must be handled explicitly.

Time rule:

Only observations <= `t`.

---

## 5. Target

Target name:

    high_activity_next_hour

Target type:

    binary classification

Possible values:

    1 = high-activity risk event at t+1
    0 = no high-activity risk event at t+1

The target describes the future hourly interval only.

---

## 6. Proxy Label Strategy

Because the dataset contains activity measurements but does not contain network capacity or throughput measurements, the target is a training proxy.

Proposed proxy:

    high_activity_next_hour = 1

when:

    total_activity at t+1 > high_activity_threshold

otherwise:

    high_activity_next_hour = 0

The high-activity threshold will be derived from historical training data.

Initial proposed threshold:

    90th percentile of total_activity in the training-period history

Important:

The threshold must not be calculated using future test-period observations.

The 90th percentile is a proxy for unusually high observed activity.

It is NOT a capacity threshold.

---

## 7. What the Model Predicts

Allowed interpretation:

    The grid has elevated predicted risk of high activity
    during the next hourly interval.

Operational action:

    Investigate the grid and review supporting operational signals.

---

## 8. What the Model Does Not Predict

The model must not claim:

- network congestion
- insufficient capacity
- degraded throughput
- latency problems
- packet loss
- radio utilization problems
- confirmed outage
- confirmed network fault

The available data does not directly support these conclusions.

---

## 9. Leakage Risks

### Future-data leakage

Risk:

A feature accidentally includes activity from `t+1`.

Prevention:

Every feature window ends at `t`.

---

### Circular target leakage

Risk:

The label is calculated from the same time window used by the features.

Prevention:

Features describe history through `t`.

The label describes only `t+1`.

---

### Threshold leakage

Risk:

The proxy threshold is calculated using both training and future test data.

Prevention:

Derive the threshold from training-period history only.

Freeze that threshold before evaluating on later data.

---

### Chronological leakage

Risk:

Neighbouring hourly records are randomly split between train and test.

Prevention:

ML3 will use a chronological split:

    earlier timestamps -> training
    later timestamps -> testing

---

## 10. ML1 Summary

Prediction unit:

    one grid_id at timestamp t

Feature boundary:

    historical data <= t

Target:

    high_activity_next_hour at t+1

Model purpose:

    predict elevated future activity risk

Business action:

    investigate

Non-goals:

    congestion
    capacity
    throughput