# ML4 — Add an Anomaly Baseline

## Purpose

ML4 adds a second independent intelligence mechanism based on historical
behaviour.

Unlike ML3, which predicts future absolute high activity, ML4 detects
whether the current activity of a grid is unusually high or unusually
low compared with its own historical behaviour at the same hour of day.

---

## Shared Baseline Implementation

A shared baseline function was created in:

app/services/activity_baseline_service.py

Both NP3 and ML4 use this implementation.

NP3 uses:

bucket = "all_history"

ML4 uses:

bucket = "hour_of_day"

This avoids maintaining separate historical-baseline implementations.

---

## Hour-of-Day Baseline

For a grid evaluated at time t, ML4 compares the current activity against
previous observations for the same grid and same hour-of-day.

Example:

Current activity at 23:00

is compared against:

previous 23:00 observations for that grid

rather than against all hours mixed together.

The baseline uses only observations strictly before the current timestamp.

---

## Baseline History Validation

At:

2013-11-07 23:00:00

all 10,000 grids were scored.

Baseline sample counts:

Minimum = 6
Maximum = 6

Therefore each hour-of-day baseline uses six historical days.

---

## Anomaly Score

The anomaly score is a standardized deviation:

anomaly_score =
(current_activity - historical_same_hour_mean)
/
historical_same_hour_standard_deviation

Threshold:

absolute anomaly score >= 2.0

Direction:

positive score = high
negative score = low

---

## ML4 Results

Timestamp:

2013-11-07 23:00:00

Scored grids:

10,000

High anomalies:

1,139

Low anomalies:

276

Total anomalies:

1,415

---

## Manual Validation — High Anomalies

### Grid 6477

Historical 23:00 activity:

410.7693
382.4848
425.1315
422.4134
421.0265
447.7334

Current:

1265.9122

Baseline mean:

418.2598

Baseline standard deviation:

19.4798

Anomaly score:

+43.5144

Direction:

high

This is a legitimate high anomaly because the current value is far above
the previous same-hour observations.

### Grid 2783

Historical 23:00 values were approximately:

173 to 203

Current:

438.4100

Baseline mean:

188.6190

Anomaly score:

+21.1866

Direction:

high

---

## Manual Validation — Low Anomalies

### Grid 4275

Historical 23:00 values were approximately:

307 to 347

Current:

108.3696

Baseline mean:

324.1386

Anomaly score:

-15.6676

Direction:

low

This is a legitimate low anomaly because the current value is far below
its normal same-hour historical level.

### Grid 4073

Historical 23:00 values were approximately:

1250 to 1481

Current:

473.0520

Baseline mean:

1381.5334

Anomaly score:

-10.6820

Direction:

low

---

## Three-Way Comparison

At the latest timestamp:

ML3 positives:

942

NP3 alerts:

7

ML4 anomalies:

1415

ML4 high anomalies:

1139

ML4 low anomalies:

276

The three mechanisms intentionally measure different operational signals.

ML3:
predicts future absolute high activity.

NP3:
detects unusually high activity relative to a grid's broader historical
baseline.

ML4:
detects unusually high or unusually low activity relative to the same
hour-of-day historical baseline.

---

## Signal Combination Counts

ML3=0, NP3=0, ML4=0:

7779

ML3=0, NP3=0, ML4=1:

1273

ML3=1, NP3=0, ML4=0:

805

ML3=1, NP3=0, ML4=1:

136

ML3=0, NP3=1, ML4=1:

6

ML3=1, NP3=1, ML4=0:

1

---

## Example Disagreement — Grid 6572

Current activity:

4177.823

ML3 risk score:

0.993997

ML3 result:

positive

NP3 z-score:

3.391754

NP3 result:

alert

ML4 anomaly score:

0.419468

ML4 result:

not anomalous

Interpretation:

ML3 sees a high probability of future absolute high activity.

NP3 sees the current value as unusually high relative to the broader
historical baseline.

ML4 does not flag the grid because the value is not sufficiently unusual
relative to this grid's historical behaviour at the same hour of day.

This disagreement is legitimate because the three mechanisms use
different reference frames.

---

## Example Low-Anomaly Disagreement — Grid 766

Current activity:

361.5666

ML3 risk score:

0.021032

NP3 z-score:

-0.595342

ML4 anomaly score:

-3.185682

ML4 direction:

low

Interpretation:

ML3 does not flag the grid because it is not predicting high future
activity.

NP3 does not alert because NP3 only focuses on positive high deviations.

ML4 identifies the grid because its activity is unusually low relative
to its normal activity at the same hour of day.

---

## Observations

1. Hour-of-day baselines detect contextual anomalies that broader
historical baselines can miss.

2. Low anomalies are visible in ML4 but are not represented by the
existing NP3 high-only rule or the ML3 high-activity classifier.

3. Disagreement between ML3, NP3 and ML4 is expected because each
mechanism answers a different operational question.

---

## Limitations

Only six previous same-hour observations are available for each baseline.

Because the historical sample is small, baseline standard deviation can
be very small, producing large anomaly scores.

The anomaly score indicates unusual activity and must not be interpreted
as confirmed congestion, outage, degradation, or capacity exhaustion.