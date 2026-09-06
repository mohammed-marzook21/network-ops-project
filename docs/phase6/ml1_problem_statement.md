1. Future activity leakage
   Risk:
   A feature accidentally uses activity from t+1.

   Prevention:
   Every feature query/window must stop at t.

2. Circular target leakage
   Risk:
   Label and features are calculated from the same time window.

   Prevention:
   Features end at t.
   Label belongs exclusively to t+1.

3. Threshold leakage
   Risk:
   The high-activity threshold is calculated using future/test data.

   Prevention:
   During model training, derive the threshold from training-period
   history only and apply it unchanged to later data.

4. Random train/test leakage
   Risk:
   Neighbouring hourly observations are randomly mixed between train
   and test.

   Prevention:
   ML3 will use a chronological split:
   earlier timestamps -> training
   later timestamps -> testing.