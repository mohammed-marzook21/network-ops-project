# NP1 — Data Profiling Summary
**Audience:** Network Analytics Team
**File analyzed:** sms-call-internet-mi-2013-11-01.csv

- The file covers 24 hourly intervals across 10,000 unique grid cells in the Milan network, spanning 2013-11-01 00:00 to 23:00.
- Activity is recorded across 246 distinct country codes; a single grid and hour can have multiple country-code rows (e.g. grid 1 at 00:00 has 3 separate rows), so records must be aggregated to grid+hour before any KPI is computed.
- Roughly half of all activity columns are blank in a given row (e.g. sms_in is null in 1,086,153 of 1,891,928 rows) — this reflects that most grid/hour/country combinations only register activity in one or two channels, not that data is missing or corrupted.
- The busiest hour of day was 11:00 (11 AM), and the busiest grid cell was grid 5161, based on total activity (SMS + calls + internet).
- No negative values or exact duplicate rows were found across any activity column — the source file is clean.