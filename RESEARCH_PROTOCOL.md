# Initial protocol — before source exploration

## 4. Frozen scope and research hypotheses

### Geography: three gateways, four administrative port labels

| Gateway ID | Definition | Treatment |
|---|---|---|
| `san_pedro_bay` | Los Angeles plus Long Beach | Add their non-overlapping official loaded-import TEUs. Treat shared anchorage as one physical gateway. Preserve terminal/port detail internally. |
| `new_york_new_jersey` | Port of New York and New Jersey reporting system | Verify which PortWatch facilities and geofences belong to the official reporting perimeter. |
| `savannah` | Port of Savannah | Exclude other Georgia Ports Authority locations unless the official target explicitly includes them. |

These gateways are selected now for a bounded West/East Coast comparison, not because a later return or forecast result looks favorable. Do not substitute ports after viewing test performance.

### Primary hypothesis H1

A geography-aware model of shipping activity reduces error in a composite monthly loaded-import TEU nowcast relative to a model using the same information cutoff but only aggregate shipping activity.

### Secondary measurement question M1

A transparent, coverage-aware AIS state model can produce interpretable port-activity and queue-candidate measures whose trajectories are consistent with observed movement and available external operational aggregates.

M1 is not a claim that every stationary vessel is delayed, that the algorithm measures the cause of delay, or that its inferred labels are independently verified ground truth.

### Primary target

For calendar month `m`:

`Y[m] = loaded_import_teu[Los Angeles,m] + loaded_import_teu[Long Beach,m] + loaded_import_teu[NYNJ,m] + loaded_import_teu[Savannah,m]`

One TEU is a container-size unit, not a ship, ton, dollar, or individual container count. Use the target's documented definition and calendar basis. Do not mix loaded imports with total TEUs, empties, exports, annual fiscal totals, or container lifts.

The target is **the selected-gateway composite**, not total U.S. imports, total seaborne trade, consumer demand, or GDP. Report per-gateway results as diagnostics, not as extra independent replications.

### Time scope

- Source collection for the forecasting panel: 2019-01-01 through 2025-12-31.
- 2019: warm-up for year-over-year features and seasonal benchmarks.
- Development: 2020–2022, subject to label availability at each origin.
- Validation and model selection: the 12 monthly origins in 2023.
- Locked temporal test: the 24 monthly origins in 2024–2025.
- 2026: excluded from primary selection and evaluation. A later explicitly labeled extension may use it without replacing the primary result.
- Raw geospatial measurement layer: 2024-01-01 through 2024-12-31, after a small acquisition pilot.

This is a **retrospective, protocol-locked temporal evaluation**, not a prediction registered in 2023. Document all historical exposure by the user or agents. No protocol can erase already observed historical knowledge.

---


## 7. Configuration to implement

Implement validated loading of the following configuration. Resolve null paths during preflight, then write the resolved config and its SHA-256. Any change to research-critical fields after lock requires a separately labeled amendment.

```yaml
project:
  name: supply-chain-shadow-index
  title: Ports Before Reports
  protocol_version: "1.0"
  research_checked: "2026-10-15"
  seed: 20261015
  workspace_root: null
  website_repo: null
  allow_remote_writes: false
  allow_spending: false

scope:
  gateways: [san_pedro_bay, new_york_new_jersey, savannah]
  target: selected_gateway_loaded_import_teu
  flow_start: "2019-01-01"
  flow_end: "2025-12-31"
  ais_start: "2024-01-01"
  ais_end: "2024-12-31"
  ais_pilot_days: 14
  forecast_day: 21
  forecast_clock: end_of_day_utc
  primary_flow_lag_days: 7
  sensitivity_flow_lag_days: [14, 28]
  unknown_target_release_lag_days: 60
  target_release_lag_sensitivity_days: 90
  availability_mode: current_vintage_pseudo_realtime

research:
  warmup_year: 2019
  development_years: [2020, 2021, 2022]
  validation_years: [2023]
  locked_test_years: [2024, 2025]
  excluded_extension_years: [2026]
  minimum_training_months: 24
  minimum_test_target_months: 20
  primary_metric: composite_teu_wape
  primary_comparison: geography_ridge_vs_aggregate_ridge
  ridge_alphas: [1.0, 10.0, 100.0]
  shipping_windows_days: [7, 28]
  bootstrap_replicates: 10000
  confidence_level: 0.95
  bootstrap_block_months: [3, 6]
  practical_lift_threshold: 0.05
  max_core_feature_columns: 12
  mandatory_models:
    - seasonal_naive
    - released_target_ridge
    - aggregate_activity_ridge
    - geography_ridge
    - simple_calls_to_teu

geospatial:
  publish_crs: "EPSG:4326"
  stationary_speed_knots: 1.0
  minimum_state_duration_minutes: 30
  maximum_interpolation_gap_minutes: 30
  geofence_buffer_sensitivity_meters: [0, 100, 250]
  low_speed_sensitivity_knots: [0.5, 1.5]
  gap_sensitivity_minutes: [15, 60]
  trailing_standardization_days: 90
  minimum_standardization_days: 30
  retrospective_queue_matching_allowed_in_predictors: false

resources:
  max_threads: 8
  max_memory_gib: 48
  project_disk_cap_gib: 80
  raw_cache_cap_gib: 16
  minimum_free_disk_gib: 20
  network_transfer_cap_gib: 200
  provider_concurrency: 2
  default_requests_per_second: 1
  retries: 5

publishing:
  integrate_existing_portfolio: true
  deploy: false
  create_recurring_job: false
  expose_vessel_identifiers: false
  publish_raw_vendor_data: false
  synthetic_fixtures_separate: true
  require_claims_ledger: true
```

