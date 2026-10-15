"""Build evidence-linked review artifacts; this module never publishes remotely."""
from pathlib import Path
import csv
import datetime as dt
import gzip
import hashlib
import json
import re
import zipfile
import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
from scsi.provenance import sha256,write_json,utcnow,ledger
from scsi.research.pipeline import verify_lock
from scsi.publishing.figures import NAMES,create_figures

SOURCES=[
    {"id":"bts_loaded_imports","name":"BTS / port-authority loaded-import TEUs","url":"https://data.bts.gov/resource/y5ut-ibwt.json","terms_url":"https://www.usa.gov/government-works"},
    {"id":"portwatch","name":"Kpler; UN Global Platform; IMF PortWatch","url":"https://portwatch.imf.org/","terms_url":"https://www.imf.org/en/about/copyright-and-terms"},
    {"id":"noaa_points","name":"NOAA Office for Coastal Management / MarineCadastre","url":"https://github.com/ocm-marinecadastre/ais-vessel-traffic","terms_url":"https://github.com/ocm-marinecadastre/ais-vessel-traffic/blob/main/data/ais-broadcast-points-2024-readme.md"},
]
LIMITS=["Current-vintage pseudo-real-time evaluation under assumed reporting lags; historical public availability is not verified.","Only 24 independent monthly test periods; model selection, data revisions and regime uncertainty remain.","Selected-gateway loaded-import TEUs are not total U.S. imports, consumer demand or investment returns.","NOAA cargo-vessel proxy and queue-candidate states are retrospective, coverage-limited measurements, not independently validated delay labels."]
FORECAST_FIELDS=("model_id","target_month","forecast_origin_utc","feature_cutoff_utc","training_label_cutoff","train_end","latest_training_target","prediction_teu","actual_teu","interval_lower","interval_upper","fallback_used","fallback_reason","source_features_valid","flow_lag_days","target_release_lag_days","availability_mode","available_training_months","protocol_sha256","experiment_id","seasonal_base_teu")
SENSITIVITY_FIELDS=("experiment_id","role","flow_lag_days","target_release_lag_days","gateways","selected_benchmark","metrics","comparisons","year_diagnostics","common_valid_feature_metrics")

def read_results(root):
    root=Path(root);verify_lock(root)
    path=root/"artifacts/metrics/locked_results.json"
    data=json.loads(path.read_text(encoding="utf-8"))
    if data["protocol_sha256"]!=sha256(root/"artifacts/protocol_lock.json"):raise ValueError("Results do not match protocol")
    for name,h in data["prediction_hashes"].items():
        if sha256(root/name)!=h:raise ValueError("Prediction artifact changed")
    return data,next(x for x in data["experiments"] if x["role"]=="primary")

def claim_text(results,primary):
    status=results["claim_status"]
    if status in ("REAL_DATA_BLOCKED","MEASUREMENT_ONLY"):
        return "The forecasting claim is blocked; completed measurement evidence is reported separately."
    direct=next(x for x in primary["comparisons"] if x["comparator"]=="aggregate_activity_ridge")
    if status=="HISTORICAL_LIFT_SUPPORTED":return f"Geographic detail reduced historical forecast error by {direct['relative_lift']:.1%} versus aggregate shipping in the locked 2024–2025 test."
    if status=="NO_INCREMENTAL_LIFT":return "Geographic detail did not improve the import forecast in the locked 2024–2025 test."
    if status=="PROMISING_BUT_UNCERTAIN":
        benchmark=next(c for c in primary["comparisons"] if c["comparator"]==primary["selected_benchmark"])
        if benchmark["relative_lift"]<=0:
            return f"{NAMES[primary['selected_benchmark']]} beat the geography-aware model; the gain over aggregate shipping was uncertain."
        return "Geographic detail showed a tentative improvement; the evidence does not establish a robust forecasting advantage."
    return "The forecasting claim is blocked; completed measurement evidence is reported separately."

