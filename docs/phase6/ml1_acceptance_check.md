# ML1 — Acceptance Check

## Problem

Primary ML problem:

Predict high-activity risk for the next hourly interval.

---

## Acceptance Criteria

### 1. Prediction unit defined

PASS

Prediction unit:

    one grid_id at timestamp t

The model predicts the state of the same grid at the next hourly interval t+1.

---

### 2. Label definition documented

PASS

Target:

    high_activity_next_hour

Definition:

    1 = total_activity at t+1 exceeds the approved high-activity proxy threshold
    0 = otherwise

Initial proposed proxy threshold:

    90th percentile of total_activity from training-period history

This threshold is a training proxy and is not a physical capacity threshold.

---

### 3. Exact t / t+1 boundary documented

PASS

Features:

    data available up to and including t

Label:

    next interval t+1

Example:

    feature_timestamp = 2013-11-07 22:00:00
    label timestamp    = 2013-11-07 23:00:00

No value from 23:00 may contribute to features for 22:00.

---

### 4. Future label confirmed

PASS

The label belongs only to the future interval t+1.

The label is not calculated from the same window as the features.

---

### 5. Non-goals documented

PASS

The model does NOT claim:

- congestion
- capacity exhaustion
- throughput degradation
- latency degradation
- packet loss
- radio utilization problems
- confirmed outage
- confirmed network fault

---

### 6. Business action defined

PASS

Positive prediction means:

    Investigate the grid and review supporting operational signals.

It does NOT mean:

    The network is congested.

---

### 7. Leakage risks identified

PASS

Identified risks:

1. future-data leakage
2. circular target leakage
3. threshold leakage
4. chronological train/test leakage

Controls:

- every feature ends at t
- target belongs to t+1
- threshold derived from training history only
- ML3 will use a chronological split

---

## One-Sentence Model Knowledge Statement

At prediction time, the model combines multiple historical activity patterns
through timestamp t to estimate the probability of high activity at t+1,
rather than simply testing whether the current interval already exceeds a
threshold.

---

## ML1 Status

ML1 COMPLETE

Primary problem:
    high-activity risk

Prediction unit:
    grid_id + timestamp t

Features:
    historical information <= t

Target:
    high_activity_next_hour at t+1

Business action:
    investigate

Non-goals:
    congestion, capacity, throughput