Geospatial thresholds are initial engineering assumptions, not universal maritime definitions. Revise them only during the documented measurement pilot, not to maximize forecast performance. Freeze the final choices and retain the initial settings in the decision log.

---

## 8. Data contracts, provenance, and availability

Implement explicit schema validation. At minimum, create the following logical tables.

### `source_snapshots`

`source_id, snapshot_id, retrieved_at_utc, source_published_at_utc, first_seen_at_utc, source_url, resolved_url, etag, last_modified, sha256, byte_count, row_count, schema_hash, terms_url, redistribution_status, vintage_notes`

Unknown dates are null. A retrieval timestamp is not a historical first-publication date. HTTP `Last-Modified` is evidence about a file, not necessarily about individual observations.

### `gateway_crosswalk`

`gateway_id, source_id, source_port_id, official_target_label, latitude, longitude, reporting_scope, valid_from, valid_to, geometry_version, mapping_evidence_url, confidence, reviewer_type`

Resolve by official name, coordinates, facility scope, and port documentation together. Never rely only on fuzzy name matching. Coordinates are for location and matching, not evidence of import volume. Preserve aliases and exclusions.

### `portwatch_daily`

`source_port_id, gateway_id, observation_date, observation_interval_end_utc, vessel_category, port_calls, incoming_volume, incoming_volume_unit, outgoing_volume, snapshot_id, source_published_at_utc, availability_basis, quality_flags`

Inspect actual fields and map them; these are canonical internal names. Container-specific calls are preferred for the primary experiment. Aggregate cargo calls or mixed-vessel tons are not silently equivalent substitutes. If container-specific calls are unavailable, amend the scope before outcomes are examined and label the limitation, or classify the primary study as blocked.

### `official_teu_monthly`

`official_port_id, gateway_id, month, direction, load_status, teu, reporting_calendar, first_release_at_utc, revision_at_utc, vintage_id, source_url, snapshot_id, quality_flags`

Preserve original and revised observations separately. Sum LA and LB only after confirming definitions. Check monthly totals against annual totals where comparable; explain rounding or revisions rather than forcing equality.

### `ais_points` and `ais_episodes`

Points include vessel identifier, observation timestamp, position, speed, course, documented vessel category, source partition, geometry version, and quality flags.

Episodes include start/end observation bounds, zone, state, duration observed, censored-left/right flags, gap flags, elapsed duration as of cutoff, confidence, and source lineage. **Do not store a future-completed waiting time in an as-of feature record.**

### `gateway_daily_features`

`gateway_id, observation_date, feature_name, value, unit, coverage_measure, available_at_utc, availability_basis, observation_cutoff_utc, snapshot_id, method_version, quality_flags`

### `forecast_records`

`experiment_id, model_id, target_month, forecast_origin_utc, feature_cutoff_utc, training_label_cutoff, feature_snapshot_ids, protocol_sha256, train_end, model_parameters, prediction_teu, interval_lower, interval_upper, fallback_used, generated_at_utc`

### `claims`

