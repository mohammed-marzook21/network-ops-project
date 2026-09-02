DE4 — Batch vs Streaming Decision Workshop
Proposed classification by Claude — reviewed/challenged, not authored, by Mohammed Marzook

Hotspot alerts should remain batch-based because the analytics data is only available when the daily hourly_grid_summary file arrives. Even if we introduce a streaming system, it cannot generate earlier alerts because there are no new events available to process during the day. Therefore, batch processing is more practical here because streaming would increase infrastructure and maintenance complexity without improving the actual alerting latency.

The hypothetical live activity scenario is different because the data would be continuously generated and available in real time, while the other scenarios depend on files or periodic aggregated data. Since this scenario requires decisions or alerts within seconds, waiting for a daily or scheduled batch would be too slow. Streaming is therefore appropriate because it can process each event as it arrives and provide the required low-latency response.

Decision Matrix
Scenario	Source	Arrival Pattern	Required Latency	Decision
Daily usage summary	telecom_pipeline.py output (hourly_grid_summary)	Once per day (batch file)	24 hours	Batch
Hypothetical live activity events	Hypothetical real-time telecom event stream (not present in this dataset)	Continuous	Seconds	Streaming (hypothetical only)
Billing report	Aggregated monthly usage	Monthly batch cycle	30 days	Batch
Hotspot alerts	NP3/analytics rule engine on hourly_grid_summary	Hourly, but bound by the daily file arrival	15–60 minutes would be ideal, but capped by data arrival	Batch
Executive dashboard refresh	Analytics warehouse tables	Daily refresh is sufficient for exec reporting	24 hours	Batch
Model training and scoring	Historical aggregated data	Training: periodic (weekly/monthly). Scoring: daily today	Training: days. Scoring: 24 hours today, seconds if live events existed	Batch today; Streaming is the hypothetical future path for scoring only
Why files are processed as batch even though real network activity is continuous

The underlying phenomenon (people using their phones) is continuous, but the data itself arrives as one file per day — regardless of how continuous the real-world activity is, this system only ever sees a new batch once every 24 hours. Batch processing matches the actual arrival pattern of the data source, not the theoretical continuity of what that data represents.

Where Kafka could conceptually enter (without changing this dataset)

If a real-time event source existed (e.g., cell towers emitting individual activity events as they happen), Kafka would sit as a message queue between those producers and a streaming consumer (Spark Structured Streaming or similar) — decoupling "something happened" from "something processed it." Critically, this would be an entirely new, parallel path, not a replacement for the existing batch pipeline — the daily CSV export and the batch Spark job would keep running unchanged for the use cases that genuinely only need daily freshness (billing, exec dashboards, daily summaries).

[NEEDS YOUR OWN WORDS] Defend the Hotspot Alerts batch decision

Why is "batch, because streaming would add cost without adding value here" the right call for hotspot alerts specifically, given the data only arrives once a day? Write 2-3 sentences in your own words — this is one of the two things your guide explicitly says only you can satisfy.

Draft starting point (edit this, don't just copy it): "Even if we built a real-time streaming alert pipeline, there would be nothing new to alert on until the next day's file arrives anyway — so the added Kafka/Spark Streaming complexity would buy us zero actual improvement in how fast alerts reach anyone, since the bottleneck is the data's arrival pattern, not the processing speed."

[NEEDS YOUR OWN WORDS] Defend the hypothetical streaming choice

You classified "hypothetical live activity events" as needing seconds-level latency and streaming. In your own words: what about this specific scenario is different from the other five, that makes streaming the right call there but nowhere else?

Revised Architecture Note

The streaming path (Kafka → Spark Structured Streaming → a real-time scoring/alerting layer) is drawn as an optional, unbuilt extension sitting alongside the existing batch pipeline from DE1 — see the "↳ Connects to: Future Kafka extension" note in the guide. Nothing in Phase 3 requires building this; it exists only as a documented possibility for if/when a real live data source is ever introduced.