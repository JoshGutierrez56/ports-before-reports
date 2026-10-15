# Ports Before Reports: research findings

## Finding first

**Calls-to-TEU benchmark beat the geography-aware model; the gain over aggregate shipping was uncertain.** The primary candidate's weighted absolute percentage error was **11.21%**, versus **11.89%** for aggregate shipping and **7.34%** for the strongest noncandidate baseline selected on 2023 validation. The direct geography comparison implies **+5.69% relative lift**, not percentage points of error reduction. The evidence status is **PROMISING_BUT_UNCERTAIN**. The primary statistical gate is separately retained as **PROMISING_BUT_UNCERTAIN**; reporting-lag robustness undermines an unqualified claim: **True**.

This is a retrospective, protocol-locked evaluation conducted in October 2026. It is not a forecast registered before the test years, a verified point-in-time backtest, or a trading-return study. A clear negative or uncertain result remains useful: it tells an analyst whether retaining gateway detail justified its extra predictors in this bounded exercise. It does not establish that geography never matters in other markets or specifications.

## What is being forecast

The target is monthly loaded-import TEUs summed across Los Angeles, Long Beach, New York/New Jersey and Savannah. Los Angeles and Long Beach form one physical San Pedro Bay gateway; the other two reporting systems form the East Coast gateways. A TEU is a standardized container-size unit. It is not a vessel, ton, dollar amount, individual box count, or measure of consumer demand. The composite is deliberately narrower than total U.S. imports.

Official BTS observations provide 336 port-month records over 84 calendar months from January 2019 through December 2025. Definitions were checked against the exact loaded-import series rather than a similarly named total-TEU catalog. Cross-checks cover 108 authority-month comparisons, with 106 within one TEU. Two Savannah differences are retained rather than forced to match: June 2023 differs by 12 TEUs and December 2020 by six. The BTS vintage remains consistent throughout the target. Long Beach's direct authority request returned an access restriction; it was not bypassed.

The PortWatch panel contains 7,671 gateway-day records: 2,557 dates across three resolved facilities. The shared Los Angeles/Long Beach PortWatch identifier is used once. Container-specific calls are the predictors; estimated tons never become official TEU labels. The API's counts, unique identifiers and source-edit state were reconciled before and after extraction. Nine gateway-days across three documented provider blackout dates are marked missing, even where a source number might otherwise look usable. Missing observations do not become zero traffic.

## Frozen comparison and information set

The research question is whether gateway-level disaggregation adds information beyond an aggregate activity series observed at the same cutoff. It is not an experiment identifying the causal effect of distance, an estimate of network spillovers, or proof that a mapping library creates predictive value. The candidate also has more regressors: eight instead of four for aggregate shipping. Regularization and a transparent operational baseline address this difference without pretending to eliminate model-selection uncertainty.

2019 supplies warm-up history. Development uses 2020–2022, model selection uses twelve monthly origins in 2023, and the untouched performance evaluation uses the twenty-four origins in 2024–2025. 2026 observations are excluded. Every origin is the end of day 21 UTC, represented internally by the exclusive start of day 22. Under the primary seven-day assumed data lag, complete daily observations through day 14 are admissible. Historical observation dates are not themselves proof of release availability.

Shipping features compare trailing seven- and twenty-eight-day call totals with matched prior-year windows using a fixed log-ratio pseudocount. February 29 maps to February 28 for the prior-year endpoint, with the same window length. Aggregate features sum calls before transformation; the candidate retains each gateway. Two history features use the latest released target growth and the mean of the latest three released growth values. Both numerator and seasonal denominator must be available. Current-month labels cannot enter fitting.

The target model predicts log year-over-year growth and reconstructs TEUs from the released prior-year seasonal base. Standardization is fitted only on each origin's training rows. Ridge penalties are restricted to 1, 10 and 100, selected using validation WAPE; ties favor stronger regularization. There is no test-tuned feature search, inverse-transform bias correction or output clipping. Expanding coefficient refits are allowed during the test, but selected penalties and benchmark identities remain frozen.

The fifth model converts calls into TEUs using each gateway's training-only median monthly TEU-per-call ratio and projects the latest observed twenty-eight-day call rate across the forecast month's day count. This simple model assumes a stable conversion and rate. It may fail when vessel size, cargo composition or within-month timing changes, but its operational meaning is easier to inspect than a flexible regression. The strongest noncandidate model was **Calls-to-TEU benchmark**, chosen before test scores were opened.

## Results on a common policy

All mandatory models forecast the same twenty-four test months. If the shared activity-feature contract is incomplete, the common policy uses the prior-year same-month target. The primary candidate's fallback rate is 12.5%, and its valid-source-feature rate is 87.5%. Full-policy performance is primary; common-valid-feature scores are retained separately. A model cannot improve its headline by skipping difficult months.