`claim_id, proposed_text, claim_type, supporting_artifact, statistic_definition, evaluation_period, denominator, availability_status, limitations, approval_status`

### Availability modes

1. **Verified point-in-time:** An archived vintage or first-seen record proves the data used existed by the historical origin.
2. **Current-vintage pseudo-real-time:** Historical event data are evaluated with a stated lag, but the original release vintage is not established. This is the default research mode.
3. **Retrospective descriptive:** The feature reconstructs past physical behavior using archive data, without a contemporaneous availability claim.
4. **Prospective shadow forecast:** The program saves a genuinely new forecast and immutable source snapshot before the outcome is known. Infrastructure must exist, but no recurring job is enabled by default.

Store `verified_available_at_utc` separately from `assumed_available_at_utc`. The execution mode selects the admissible information set without overwriting the factual availability record. If the only verified timestamp is retrieval in 2026, the same data may be used for a clearly labeled pseudo-real-time experiment but cannot appear in a verified 2024 information set.

A seven-day lag alone never upgrades mode 2 into mode 1. If a source's methodology or calibration changed after the test period, record that even if the observations are dated earlier.

For pseudo-real-time target availability, use a known first release when verified; otherwise assume 60 calendar days after month-end and repeat at 90 days. These are modeling assumptions, not asserted historical schedules. The target for the current forecast month must never enter training.

---

## 9. Geospatial measurement pipeline

### 9.1 Geometry and port boundaries

Obtain authoritative or clearly attributed port/terminal/anchorage boundaries where available. Digitize defensible geometry from authoritative reference material when necessary, documenting the source, date, and interpretation. Save GeoJSON/GeoParquet with versioned metadata and a visual boundary audit.

Differentiate:

- outer approach area;
- candidate anchorage/holding areas;
- container-terminal berth areas;
- other commercial berths;
- transit channels;
- areas outside the modeled gateway.

A broad bounding box is an acquisition filter, not a harbor or anchorage definition. Do not count every slow vessel inside it as queueing. Handle shared San Pedro Bay anchorage without allocating the same vessel-hour to both LA and LB. Vessels may berth at multiple terminals; gateway entries and terminal calls are different events.

Use an appropriate local projected CRS for buffers and distances, chosen and checked at execution. Publish WGS84 coordinates. Inspect CRS metadata for each source; related NOAA point and track products need not use identical formats or coordinate reference systems. Never calculate a 100-meter buffer directly in longitude/latitude degrees.

### 9.2 Cleaning and continuity

- Parse timestamps as timezone-aware UTC and sort by vessel and time across file boundaries.
- Keep overnight episode state; do not reset a voyage at midnight or a monthly file boundary.
- Deduplicate exact retransmissions; flag conflicting same-vessel/same-time positions instead of averaging impossible locations.
- Validate latitude, longitude, speed, course, dimensions, and documented sentinel values.
- Flag impossible jumps and identifier collisions; do not invent the missing track.
- AIS broadcast cargo classification is broader than confirmed containership identity. Validate source-specific codes. Use “cargo-vessel proxy” when identity or classification cannot support “containership.”
- Never infer loaded TEUs, exact cargo weight, or vessel capacity from dimensions alone.
- Exclude recreational, fishing, tug, and other irrelevant traffic from freight features when classification supports it. Preserve unknown classifications as unknown.
- Preserve source sampling changes and coverage diagnostics. More transmissions from the same vessel are not automatically more activity.

### 9.3 State machine

Implement an auditable state model, not an opaque clustering score:

```text
OUTSIDE / APPROACH
    -> TRANSIT
    -> ANCHORAGE_CANDIDATE
    -> BERTH_CANDIDATE
    -> DEPARTED

At any point:
    -> UNKNOWN_GAP when observations are insufficient
```

Zone, speed, persistence, and trajectory continuity jointly determine a state. Use the frozen pilot thresholds in configuration. Use hysteresis or a minimum persistence rule to prevent repeated entry/exit events caused by boundary jitter.

For intervals between two valid pings within the maximum allowed gap, allocate observed time conservatively. Split intervals at day boundaries. Interpolate only under an explicit bounded rule, record interpolation, and test sensitivity. Gaps longer than the threshold are unobserved intervals, not extended confirmed anchoring.

A vessel stationary in an anchorage may be waiting, resting, staging, or doing something else. Without additional evidence, label it a **queue candidate**, not a proven delayed import vessel.

