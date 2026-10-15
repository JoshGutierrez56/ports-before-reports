# Data dictionary

| Table / artifact | Key / grain | Units and essential semantics |
| --- | --- | --- |
| source_snapshot_catalog.json | source_id / snapshot_id | SHA256, actual retained bytes, original/resolved URLs, retrieval UTC, null unknown publication dates, schema and licensing |
| gateway_crosswalk.csv | source port / gateway / version | Combined LA-LB once; NYNJ reporting-perimeter ambiguity explicit; Savannah excludes other Georgia ports |
| portwatch_daily.parquet | source_port_id × observation_date | Container-specific calls; incoming/outgoing estimated volumes retain source units, never TEUs; nine documented blackout port-days null |
| official_teu_monthly.parquet | official_port_id × month × vintage | Loaded-import TEUs, calendar month, original source URL, first_release_at_utc null when unverified, revisions never double-counted |
| raw_cropped/*.parquet | source partition × vessel × timestamp | UTC, WGS84 lon/lat, speed knots, source broadcast type; identifiers private/local |
| geo_episodes.parquet | vessel / gateway / episode bounds | Observed duration, candidate state, censoring and gaps; retrospective linkage separate from as-of elapsed duration |
| geo_daily_features.csv | gateway × UTC date | Candidate vessel-hours, active elapsed age, arrivals, coverage and null/zero distinctions; consult GEOSPATIAL_METHOD for exact fields |
| predictions/*.json | experiment × target_month × model | TEU prediction/outcome, exclusive origin/cutoff, admitted training months, scaler/coefficients, model parameters, snapshot hashes, fallback reason |
| metrics/locked_results.json | experiment × model/comparator | WAPE and relative lift stored as fractions, MAE/RMSE/bias inTEUs, direction accuracy fraction, block bootstrap bounds, exact denominator |
| data/public/site_data.json | reviewed public subset | Metadata source/snapshot/dates/units/protocol; no vessel identifiers, private paths or full raw panel; nulls preserved |

One TEU is a container-size unit. Positive bias means overprediction. Positive relative lift means lower error. A 5% relative lift is not five percentage points of WAPE. `fallback_used` marks the shared seasonal policy and must not be confused with source absence. `source_features_valid` measures the window contract, not total vessels detected. Independently observed calendar periods number24, not gateway-days or forecast-model rows.
