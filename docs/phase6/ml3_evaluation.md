# ML3 — Train and Evaluate Baseline Model

## Problem

Predict whether a grid will experience unusually high absolute network
activity in the next hourly interval.

Prediction unit:

- one grid_id
- at prediction timestamp t
- target measured at t+1

The positive class is an investigation signal and does not represent
confirmed congestion, outage, or capacity exhaustion.

---

## Features

The model uses the six ML2/API4 features:

- avg_activity
- activity_growth
- active_hours
- peak_ratio
- variability
- internet_share

All features are calculated using information available at or before t.

---

## Target

Target:

high_activity_next_hour

Definition:

next_hour_total_activity > training-period 90th percentile

Training-only threshold:

1177.6937000000003

The target threshold was calculated exclusively from training-period
outcomes and was then applied unchanged to both training and test data.

---

## Chronological Split

Training:

2013-11-02 23:00:00
to
2013-11-06 22:00:00

Training rows:

959,908

Testing:

2013-11-06 23:00:00
to
2013-11-07 22:00:00

Test rows:

239,976

The train and test periods do not overlap.

No random split was used.

---

## Class Balance

Training positive rate:

10.00%

Test positive rate:

10.77%

---

## Model

Algorithm:

Logistic Regression

Model version:

ml3-logreg-v1

Preprocessing:

- median imputation
- standard scaling
- Logistic Regression

---

## Test Metrics

Accuracy:

0.95294

Precision:

0.82154

Recall:

0.71940

Base rate:

0.10773

Confusion matrix:

TN = 210084
FP = 4040
FN = 7254
TP = 18598

---

## Coefficients

Standardized Logistic Regression coefficients:

avg_activity       +3.280088
peak_ratio         +0.372510
variability        -0.206151
activity_growth    -0.118735
internet_share     -0.061210
active_hours        0.000000

avg_activity was the dominant predictive feature.

---

## High-Accuracy Investigation

Accuracy exceeded 95%, so additional leakage and baseline checks were
performed.

Always-normal baseline:

Accuracy = 0.89227
Precision = 0
Recall = 0

Correlation between avg_activity and next-hour activity:

0.8561

This is a strong relationship but not a near-perfect one.

Feature timestamps end at t and labels are measured exactly at t+1.
The target threshold is calculated only from training-period outcomes.

A simple avg_activity threshold baseline produced:

Accuracy = 0.95639
Precision = 0.78582
Recall = 0.81820

Therefore, much of the predictability comes from strong temporal
persistence in network activity.

The Logistic Regression model should not be claimed to outperform every
simple operational baseline.

---

## Comparison With NP3 Rule-Based Alerts

Across 239,976 aligned test rows:

Actual high-activity labels:

25,852

ML positive predictions:

22,638

NP3 alerts:

7,362

Agreement:

Both positive = 1,127
ML only = 21,511
NP3 only = 6,235
Neither = 211,103

Agreement rate:

88.44%

When evaluated against the ML3 high-activity target:

ML:

Accuracy = 0.95294
Precision = 0.82154
Recall = 0.71940

NP3:

Accuracy = 0.88001
Precision = 0.30019
Recall = 0.08549

This does not mean that NP3 is inferior.

The two methods answer different operational questions.

ML3 predicts future absolute high activity.

NP3 detects unusual activity relative to the individual grid's own
historical baseline.

---

## Example Disagreement

Grid 3558:

Next-hour activity = 1267.8874
ML risk score = 0.787695
NP3 z-score = -0.537360
Actual high-activity label = 1

ML correctly identified absolute high activity, while NP3 did not alert
because this activity was not unusual relative to the grid's own history.

Grid 8586:

Next-hour activity = 537.5710
ML risk score = 0.017413
NP3 z-score = 2.521249
Actual high-activity label = 0

NP3 detected an unusual increase relative to this grid's historical
behavior even though absolute activity did not cross the ML3
high-activity threshold.

---

## Observations

1. Recent activity is highly predictive of next-hour activity.
   avg_activity was the strongest Logistic Regression feature and had
   a correlation of 0.8561 with next-hour activity.

2. ML3 and NP3 capture complementary operational signals.
   ML3 focuses on future absolute high activity while NP3 focuses on
   grid-specific anomalies.

3. The simple avg_activity threshold achieved slightly higher accuracy
   and recall than Logistic Regression, so ML3 should not be presented
   as universally superior to simple rules.

---

## Limitations

Only seven days of source history are currently available.

The high-activity target is a statistical proxy rather than a physical
network-capacity or congestion label.

The model has been validated only on the current historical dataset and
is not being represented as production-ready.