A later visit to a container berth may improve retrospective event interpretation. It cannot retroactively determine whether that vessel belonged in an earlier as-of queue feature. Keep retrospective linkage in a separate QA table.

### 9.4 Daily measures

Compute, with coverage and censoring metadata:

- distinct observed eligible vessel arrivals;
- observed berth-candidate vessel-hours;
- observed anchorage-candidate vessel-hours;
- queue-candidate stock at the end of a fully observed day;
- median elapsed time of active queue candidates, using only observations through the cutoff;
- completed berth-stay durations whose departures are already observed;
- number and fraction of censored episodes;
- observed ping continuity, invalid-record rate, and source-partition completeness.

No observed queue on a sufficiently observed day can be zero. A missing source day or unknown coverage is not zero. If no queue exists, active-queue median age can be defined as zero only alongside a verified zero-queue indicator; otherwise it is undefined.

Do not scale a tiny number of observed hours to an entire day and call it a measured queue. Publish coverage-limited lower bounds or mark the day unreliable. File completeness and ping continuity are coverage proxies, not proof that every vessel was observable. Where receiver uptime or detection probability is unknown, say so; do not claim a percentage of all ships observed merely from the fraction of source days downloaded.

### 9.5 Index construction

Keep two axes rather than netting activity and friction into a misleading single number:

- **Flow:** shipping-activity change relative to comparable past windows, using the long PortWatch panel.
- **Friction:** a transparent combination of observed anchorage-candidate hours and active-candidate elapsed age, available only where raw measurement supports it.

For the optional friction summary, use equal weights of the two robust standardized `log1p` components. Estimate location and scale from the previous 90 valid days, excluding the current day; require at least 30. Record a deterministic fallback when the median absolute deviation is zero. Retain raw units beside the index. Display clipping must not alter research data.

Do not claim seasonal adjustment from a short rolling baseline. Never backfill 2019–2023 friction with a model trained on 2024 and present it as observed historical congestion.

### 9.6 Measurement audit

Review at least 60 stratified trajectory examples across the three gateways, covering anchorage, berth, transit, boundary jitter, missing intervals, and left/right censoring. Produce map panels and a traceable audit table. State whether review was agent-assisted, manually performed by the user, or independently performed; do not invent expert validation.

Compare appropriate aggregates to the separately documented BTS operational series where periods and definitions overlap. Shared AIS origins mean this is a consistency check, not fully independent ground truth. Explain differences in vessel classes, anchorage versus berth, completed versus active episodes, and mean versus median.

Required outputs: `docs/GEOSPATIAL_METHOD.md`, geometry provenance, trajectory audit table, coverage calendar, sensitivity table, and actual-data maps.

---

## 10. Forecast design and information sets

### 10.1 Forecast origin

Produce one forecast per month, **as of the end of calendar day 21 UTC**, for that month's final composite loaded-import TEUs. Represent the origin internally as the start of day 22 UTC with an exclusive boundary.

For the primary seven-day modeled lag, only complete observation intervals ending on or before `origin - 7 days` may enter the forecast. This typically admits observations through the end of day 14. Use interval boundaries consistently; test off-by-one and leap-year behavior.

Repeat the identical frozen pipeline with 14- and 28-day shipping lags. A long lag may leave no current-month observations; trailing windows still exist. Never zero-fill the unobserved current month.

The public copy must say “historical nowcast under an assumed reporting lag” unless actual release-vintage evidence supports a stronger claim. Compute days-before-official-release only for months with verified release dates and label that denominator.

### 10.2 Feature definitions

For each gateway, use container-specific port calls aggregated over trailing 7- and 28-day windows ending at the admissible cutoff. Construct matched prior-year windows with a documented calendar rule, including February 29 handling.

A primary shipping feature is:

`log((1 + calls_current_window) / (1 + calls_matched_prior_year_window))`

The fixed pseudocount handles genuine zero calls, not missing observations. Do not introduce dozens of windows, ship categories, weather features, news terms, or flexible spatial embeddings.

The same transformations applied to summed gateway calls create aggregate-only features. Geography-aware features retain the gateway identity. This is an information-preservation comparison, not proof that a GIS library itself causes accuracy gains. It tests gateway-level disaggregation, not a causal effect of physical distance or a spatial-neighborhood model. The candidate also has more predictors; describe that difference, retain regularization and the strong operational baseline, and do not attribute every gain to geography alone.

