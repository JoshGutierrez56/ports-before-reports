# Model card

## Intended use and result

Calls-to-TEU benchmark beat the geography-aware model; the gain over aggregate shipping was uncertain.

- Unit of prediction: monthly selected-gateway loaded-import TEUs, four official port labels / three physical gateways.
- Primary comparison: geography ridge vs aggregate-activity ridge; additional benchmark selected solely on 2023 validation: Calls-to-TEU benchmark.
- Sample: 12 validation months; 24 test months (2024–2025); 2026 excluded.
- Availability: current-vintage pseudo-real-time, assumed 7-day shipping / 60-day undated-target delay. No historical release-vintage proof.
- Features: two released-target growth features; two aggregate or six gateway call-growth features. Training-only scaling; ridge alpha grid [1,10,100].
- Primary selected penalties: `{"aggregate_activity_ridge": 1.0, "geography_ridge": 1.0, "released_target_ridge": 1.0}`.
- Target: log annual growth; released seasonal base reconstruction; no inverse bias correction, outcome-driven clipping or forecast intervals.
- Missingness: shared seasonal fallback; primary full-policy fallback 12.5%. Missing traffic is never zero.
- Claim status: PROMISING_BUT_UNCERTAIN; source and protocol hash: `1d853f3d8a9e9185cbaad64b44d20d7630a239c2bf45ac405fd8e90e9400fda0`.

## Evaluation

| Model | WAPE | MAE · TEUs | RMSE · TEUs | Bias · TEUs | YoY direction |
| --- | --- | --- | --- | --- | --- |
| Last year's month | 11.23% | 162,177 | 185,904 | -115,338 | 0.0% |
| Released target history | 8.92% | 128,852 | 164,547 | -9,778 | 66.7% |
| Aggregate shipping | 11.89% | 171,759 | 197,700 | +74,874 | 62.5% |
| Geographic shipping | 11.21% | 161,994 | 182,841 | +90,026 | 79.2% |
| Calls-to-TEU benchmark | 7.34% | 106,077 | 127,723 | -46,479 | 66.7% |

| Comparator | Relative lift | 3-month block 95% interval | 6-month block 95% interval |
| --- | --- | --- | --- |
| Aggregate shipping | +5.69% | [-23.28%, +30.93%] | [-28.18%, +25.22%] |
| Calls-to-TEU benchmark | -52.71% | [-117.87%, -21.01%] | [-115.42%, -37.02%] |

## Limits and prohibited claims

The geospatial engine is separate from H1. Its 2024 observations cannot create earlier measured congestion. Current-vintage revisions, short test history, estimated port-call boundaries and model complexity limit interpretation. Queue candidates are not verified delayed loaded-import ships. No causal, profitable, alpha, live, institutional-adoption, production-grade or independent-human-validation claim is supported. The optional equity extension is **NOT_REQUIRED_FOR_V1** and not executed.

## Operations

Local batch research only. No daemon/scheduler, remote writes or paid resources. Source acquisition uses bounded retry/rate limits, immutable hashes and resumable receipts. Failure to satisfy a source contract stops that stage or uses the declared shared fallback; it never fabricates a target. Prospective packets are append-only and refuse after-cutoff snapshots or already-known current outcomes.
