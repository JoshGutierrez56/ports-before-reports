"""Human-readable research documents generated from the frozen evidence ledger."""
from pathlib import Path
import json
import re
import pandas as pd
from scsi.provenance import sha256,write_json,utcnow
from scsi.publishing.figures import NAMES

def markdown_table(headers,rows):
    return "\n".join(["| "+" | ".join(headers)+" |","| "+" | ".join(["---"]*len(headers))+" |",*["| "+" | ".join(map(str,r))+" |" for r in rows]])

def write_reports(root,config,results,primary):
    from scsi.publishing.exports import claim_text,LIMITS
    root=Path(root);docs=root/"docs";docs.mkdir(exist_ok=True)
    met={m["model_id"]:m for m in primary["metrics"]};direct=next(x for x in primary["comparisons"] if x["comparator"]=="aggregate_activity_ridge")
    strong=next(x for x in primary["comparisons"] if x["comparator"]==primary["selected_benchmark"])
    headline=claim_text(results,primary)
    table=markdown_table(["Model","WAPE","MAE · TEUs","RMSE · TEUs","Bias · TEUs","YoY direction"],[[NAMES[m["model_id"]],f"{m['wape']:.2%}",f"{m['mae']:,.0f}",f"{m['rmse']:,.0f}",f"{m['bias']:+,.0f}",f"{m['direction_accuracy']:.1%}"] for m in primary["metrics"]])
    intervals=markdown_table(["Comparator","Relative lift","3-month block 95% interval","6-month block 95% interval"],[[NAMES[c["comparator"]],f"{c['relative_lift']:+.2%}",*[f"[{b['lower']:+.2%}, {b['upper']:+.2%}]" for b in c["bootstrap"]]] for c in primary["comparisons"]])
    sensitivity=markdown_table(["Shipping lag","Unknown target lag","Geography WAPE","Aggregate WAPE","Selected baseline WAPE"],[[e["flow_lag_days"],e["target_release_lag_days"],*[f"{next(m['wape'] for m in e['metrics'] if m['model_id']==key):.2%}" for key in ["geography_ridge","aggregate_activity_ridge",e["selected_benchmark"]]]] for e in results["experiments"] if e["role"] in ("primary","reporting_lag_sensitivity")])
    records=json.loads((root/primary["prediction_artifact"]).read_text());first=next(r for r in records if r["model_id"]=="geography_ridge" and not r["fallback_used"])
    agg=next(r for r in records if r["model_id"]=="aggregate_activity_ridge" and r["target_month"]==first["target_month"])
    from scsi.research.pipeline import load_inputs
    from scsi.features.flow import window_sum,matched_prior_end
    from scsi.config import GATEWAYS
    daily,_=load_inputs(root)
    example_day=(pd.Timestamp(first["feature_cutoff_utc"])-pd.Timedelta(days=1)).tz_localize(None).normalize()
    current_calls=window_sum(daily,example_day,28,GATEWAYS)
    prior_calls=window_sum(daily,matched_prior_end(example_day),28,GATEWAYS)
    flow_example=f"The admissible twenty-eight-day window contained {current_calls.sum():,.0f} container calls, versus {prior_calls.sum():,.0f} in the matched prior-year window ({current_calls.sum()/prior_calls.sum()-1:+.1%})."
    queue_example="The matching full-year measurement date is still pending in this draft; no queue evidence is asserted for this decision example."
    geo_receipt=root/"artifacts/audit/geo_daily_features.csv"
    geo_summary="The measurement pipeline has not yet produced a final coverage receipt; no full-year completeness is implied by this draft."
    if geo_receipt.exists():
        gd=pd.read_csv(geo_receipt)
        datecol=next((k for k in ("date","observation_date","day") if k in gd),None)
        if datecol:
            dates=pd.to_datetime(gd[datecol]);geo_summary=f"The current measurement export contains {dates.nunique()} distinct source dates, {len(gd):,} gateway-day rows, spanning {dates.min():%Y-%m-%d} to {dates.max():%Y-%m-%d}. The separate acquisition manifest establishes which national partitions were actually acquired; rows alone do not prove complete vessel detection."
            matched=gd.loc[dates.eq(example_day)]
            if len(matched)==3:
                pieces=[]
                for _,g in matched.iterrows():
                    stock="unknown" if pd.isna(g.queue_stock) else f"{int(g.queue_stock)} observed candidates"
                    pieces.append(f"{g.gateway_id.replace('_',' ')}: {stock}, {g.anchorage_hours:,.1f} observed anchorage-candidate hours")
                queue_example=f"Retrospective NOAA reconstruction on {example_day:%Y-%m-%d} gives "+"; ".join(pieces)+". These bounded observations do not establish a common congestion shock; Savannah's known offshore coverage limitation prevents treating a low count as no queue. The archive was not verified available at the forecast origin."
    operational_summary=""
    operational_path=root/"artifacts/audit/geo_operational_summary.json"
    if operational_path.exists():
        operational=json.loads(operational_path.read_text(encoding="utf-8"))
        pieces=[f"{row['gateway_id'].replace('_',' ')}: {row['noaa_candidate_mean']:.2f} mean modeled candidates versus {row['reported_stock_mean']:.2f} reported stock across {row['valid_pairs']} valid date pairs" for row in operational if row.get("valid_pairs",0)>0]
        if pieces:
            operational_summary="The matched operational comparison does not establish agreement: "+"; ".join(pieces)+". Population, geographic footprint and observation-clock differences preclude a like-for-like accuracy score. In particular, Savannah's zero modeled stock alongside positive reported stock reinforces the bounded offshore-coverage limitation; it is not evidence of no queue. Source: `artifacts/audit/geo_operational_summary.json`."
    robust=json.loads((root/"artifacts/metrics/robustness.json").read_text()) if (root/"artifacts/metrics/robustness.json").exists() else {}
    report=f"""# Ports Before Reports: research findings

## Finding first

**{headline}** The primary candidate's weighted absolute percentage error was **{met['geography_ridge']['wape']:.2%}**, versus **{met['aggregate_activity_ridge']['wape']:.2%}** for aggregate shipping and **{met[primary['selected_benchmark']]['wape']:.2%}** for the strongest noncandidate baseline selected on 2023 validation. The direct geography comparison implies **{direct['relative_lift']:+.2%} relative lift**, not percentage points of error reduction. The evidence status is **{results['claim_status']}**. The primary statistical gate is separately retained as **{results['primary_gate_status']}**; reporting-lag robustness undermines an unqualified claim: **{results['reporting_lag_robustness_undermines']}**.

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

The fifth model converts calls into TEUs using each gateway's training-only median monthly TEU-per-call ratio and projects the latest observed twenty-eight-day call rate across the forecast month's day count. This simple model assumes a stable conversion and rate. It may fail when vessel size, cargo composition or within-month timing changes, but its operational meaning is easier to inspect than a flexible regression. The strongest noncandidate model was **{NAMES[primary['selected_benchmark']]}**, chosen before test scores were opened.

## Results on a common policy

All mandatory models forecast the same twenty-four test months. If the shared activity-feature contract is incomplete, the common policy uses the prior-year same-month target. The primary candidate's fallback rate is {met['geography_ridge']['fallback_rate']:.1%}, and its valid-source-feature rate is {met['geography_ridge']['source_coverage_rate']:.1%}. Full-policy performance is primary; common-valid-feature scores are retained separately. A model cannot improve its headline by skipping difficult months.

{table}

WAPE divides total absolute TEU error by total realized TEUs. MAE and RMSE preserve the target's units; bias is prediction minus outcome. Directional accuracy asks whether predicted and realized year-over-year growth have the same sign, not whether a trading position would make money. No per-gateway regression scores are fabricated from composite-only predictions. Changed-target diagnostics remove a gateway explicitly and are not extra independent replications of the primary target.

## Uncertainty and robustness

{intervals}

Each interval uses 10,000 paired moving-block bootstrap replicates. Three- and six-month contiguous calendar blocks preserve some serial dependence, and the same sampled months are used across models. Missing-target markers remain on the calendar. The twenty-four test months, not thousands of daily inputs or several ports, are the independent forecast periods. These are intervals for comparative average error, not prediction intervals for a new month. No forecast band is displayed because a separately validated band was not part of the core model.

The preselected practical threshold is five percent relative improvement versus both aggregate shipping and the validation-selected strongest baseline, with both block-length intervals above zero and at least twenty available target months. That hurdle is a project decision rule, not a universal economic standard. Even a statistical pass would remain qualified by reporting-lag, revision and regime uncertainty. Robustness results are all retained; an attractive secondary slice cannot replace an unfavorable primary comparison.

{sensitivity}

Each lag/release-lag specification was selected using the same 2023-only procedure before any final test score. Longer shipping delays can remove current-month observations entirely; trailing windows are still measured, never zero-filled. The sixty- and ninety-day target-release lags are assumptions for undated releases, not claims about historical authority schedules. All 336 source target rows lacked verified first-release timestamps, so the denominator for a verified days-before-official-release claim is zero.

Year-by-year scores, gateway concentration and all three leave-one-gateway-out targets are stored in the results artifact. Excluding the ambiguous NYNJ facility perimeter uses the same explicit changed-target experiment; it does not allocate uncertain terminals arbitrarily. No optional estimated-tonnage feature was added, so its ablation is not applicable. A deliberately future-shifted twenty-eight-day feature is saved only as a forbidden diagnostic, never as an admissible forecasting model.

## Busy port or bottleneck: a separate measurement layer

{geo_summary} The raw-point study is confined to the documented 2024 NOAA archive. It does not create a long 2019–2025 congestion history. Cargo broadcast codes identify a cargo-vessel proxy, not independently confirmed containerships. Transmission density is not vessel activity, and stationary presence is not verified import delay.

The engine separates approach, transit, anchorage candidates, berth candidates and unknown gaps using attributed boundaries, speed, persistence and continuity. Local projected coordinate systems are used for meter buffers; public coordinates remain WGS84. Shared San Pedro anchorage is counted once. Exact duplicate pings are removed, conflicting positions are flagged, implausible jumps are not filled, and state carries across midnight. Long missing intervals become unknown time rather than confirmed dwell.

Anchorage hours and elapsed age of active candidates are lower-bound observations with coverage and censoring metadata. A vessel later reaching a container berth can support retrospective interpretation but cannot rewrite what was observable at an earlier cutoff. The optional friction summary uses two equally weighted robust log-transformed components, standardized on prior valid days only. It is not seasonal adjustment. A zero detected queue is distinguished from unknown coverage; it does not prove that no real queue existed.

Sixty stratified actual trajectories are audited by agents, not maritime experts or independent human reviewers. The geometry, speed and gap sensitivity tables remain part of the result. The pilot showed substantial sensitivity to approximate berth corridors; official anchorage polygons are more defensible than inferred quay buffers. The study therefore demonstrates a reproducible measurement process, not validated delay ground truth. Limited BTS operational waiting-stock data provide a definition-aware consistency check; shared AIS origins and differing vessel classes prevent treating that comparison as independent truth.

{operational_summary}

## Analyst use and a dated decision example

The first valid test-origin example is chosen chronologically, not for an attractive story: **{first['target_month']}**. Geographic shipping predicted **{first['prediction_teu']:,.0f} TEUs**, aggregate shipping **{agg['prediction_teu']:,.0f}**, and the subsequently recorded target was **{first['actual_teu']:,.0f}**. Its information cutoff was **{first['feature_cutoff_utc']}**, with latest admitted target-growth observation **{first['latest_training_target']}**. {flow_example} {queue_example} The precomputed record exposes the exact inputs, training months and fitted parameters so the disagreement can be inspected rather than narrated from a chart alone.

An analyst could use that disagreement to ask whether inventory arrivals are geographically concentrated, whether a disruption is shifting gateway activity, or whether official reporting timing obscures a physical change. The separately dated queue-candidate exhibit can help inspect a congestion explanation, but it is retrospective and cannot be smuggled into the earlier information set. A security-level thesis would additionally require product mix, inventory disclosures, importer exposure, shipment utilization and economically justified company mapping. Headquarters proximity supplies none of those facts.

## Reproducibility, permissions and conclusion

The final protocol, exact source manifests, crosswalk, research-critical code and validation selections were hashed before test evaluation. Pre-test software-hardening reruns produced exactly identical validation grids, selections and prediction records across all nine specifications. Immutable test files have per-experiment receipts; interrupted runs verify hashes instead of overwriting results. Future-data append checks leave both fallback and valid-origin forecasts unchanged, including fitted parameters. Synthetic fixtures live only in the tests and never supply empirical charts.

The local package, tests, executed notebooks, source/license registry and reviewed export bundle make the result inspectable. PortWatch is attributed to Kpler, the UN Global Platform and IMF PortWatch; its access is not a license to redistribute raw proprietary AIS. NOAA product-specific terms and BTS government-data terms are recorded separately. No remote repository, site deployment, paid service, recurring job or LinkedIn post was created for this project. A prospective append-only forecast command exists, but no live forecast is claimed before a genuine future snapshot is saved.

The defensible contribution is the controlled comparison, the measurement audit and an honest availability boundary. {headline} The companion map explains physical activity with visible uncertainty, while the forecast evidence answers the narrower statistical question without converting an interesting port story into invented investment alpha.

## Evidence links

- [Frozen metrics](../artifacts/metrics/locked_results.json) and [robustness](../artifacts/metrics/robustness.json)
- [Protocol lock](../artifacts/protocol_lock.json), [availability audit](AVAILABILITY_AUDIT.md), [literature review](LITERATURE_REVIEW.md)
- [Data access audit](DATA_ACCESS_AUDIT.md), [geospatial method](GEOSPATIAL_METHOD.md), [data licenses](../DATA_LICENSES.md)
"""
    (docs/"RESEARCH_FINDINGS.md").write_text(report,encoding="utf-8")
    count=len(re.findall(r"\b[\w’'-]+\b",report))
    write_json(root/"artifacts/audit/report_receipt.json",{"word_count":count,"target_range":[1500,2500],"generated_at_utc":utcnow(),"metrics_sha256":sha256(root/"artifacts/metrics/locked_results.json"),"protocol_sha256":results["protocol_sha256"]})
    model=f"""# Model card

## Intended use and result

{headline}

- Unit of prediction: monthly selected-gateway loaded-import TEUs, four official port labels / three physical gateways.
- Primary comparison: geography ridge vs aggregate-activity ridge; additional benchmark selected solely on 2023 validation: {NAMES[primary['selected_benchmark']]}.
- Sample: 12 validation months; 24 test months (2024–2025); 2026 excluded.
- Availability: current-vintage pseudo-real-time, assumed 7-day shipping / 60-day undated-target delay. No historical release-vintage proof.
- Features: two released-target growth features; two aggregate or six gateway call-growth features. Training-only scaling; ridge alpha grid [1,10,100].
- Primary selected penalties: `{json.dumps(primary['alphas'],sort_keys=True)}`.
- Target: log annual growth; released seasonal base reconstruction; no inverse bias correction, outcome-driven clipping or forecast intervals.
- Missingness: shared seasonal fallback; primary full-policy fallback {met['geography_ridge']['fallback_rate']:.1%}. Missing traffic is never zero.
- Claim status: {results['claim_status']}; source and protocol hash: `{results['protocol_sha256']}`.

## Evaluation

{table}

{intervals}

## Limits and prohibited claims

The geospatial engine is separate from H1. Its 2024 observations cannot create earlier measured congestion. Current-vintage revisions, short test history, estimated port-call boundaries and model complexity limit interpretation. Queue candidates are not verified delayed loaded-import ships. No causal, profitable, alpha, live, institutional-adoption, production-grade or independent-human-validation claim is supported. The optional equity extension is **NOT_REQUIRED_FOR_V1** and not executed.

## Operations

Local batch research only. No daemon/scheduler, remote writes or paid resources. Source acquisition uses bounded retry/rate limits, immutable hashes and resumable receipts. Failure to satisfy a source contract stops that stage or uses the declared shared fallback; it never fabricates a target. Prospective packets are append-only and refuse after-cutoff snapshots or already-known current outcomes.
"""
    (docs/"MODEL_CARD.md").write_text(model,encoding="utf-8")
    (docs/"AVAILABILITY_AUDIT.md").write_text(f"""# Availability audit

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

{sensitivity}

The deliberately future-shifted placebo is diagnostic-only and explicitly forbidden in production. See `artifacts/audit/time_shift_placebo_forbidden.json`. Future-append invariance results are in `artifacts/metrics/robustness.json`. No future-completed queue duration enters an earlier as-of feature.
""",encoding="utf-8")
    dictionary="""# Data dictionary

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
"""
    (docs/"DATA_DICTIONARY.md").write_text(dictionary,encoding="utf-8")
    return {"report":"docs/RESEARCH_FINDINGS.md","word_count":count,"within_word_target":1500<=count<=2500}