Use at most two released-target features: the latest available year-over-year target growth and the mean of the latest three available growth observations. Record staleness and verify comparability. Avoid using a convenient `t-1` value before its release.

Model the target as:

`growth[m] = log(Y[m] / Y[m-12])`

Reconstruct TEUs with the known seasonal base. If a bias correction is used for inverse transformation, estimate it only from permitted training residuals, apply it identically across comparable models, and freeze the choice before test. Record any lower-bound clipping. Do not use test outcomes to set output bounds.

### 10.3 Missingness policy

Validate complete, comparable gateway windows. Missing days do not count as no traffic. Do not allow a model to improve its score merely by abstaining in difficult months.

Before outcome inspection, define a common source-coverage mask for the mandatory models. For an origin failing the core activity-feature contract, use the seasonal-naive forecast as the shared policy fallback and record it. Report both full-policy performance and common-valid-feature performance, clearly identifying the primary table.

A missing official target cannot be fabricated or replaced with PortWatch's own estimate. Fewer than 20 available test months blocks a supported-predictive headline. Report the actual sample and a descriptive result instead. Port-specific counts do not inflate the number of independent calendar periods.

### 10.4 Mandatory baselines

| Model | Information | Purpose |
|---|---|---|
| `seasonal_naive` | Last year's same-month official composite | Hard-to-misinterpret seasonal benchmark |
| `released_target_ridge` | Only released-target features | Tests whether shipping adds information beyond target history |
| `aggregate_activity_ridge` | Released-target features plus summed shipping features | Primary geography-blind comparator |
| `geography_ridge` | Released-target features plus separate gateway shipping features | Primary candidate |
| `simple_calls_to_teu` | Training-only gateway TEU/call conversion plus simple call projection | Practical transparent operational benchmark |

For `simple_calls_to_teu`, estimate each gateway's median monthly TEU-per-container-call ratio from admissible completed training months. Project the current month's calls from the latest observed 28-day rate times the month's day count, then multiply by the ratio and sum. This intentionally simple baseline shares the same observation cutoff. Document its simplifying assumption; do not tune it on the test period.

The headline benchmark is the strongest noncandidate baseline selected on 2023 validation, not whichever model performs worst on the test. Always show the direct `geography_ridge` versus `aggregate_activity_ridge` comparison, even when another benchmark wins.

### 10.5 Fitting and selection

Use a scikit-learn pipeline with training-only standardization and Ridge. The only core regularization grid is `[1, 10, 100]`. Maximum 12 feature columns, excluding fixed metadata. Avoid additional feature search [S24].

Run expanding monthly validation origins in 2023. At each origin, use only training labels available under the specified availability mode, with a minimum of 24 training months. Select each model's regularization on aggregate validation WAPE; break ties toward stronger regularization and then fewer features.

Save the initial protocol before any data exploration. Measurement work on 2024 trajectories must not change the forecasting target, gateway selection, model family, feature windows, or scoring rules. Document this measurement-related exposure.

Freeze the entire protocol, data manifests, crosswalk, transforms, model grid, chosen hyperparameters, benchmark, and reporting rules before opening the final test results. A research auditor may check schemas and completeness, but must not feed test-period performance or attractive episodes to the model-design agent.

During the 2024–2025 test, permit expanding-window coefficient refits using newly available historical labels, as specified in advance. Do not retune hyperparameters, change features, replace ports, or change the selected benchmark. Each prediction must be reconstructible from its exact information set.

The basic program must enforce as-of joins itself. A chronological split alone is not a substitute for publication-lag logic or historical-vintage evidence.

---

## 11. Metrics, uncertainty, ablations, and claim gates

### Primary metric

For the fixed eligible test target months:

`WAPE(model) = sum(abs(Y - prediction_model)) / sum(Y)`

`relative_lift = 1 - WAPE(candidate) / WAPE(comparator)`

A positive lift means less error. Report WAPE as a percentage and relative lift separately; do not confuse percentage-point error reduction with percentage relative improvement.

Required supporting metrics: MAE in TEUs, RMSE in TEUs, bias, directional accuracy of year-over-year growth, source-coverage rate, fallback rate, and the same diagnostics by gateway where a gateway forecast exists. Do not manufacture gateway forecasts from a composite-only regression; fit a separately labeled diagnostic model or omit that unsupported breakdown.

### Uncertainty

