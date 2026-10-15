# Availability audit

**Default mode: current-vintage pseudo-real-time.** Collection occurred in October 2026. Observation dates do not establish public release times. The retrospective lock does not erase prior human/agent knowledge of economic events.

| Layer | Observation dates | Verified availability | Assumption / consequence |
| --- | --- | --- | --- |
| PortWatch container calls | 2019–2025 | Actual retrieval receipts in 2026; no archived historical vintages | Day-21 origin, shipping lags7/14/28; current methods include post-period revisions |
| Official loaded imports | 2019–2025 | 0/336 verified first-release timestamps | 60-calendar-day lag after monthend, repeated90; no current-month training |
| NOAA raw positions | 2024 | Archive published after observations; source/file headers recorded | Retrospective descriptive only; not a contemporaneously public2024 predictor |
| Prospective extension | Future, only if executed | Must save actual acquired snapshots by origin | Append-only command, no scheduler and no completed live forecast claimed |

`verified_available_at_utc` and `assumed_available_at_utc` remain distinct. Retrieval or Last-Modified cannot be silently relabeled a historical first release. The PortWatch July2026 vessel addition, earlier classification/boundary revisions and current-vintage calibration mean a7-day lag alone cannot prove point-in-time validity. Exact source metadata and methodology changes are in the access audit.

At each origin, training labels and annual denominators must be released; target-history predictors are reconstructed as of their own historical origin. Standardization uses only admitted training rows. A chronological split alone is insufficient. Forecast origin is the exclusive start of day22UTC; a7-day lag admits complete daily intervals ending by day15UTC (observations through day14). Leap-year and missing-window boundaries are tested.

Verified lead-time denominator: **0 monthly releases**. Therefore no claim of 'X days ahead of official reports' is calculated. All public copy says historical nowcast under assumed reporting lags. No bootstrap confidence interval is presented as a forecast band.

All predefined lag sensitivity results:

| Shipping lag | Unknown target lag | Geography WAPE | Aggregate WAPE | Selected baseline WAPE |
| --- | --- | --- | --- | --- |
| 7 | 60 | 11.21% | 11.89% | 7.34% |
| 7 | 90 | 11.34% | 12.37% | 7.30% |
| 14 | 60 | 10.00% | 9.07% | 6.25% |
| 14 | 90 | 10.52% | 9.26% | 6.29% |
| 28 | 60 | 10.36% | 10.04% | 7.81% |
| 28 | 90 | 11.12% | 9.33% | 7.92% |

The deliberately future-shifted placebo is diagnostic-only and explicitly forbidden in production. See `artifacts/audit/time_shift_placebo_forbidden.json`. Future-append invariance results are in `artifacts/metrics/robustness.json`. No future-completed queue duration enters an earlier as-of feature.