| Model | WAPE | MAE · TEUs | RMSE · TEUs | Bias · TEUs | YoY direction |
| --- | --- | --- | --- | --- | --- |
| Last year's month | 11.23% | 162,177 | 185,904 | -115,338 | 0.0% |
| Released target history | 8.92% | 128,852 | 164,547 | -9,778 | 66.7% |
| Aggregate shipping | 11.89% | 171,759 | 197,700 | +74,874 | 62.5% |
| Geographic shipping | 11.21% | 161,994 | 182,841 | +90,026 | 79.2% |
| Calls-to-TEU benchmark | 7.34% | 106,077 | 127,723 | -46,479 | 66.7% |

WAPE divides total absolute TEU error by total realized TEUs. MAE and RMSE preserve the target's units; bias is prediction minus outcome. Directional accuracy asks whether predicted and realized year-over-year growth have the same sign, not whether a trading position would make money. No per-gateway regression scores are fabricated from composite-only predictions. Changed-target diagnostics remove a gateway explicitly and are not extra independent replications of the primary target.

## Uncertainty and robustness

| Comparator | Relative lift | 3-month block 95% interval | 6-month block 95% interval |
| --- | --- | --- | --- |
| Aggregate shipping | +5.69% | [-23.28%, +30.93%] | [-28.18%, +25.22%] |
| Calls-to-TEU benchmark | -52.71% | [-117.87%, -21.01%] | [-115.42%, -37.02%] |

Each interval uses 10,000 paired moving-block bootstrap replicates. Three- and six-month contiguous calendar blocks preserve some serial dependence, and the same sampled months are used across models. Missing-target markers remain on the calendar. The twenty-four test months, not thousands of daily inputs or several ports, are the independent forecast periods. These are intervals for comparative average error, not prediction intervals for a new month. No forecast band is displayed because a separately validated band was not part of the core model.

The preselected practical threshold is five percent relative improvement versus both aggregate shipping and the validation-selected strongest baseline, with both block-length intervals above zero and at least twenty available target months. That hurdle is a project decision rule, not a universal economic standard. Even a statistical pass would remain qualified by reporting-lag, revision and regime uncertainty. Robustness results are all retained; an attractive secondary slice cannot replace an unfavorable primary comparison.

| Shipping lag | Unknown target lag | Geography WAPE | Aggregate WAPE | Selected baseline WAPE |
| --- | --- | --- | --- | --- |
| 7 | 60 | 11.21% | 11.89% | 7.34% |
| 7 | 90 | 11.34% | 12.37% | 7.30% |
| 14 | 60 | 10.00% | 9.07% | 6.25% |
| 14 | 90 | 10.52% | 9.26% | 6.29% |
| 28 | 60 | 10.36% | 10.04% | 7.81% |
| 28 | 90 | 11.12% | 9.33% | 7.92% |

Each lag/release-lag specification was selected using the same 2023-only procedure before any final test score. Longer shipping delays can remove current-month observations entirely; trailing windows are still measured, never zero-filled. The sixty- and ninety-day target-release lags are assumptions for undated releases, not claims about historical authority schedules. All 336 source target rows lacked verified first-release timestamps, so the denominator for a verified days-before-official-release claim is zero.

Year-by-year scores, gateway concentration and all three leave-one-gateway-out targets are stored in the results artifact. Excluding the ambiguous NYNJ facility perimeter uses the same explicit changed-target experiment; it does not allocate uncertain terminals arbitrarily. No optional estimated-tonnage feature was added, so its ablation is not applicable. A deliberately future-shifted twenty-eight-day feature is saved only as a forbidden diagnostic, never as an admissible forecasting model.

## Busy port or bottleneck: a separate measurement layer

The current measurement export contains 366 distinct source dates, 1,098 gateway-day rows, spanning 2024-01-01 to 2024-12-31. The separate acquisition manifest establishes which national partitions were actually acquired; rows alone do not prove complete vessel detection. The raw-point study is confined to the documented 2024 NOAA archive. It does not create a long 2019–2025 congestion history. Cargo broadcast codes identify a cargo-vessel proxy, not independently confirmed containerships. Transmission density is not vessel activity, and stationary presence is not verified import delay.

The engine separates approach, transit, anchorage candidates, berth candidates and unknown gaps using attributed boundaries, speed, persistence and continuity. Local projected coordinate systems are used for meter buffers; public coordinates remain WGS84. Shared San Pedro anchorage is counted once. Exact duplicate pings are removed, conflicting positions are flagged, implausible jumps are not filled, and state carries across midnight. Long missing intervals become unknown time rather than confirmed dwell.