Use paired moving-block bootstrap resampling of the monthly forecast/outcome records, with 10,000 replicates and both 3-month and 6-month block lengths. Recompute WAPE and relative lift within each replicate. Resample the same months for all models and gateways. Do not treat daily source observations or different ports as independent test forecasts.

Use the 2.5th and 97.5th percentiles for a nominal 95% interval. Draw contiguous calendar-month blocks, retaining missing-target markers rather than joining distant months into artificial adjacent blocks; evaluate only valid paired outcomes and report their count.

Report both intervals, not whichever is more favorable. Explain that 24 test months provide limited information and bootstrap intervals do not remove model-selection, revision, or regime uncertainty. An interval for average model performance is not a prediction interval for a new month.

A displayed forecast band must be built from trailing admissible forecast residuals using a documented method, or remain absent. Label an empirical band as such and assess coverage; do not claim guaranteed 90% coverage under changing market conditions.

### Required ablations and stress checks

1. Aggregate activity versus geographically disaggregated activity: H1.
2. Candidate versus the validation-selected strongest baseline.
3. Seven-, fourteen-, and twenty-eight-day assumed input delays.
4. Sixty- versus ninety-day assumed target release lag for records lacking verified dates.
5. With/without any optional estimated-tonnage feature; this feature is not in the primary specification.
6. All 24 test origins together, each test year separately, and gateway concentration/leave-one-gateway-out diagnostics with explicitly changed target scope.
7. A sensitivity in which crosswalk ambiguities are excluded rather than arbitrarily allocated.
8. Frozen geometry/speed/gap sensitivity for the measurement layer, reported separately from H1.
9. Future-data append test: modifying data after an origin must not change that origin's forecast.
10. A time-shift placebo implemented only as a diagnostic. Any deliberately future-shifted feature must be clearly marked forbidden in the production path.

Do not call the list above ten independent successful hypotheses. Predeclare the comparisons and publish all results. Do not search for a favorable event window, stock, port, feature, or date range after H1 fails.

### Claim status rules

| Status | Conditions | Allowed headline |
|---|---|---|
| `HISTORICAL_LIFT_SUPPORTED` | Candidate beats both the aggregate comparator and validation-selected best baseline; relative lift at least 5%; both bootstrap interval variants above zero; no critical leakage failure; at least 20 test months; caveats retained | “Geographic detail reduced historical forecast error by X% in the locked test.” |
| `PROMISING_BUT_UNCERTAIN` | Positive point estimate but the practical threshold, interval, robustness, or sample condition fails | “Geographic detail showed a tentative improvement; uncertainty remains.” |
| `NO_INCREMENTAL_LIFT` | Geography fails to improve the locked primary comparison | “Aggregate shipping activity was sufficient in this test,” or “Geographic detail did not improve the forecast.” |
| `MEASUREMENT_ONLY` | Forecasting validity is blocked but real-data geospatial measurement is completed | “A reproducible port-activity measurement study,” with the missing forecast evidence prominent |
| `REAL_DATA_BLOCKED` | Required source access or definitions cannot be resolved | No empirical success claim; deliver implemented code, evidence of the blocker, and completed independent work |

The 5% hurdle is a preselected project decision rule, not a universally established economic threshold. Longer lag tests may undermine practical usefulness even when the primary historical comparison passes; this must be visible in the headline qualification.

**No state automatically permits “alpha,” “profitable,” “causal,” “live,” “production-grade,” “institutional adoption,” or “proven trading advantage.”**

---


## Engineering choices frozen before outcomes

- No inverse-log bias correction; forecasts are seasonal base times exp(predicted log growth).
- Prior-year window ends at the same calendar month/day (February 29 clamps to February 28), with the same trailing window length.
- Complete daily source windows are required; missing intervals are not zeros.
- Common activity-source failure triggers seasonal-naive fallback for all models in the primary full-policy table.
- No forecast uncertainty bands in v1; performance bootstrap intervals are not prediction bands.
- No optional tonnage predictors in the core experiment; tonnage ablation is not applicable unless an amendment precedes test.
- Gatekeeping applies to both required comparisons and both bootstrap block lengths.
- Initial protocol is retrospective and locked on 2026-10-15, not preregistered in 2023. User/agents have general historical knowledge; no project test forecasts or errors have been examined.
- Measurement-pilot exposure to 2024 positions is separately logged and may not change forecast design.