def public_safe(value):
    """Reject private identifiers and machine-specific paths in public structured exports."""
    forbidden={"mmsi","imo","vessel_name","vessel_identifier","raw_vessel_id","password","access_token"}
    def walk(x):
        if isinstance(x,dict):
            for k,v in x.items():
                if k.lower() in forbidden:raise ValueError(f"Private identifier in public export: {k}")
                walk(v)
        elif isinstance(x,list):
            for v in x:walk(v)
        elif isinstance(x,str) and (re.search(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]",x) or "/Users/" in x or "/home/" in x):
            raise ValueError("Local filesystem path in public export")
    walk(value)
    json.dumps(value,allow_nan=False)
    return value

def public_result_rows(root,results):
    """The exact reviewed projection of locked results, shared by writer and gate."""
    root=Path(root)
    forecasts=[];metrics=[];sensitivity=[]
    for e in results["experiments"]:
        sensitivity.append({k:e[k] for k in SENSITIVITY_FIELDS})
        if e["role"] not in ("primary","reporting_lag_sensitivity"):continue
        rows=json.loads((root/e["prediction_artifact"]).read_text(encoding="utf-8"))
        if len(rows)!=120 or len({(r["model_id"],r["target_month"]) for r in rows})!=120:
            raise ValueError("Locked forecast experiment must contain 120 distinct origin/model records")
        forecasts.extend({k:r.get(k) for k in FORECAST_FIELDS} for r in rows)
        metrics.extend({**m,"experiment_id":e["experiment_id"],"flow_lag_days":e["flow_lag_days"],"target_release_lag_days":e["target_release_lag_days"]} for m in e["metrics"])
    return forecasts,metrics,sensitivity


def verify_public_evidence(root,results,primary,site):
    """Reject duplicate, omitted, extra or changed displayed evidence fields."""
    public_safe(site)
    forecasts,metrics,sensitivity=public_result_rows(root,results)
    expected={"claim":{"status":results["claim_status"],"text":claim_text(results,primary),"limitations":LIMITS},"forecasts":forecasts,"metrics":metrics,"sensitivity":sensitivity,"comparisons":primary["comparisons"],"primary_gate_status":results["primary_gate_status"],"reporting_lag_robustness_undermines":results["reporting_lag_robustness_undermines"],"selected_benchmark":primary["selected_benchmark"]}
    for field,value in expected.items():
        if site.get(field)!=value:raise ValueError(f"Public {field} differs from locked evidence")
    for field in ("protocol_sha256","prediction_hashes"):
        if site.get("metadata",{}).get(field)!=results[field]:
            raise ValueError(f"Public metadata {field} differs from locked evidence")


def build_site_data(root,config):
    root=Path(root);results,primary=read_results(root);dest=root/"data/public";dest.mkdir(parents=True,exist_ok=True)
    forecasts,metrics,sensitivity=public_result_rows(root,results)
    meta={"status":"FROZEN_FORECAST_EVIDENCE","generated_at_utc":utcnow(),"protocol_sha256":results["protocol_sha256"],"availability_mode":"current_vintage_pseudo_realtime","measurement_dates":{"flow":"2019-01-01/2025-12-31","forecast_test":"2024-01/2025-12","raw_ais":"2024 (see separate completeness receipt)"},"units":{"target":"loaded-import TEUs","prediction":"loaded-import TEUs","wape":"fraction","relative_lift":"fraction"},"sources":SOURCES,"snapshots":{name:json.loads((root/f"data/manifests/{name}.json").read_text())["snapshot_id"] for name in ("source_targets","source_flow")},"prediction_hashes":results["prediction_hashes"],"transformation_notes":"Published model outputs and limited transformed comparisons; full source PortWatch panel and raw vessel positions are not redistributed.","notes":LIMITS}
    out=public_safe({"metadata":meta,"claim":{"status":results["claim_status"],"text":claim_text(results,primary),"limitations":LIMITS},"forecasts":forecasts,"metrics":metrics,"comparisons":primary["comparisons"],"sensitivity":sensitivity,"primary_gate_status":results["primary_gate_status"],"reporting_lag_robustness_undermines":results["reporting_lag_robustness_undermines"],"selected_benchmark":primary["selected_benchmark"]})
    write_json(dest/"site_data.json",out)
    claims=[{"claim_id":"H1-PRIMARY","proposed_text":out["claim"]["text"],"claim_type":"locked_historical_comparison","supporting_artifact":"artifacts/metrics/locked_results.json","statistic_definition":"1 - WAPE(geography) / WAPE(aggregate); full shared fallback policy","evaluation_period":"2024-01/2025-12","denominator":24,"availability_status":"current_vintage_pseudo_realtime","limitations":"; ".join(LIMITS),"approval_status":"agent_evidence_verified_not_human_reviewed"}]
    for m in primary["metrics"]:
        claims.append({"claim_id":"METRIC-"+m["model_id"],"proposed_text":f"{NAMES[m['model_id']]}: WAPE {m['wape']:.2%}","claim_type":"descriptive_metric","supporting_artifact":"artifacts/metrics/locked_results.json","statistic_definition":"sum(abs(actual-predicted)) / sum(actual)","evaluation_period":"2024-01/2025-12","denominator":m["n_months"],"availability_status":"current_vintage_pseudo_realtime","limitations":"Full-policy result includes identical seasonal fallback on incomplete core information.","approval_status":"agent_evidence_verified_not_human_reviewed"})
    with (root/"docs/CLAIMS_LEDGER.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=list(claims[0]));w.writeheader();w.writerows(claims)
    actual=pd.DataFrame(json.loads((root/primary["prediction_artifact"]).read_text())).drop_duplicates("target_month")[["target_month","actual_teu","seasonal_base_teu"]]
    actual.to_csv(dest/"test_target_aggregates.csv",index=False)
    write_json(dest/"test_target_aggregates.metadata.json",{**meta,"artifact":"test_target_aggregates.csv","sha256":sha256(dest/"test_target_aggregates.csv"),"rows":len(actual),"notes":"BTS public-domain selected-gateway composite; no upstream report images/text copied."})
    size=len(gzip.compress((dest/"site_data.json").read_bytes()))
    if size>2*1024**2:raise ValueError("Initial research export exceeds compressed payload budget")
    receipt={"status":"complete","forecast_rows":len(forecasts),"metric_rows":len(metrics),"site_data_sha256":sha256(dest/"site_data.json"),"site_data_gzip_bytes":size,"claim_status":results["claim_status"]}
    write_json(root/"artifacts/audit/public_export_receipt.json",receipt);ledger(root,"J","public_export_built",**receipt)
    return receipt

def build_report(root,config):
    from scsi.publishing.report import write_reports
    root=Path(root);results,primary=read_results(root)
    figures=create_figures(root,results)
    report=write_reports(root,config,results,primary)
    return {"status":"complete","figures":figures,**report}

def make_source_bundle(root):
    """Explicit allowlist: no source PDFs, raw data, private paths, browser sessions or credentials."""
    root=Path(root);out=root/"release";out.mkdir(exist_ok=True)
    members=[]
    for pattern in ["src/**/*.py","tests/**/*.py","scripts/reproduce_public.py","scripts/bootstrap.ps1","scripts/run_core.ps1","scripts/verify_release.ps1","pyproject.toml","requirements.lock","LICENSE","DATA_LICENSES.md","README.md","RESEARCH_PROTOCOL.md","docs/RESEARCH_FINDINGS.md","docs/MODEL_CARD.md","docs/DATA_DICTIONARY.md","docs/DATA_ACCESS_AUDIT.md","docs/AVAILABILITY_AUDIT.md","docs/GEOSPATIAL_METHOD.md","docs/LITERATURE_REVIEW.md","docs/CLAIMS_LEDGER.csv","docs/REPRODUCIBILITY.md","docs/INTERVIEW_BRIEF.md","data/public/*.json","data/public/*.csv","data/geography/geofences_v1.geojson","data/geography/geofences_provenance.json","data/geography/gateway_crosswalk.csv","data/manifests/source_targets.json","data/manifests/source_flow.json","artifacts/metrics/*.json","artifacts/predictions/*.json","artifacts/protocol_lock.json","artifacts/initial_protocol_lock.json","artifacts/audit/geo_pilot_freeze.json","artifacts/audit/geo_measurement_receipt.json","artifacts/figures/*.png"]:
        members.extend(p for p in root.glob(pattern) if p.is_file())
    for pattern in ["notebooks/*.ipynb","notebooks/execute.py","notebooks/verify_locked_predictions.py","artifacts/audit/notebook_execution.json","artifacts/audit/independent_research_audit.json","artifacts/audit/public_reproduction_receipt.json","artifacts/audit/prediction_lineage_index.json","data/source_registry.yaml"]:
        members.extend(p for p in root.glob(pattern) if p.is_file())
    # Preserve the actual acceptance evidence in the review package, not merely
    # a full-year label. These are aggregate tables/receipts, never raw tracks.
    for pattern in ["artifacts/audit/geo_finalization_state.json","artifacts/audit/geo_postfreeze_correction_receipt.json","artifacts/audit/geo_build_acceptance_receipt.json","artifacts/audit/geo_daily_features.csv","artifacts/audit/geo_cleaning_receipt.json","artifacts/audit/geo_coverage_calendar.csv","artifacts/audit/geo_sensitivity.csv","artifacts/audit/geo_friction_correction_comparison.csv","artifacts/audit/geo_operational_comparison.csv","artifacts/audit/geo_operational_summary.json","scripts/initialize_config.py","scripts/audit_source_access.py","scripts/check_public_bundle.py","scripts/smoke_wheel.py"]:
        members.extend(p for p in root.glob(pattern) if p.is_file())
    payloads={p.relative_to(root).as_posix():p.read_bytes() for p in sorted(set(members))}
    resolved=json.loads(json.dumps(__import__("yaml").safe_load((root/"configs/project.yaml").read_text())))
    resolved["project"]["workspace_root"]=None;resolved["project"]["website_repo"]=None
    payloads["configs/project.template.yaml"]=__import__("yaml").safe_dump(resolved,sort_keys=False).encode("utf-8")
    geo_path=root/"artifacts/audit/geo_measurement_receipt.json"
    geo=json.loads(geo_path.read_text(encoding="utf-8")) if geo_path.exists() else {}
    metadata=public_safe({"publication":"LOCAL_REVIEW_ONLY","sources":SOURCES,"protocol_sha256":sha256(root/"artifacts/protocol_lock.json"),"measurement_dates":{"start":geo.get("measurement_start"),"end":geo.get("measurement_end")},"availability_mode":"retrospective_descriptive","forecast_availability_mode":"current_vintage_pseudo_realtime","measurement_receipt_sha256":sha256(geo_path) if geo_path.exists() else None,"snapshot_lineage":"artifacts/audit/geo_measurement_receipt.json","units":{"vessel_hours":"observed cargo-vessel proxy hours","queue_stock":"observed queue-candidate count, null when coverage is insufficient","active_age":"hours observed through cutoff","friction":"robust standardized index, not hours or TEUs"},"transformation_notes":"Geospatial CSVs are daily aggregates, sensitivity summaries, or measurement-correction comparisons. Raw tracks, vessel identifiers and private trace keys are excluded. January pilot sensitivities remain labeled with their actual source_days; full-year acquisition does not turn them into full-year sensitivities.","reproduction_scope":"Portable script replays 720 published forecast records and 30 metric rows, not source reacquisition or model refitting."})
    payloads["BUNDLE_METADATA.json"]=(json.dumps(metadata,indent=2,allow_nan=False)+"\n").encode("utf-8")
    bundle=out/"reviewed-source.zip";temporary=out/"reviewed-source.partial.zip"
    records=[]
    with zipfile.ZipFile(temporary,"w",zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,body in sorted(payloads.items()):
            # Fixed headers make unchanged reviewed inputs byte-reproducible.
            info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
            z.writestr(info,body,compresslevel=9)
            records.append({"path":name,"sha256":hashlib.sha256(body).hexdigest(),"bytes":len(body)})
    temporary.replace(bundle)
    manifest={"bundle":"reviewed-source.zip","sha256":sha256(bundle),"byte_count":bundle.stat().st_size,"member_count":len(records),"members":records,"excluded":"Raw/cropped AIS; full PortWatch panel; copied PDFs/HTML; machine paths; private preflight; source account data","publication":"LOCAL_REVIEW_ONLY"}
    write_json(out/"source_bundle_manifest.json",manifest)
    return manifest

def verify_execution_receipts(root):
    """Require successful checks of the files actually delivered, not old labels."""
    root=Path(root)
    test_path=root/"artifacts/test-results/pytest.xml"
    if not test_path.exists():raise ValueError("Release requires the actual pytest JUnit report")
    tree=ET.parse(test_path).getroot()
    suites=[tree] if tree.tag=="testsuite" else list(tree.findall("testsuite"))
    counts={key:sum(int(s.get(key,"0")) for s in suites) for key in ("tests","failures","errors","skipped")}
    if counts["tests"]<=0 or counts["failures"] or counts["errors"]:raise ValueError("Release tests did not pass")
    notebook_path=root/"artifacts/audit/notebook_execution.json"
    if not notebook_path.exists():raise ValueError("Release requires both executed notebooks")
    receipt=json.loads(notebook_path.read_text(encoding="utf-8"))
    expected={"01_measurement_audit.ipynb","02_locked_research.ipynb"}
    rows=receipt.get("notebooks",[])
    if receipt.get("status")!="executed" or {r.get("notebook") for r in rows}!=expected or len(rows)!=2:
        raise ValueError("Both required notebooks must execute successfully")
    for r in rows:
        if r.get("status")!="executed" or not r.get("code_cells") or r.get("code_cells")!=r.get("executed_code_cells"):
            raise ValueError("Notebook has unexecuted or failed code cells")
        if sha256(root/"notebooks"/r["notebook"])!=r["executed_notebook_sha256"]:
            raise ValueError("Notebook changed after its recorded execution")
        for name,h in r.get("input_hashes",{}).items():
            if sha256(root/name)!=h:raise ValueError(f"Notebook input changed after execution: {name}")
    independent=json.loads((root/"artifacts/audit/independent_research_audit.json").read_text(encoding="utf-8"))
    if independent.get("status")!="passed" or independent.get("prediction_records_checked")!=1080:
        raise ValueError("Independent arithmetic reconciliation is incomplete")
    if independent.get("audit_script_sha256")!=sha256(root/"notebooks/verify_locked_predictions.py"):
        raise ValueError("Independent numerical audit script changed after execution")
    if independent.get("locked_results_sha256")!=sha256(root/"artifacts/metrics/locked_results.json"):
        raise ValueError("Independent numerical audit used other locked results")
    return {"python_tests":counts,"executed_notebooks":len(rows),"executed_notebook_cells":sum(r["executed_code_cells"] for r in rows),"independently_reconciled_prediction_records":1080}


def verify_release(root,config):
    root=Path(root);results,primary=read_results(root)
    site=json.loads((root/"data/public/site_data.json").read_text());public_safe(site)
    verify_public_evidence(root,results,primary,site)
    robust=json.loads((root/"artifacts/metrics/robustness.json").read_text())
    if not all(robust["future_append_tests"].values()):raise ValueError("Leakage gate failed")
    geo_path=root/"artifacts/audit/geo_measurement_receipt.json"
    if not geo_path.exists():raise ValueError("Core release requires actual raw-AIS measurement, not a forecast-only substitute")
    geo=json.loads(geo_path.read_text(encoding="utf-8"))
    if geo.get("source_days")!=366 or geo.get("measurement_start")!="2024-01-01" or geo.get("measurement_end")!="2024-12-31":
        raise ValueError("Core release requires all366 documented2024source days; a pilot is unfinished core work")
    from scsi.geo.finalize import verify_accepted_measurement
    geo=verify_accepted_measurement(root,config)
    acceptance=json.loads((root/"artifacts/audit/geo_finalization_state.json").read_text(encoding="utf-8"))
    pilot=json.loads((root/"artifacts/audit/geo_pilot_freeze.json").read_text(encoding="utf-8"))
    if geo.get("geometry_sha256")!=pilot["geometry_sha256"]:raise ValueError("Full measurement geometry differs from frozen pilot")
    audit=pd.read_csv(root/"artifacts/audit/geo_trajectory_audit.csv")
    if len(audit)<60 or not audit.review_status.astype(str).str.contains("visual_reviewed").all():
        raise ValueError("Sixty actually reviewed trajectory examples are required")
    if sha256(root/"artifacts/audit/geo_trajectory_audit.csv")!=pilot["audit_sha256"]:raise ValueError("Frozen reviewed trajectory audit changed")
    if sha256(root/"artifacts/audit/geo_daily_features.csv")!=geo["daily_sha256"]:
        raise ValueError("Geospatial daily measurements differ from receipt")
    geo_public=root/"artifacts/audit/geo_site_data.json"
    public_safe(json.loads(geo_public.read_text(encoding="utf-8")))
    if sha256(geo_public)!=acceptance.get("site_export_sha256"):raise ValueError("Public geospatial export differs from accepted measurement")
    (root/"data/public/geo_site_data.json").write_bytes(geo_public.read_bytes())
    required=["README.md","LICENSE","DATA_LICENSES.md","requirements.lock","docs/RESEARCH_FINDINGS.md","docs/MODEL_CARD.md","docs/AVAILABILITY_AUDIT.md","docs/DATA_DICTIONARY.md","docs/GEOSPATIAL_METHOD.md","docs/LITERATURE_REVIEW.md","docs/CLAIMS_LEDGER.csv","docs/REPRODUCIBILITY.md","docs/INTERVIEW_BRIEF.md"]
    missing=[p for p in required if not (root/p).is_file()]
    if missing:raise ValueError(f"Required documentation missing: {missing}")
    executed=verify_execution_receipts(root)
    manifest=make_source_bundle(root)
    receipt={"status":"core_evidence_verified","protocol_sha256":results["protocol_sha256"],"forecast_rows_checked":len(site["forecasts"]),"metrics_checked":len(site["metrics"]),"source_bundle_sha256":manifest["sha256"],"geospatial_source_days":geo["source_days"],"trajectory_examples_reviewed":len(audit),"reviewer_type":"agent_assisted_not_independent_human_validation","created_at_utc":utcnow(),**executed}
    write_json(root/"artifacts/audit/release_evidence_check.json",receipt)
    return receipt

def shadow_forecast(root,config,snapshot):
    from scsi.research.prospective import save_shadow_forecast
    if snapshot is None:raise ValueError("shadow-forecast requires an acquired, timestamped --snapshot packet; no synthetic/live stand-in is created")
    return save_shadow_forecast(Path(root),snapshot)