Anchorage hours and elapsed age of active candidates are lower-bound observations with coverage and censoring metadata. A vessel later reaching a container berth can support retrospective interpretation but cannot rewrite what was observable at an earlier cutoff. The optional friction summary uses two equally weighted robust log-transformed components, standardized on prior valid days only. It is not seasonal adjustment. A zero detected queue is distinguished from unknown coverage; it does not prove that no real queue existed.

Sixty stratified actual trajectories are audited by agents, not maritime experts or independent human reviewers. The geometry, speed and gap sensitivity tables remain part of the result. The pilot showed substantial sensitivity to approximate berth corridors; official anchorage polygons are more defensible than inferred quay buffers. The study therefore demonstrates a reproducible measurement process, not validated delay ground truth. Limited BTS operational waiting-stock data provide a definition-aware consistency check; shared AIS origins and differing vessel classes prevent treating that comparison as independent truth.

The matched operational comparison does not establish agreement: san pedro bay: 3.29 mean modeled candidates versus 0.90 reported stock across 49 valid date pairs; savannah: 0.00 mean modeled candidates versus 4.32 reported stock across 50 valid date pairs. Population, geographic footprint and observation-clock differences preclude a like-for-like accuracy score. In particular, Savannah's zero modeled stock alongside positive reported stock reinforces the bounded offshore-coverage limitation; it is not evidence of no queue. Source: `artifacts/audit/geo_operational_summary.json`.

## Analyst use and a dated decision example

The first valid test-origin example is chosen chronologically, not for an attractive story: **2024-03**. Geographic shipping predicted **1,396,631 TEUs**, aggregate shipping **1,295,840**, and the subsequently recorded target was **1,246,396**. Its information cutoff was **2024-03-15T00:00:00+00:00**, with latest admitted target-growth observation **2023-12**. The admissible twenty-eight-day window contained 413 container calls, versus 379 in the matched prior-year window (+9.0%). Retrospective NOAA reconstruction on 2024-03-14 gives san pedro bay: 4 observed candidates, 74.4 observed anchorage-candidate hours; new york new jersey: 1 observed candidates, 41.3 observed anchorage-candidate hours; savannah: 0 observed candidates, 0.0 observed anchorage-candidate hours. These bounded observations do not establish a common congestion shock; Savannah's known offshore coverage limitation prevents treating a low count as no queue. The archive was not verified available at the forecast origin. The precomputed record exposes the exact inputs, training months and fitted parameters so the disagreement can be inspected rather than narrated from a chart alone.

An analyst could use that disagreement to ask whether inventory arrivals are geographically concentrated, whether a disruption is shifting gateway activity, or whether official reporting timing obscures a physical change. The separately dated queue-candidate exhibit can help inspect a congestion explanation, but it is retrospective and cannot be smuggled into the earlier information set. A security-level thesis would additionally require product mix, inventory disclosures, importer exposure, shipment utilization and economically justified company mapping. Headquarters proximity supplies none of those facts.

## Reproducibility, permissions and conclusion

The final protocol, exact source manifests, crosswalk, research-critical code and validation selections were hashed before test evaluation. Pre-test software-hardening reruns produced exactly identical validation grids, selections and prediction records across all nine specifications. Immutable test files have per-experiment receipts; interrupted runs verify hashes instead of overwriting results. Future-data append checks leave both fallback and valid-origin forecasts unchanged, including fitted parameters. Synthetic fixtures live only in the tests and never supply empirical charts.

The local package, tests, executed notebooks, source/license registry and reviewed export bundle make the result inspectable. PortWatch is attributed to Kpler, the UN Global Platform and IMF PortWatch; its access is not a license to redistribute raw proprietary AIS. NOAA product-specific terms and BTS government-data terms are recorded separately. This GitHub repository publishes the reviewed research code and aggregate evidence. No portfolio website deployment, paid service, recurring job or LinkedIn post is part of this release. A prospective append-only forecast command exists, but no live forecast is claimed before a genuine future snapshot is saved.

The defensible contribution is the controlled comparison, the measurement audit and an honest availability boundary. Calls-to-TEU benchmark beat the geography-aware model; the gain over aggregate shipping was uncertain. The companion map explains physical activity with visible uncertainty, while the forecast evidence answers the narrower statistical question without converting an interesting port story into invented investment alpha.

## Evidence links

- [Frozen metrics](../artifacts/metrics/locked_results.json) and [robustness](../artifacts/metrics/robustness.json)
- [Protocol lock](../artifacts/protocol_lock.json), [availability audit](AVAILABILITY_AUDIT.md), [literature review](LITERATURE_REVIEW.md)
- [Data access audit](DATA_ACCESS_AUDIT.md), [geospatial method](GEOSPATIAL_METHOD.md), [data licenses](../DATA_LICENSES.md)
