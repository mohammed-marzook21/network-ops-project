# NP3 — Limitation Statement

**Baseline used:** Within-day median, excluding the current hour.

**Alert volume:** 41,121 alerts across 240,000 grid/hours (17.13%), using
HIGH_ACTIVITY/SPIKE ratio of 1.5x and DROP ratio of 0.5x, with an activity
floor at the 10th percentile of daily totals (928.35).

**Structural limitation:**
This within-day baseline has no concept of what is "normal" for a given grid
at a specific hour of day. It cannot distinguish "this grid is always quiet
at 3 AM" from "this grid's activity has genuinely dropped" — both look
identical to a baseline built from a single day, because that baseline only
knows the grid's own within-day median, not its typical behavior at that
specific hour.

**What would fix this:** Multiple days of historical data, allowing an
hour-of-day baseline (e.g. "what does grid 10 normally do at 14:00?") instead
of a within-day baseline. This is exactly what Phase 2 and Phase 3 accumulate,
and is the motivation for the smarter baseline built later in lab ML4.