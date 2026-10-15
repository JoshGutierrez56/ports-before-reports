"""Stage-specific validation, immutable freeze, test evaluation and predeclared checks."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from scsi.config import GATEWAYS,MODELS,canonical_hash,config_hash
from scsi.provenance import sha256,write_json,utcnow,ledger,assert_hash
from scsi.features.flow import normalized_daily
from scsi.research.data import prepare_targets
from scsi.research.models import ForecastEngine
from scsi.research.evaluation import select_validation,evaluate_origins,metrics,comparison
from scsi.research.claims import classify

CRITICAL_CODE=["config.py","features/asof.py","features/flow.py","research/data.py","research/models.py","research/evaluation.py","research/bootstrap.py","research/claims.py","research/pipeline.py"]

def input_hashes(root):
    root=Path(root)
    paths=[root/"data/curated/official_teu_monthly.parquet",root/"data/curated/portwatch_daily.parquet",root/"RESEARCH_PROTOCOL.md",root/"configs/project.yaml"]
    paths += [root/"src/scsi"/f for f in CRITICAL_CODE]
    # Freeze the exact H1 acquisition manifests, not later literature/operational catalog receipts.
    paths += [root/"data/manifests/source_targets.json",root/"data/manifests/source_flow.json"]
    paths += sorted((root/"data/geography").glob("gateway_crosswalk*"))
    return {str(p.relative_to(root)).replace("\\","/"):sha256(p) for p in paths if p.is_file()}

def load_inputs(root,release_lag=60,gateways=None):
    root=Path(root)
    raw_t=pd.read_parquet(root/"data/curated/official_teu_monthly.parquet")
    raw_d=pd.read_parquet(root/"data/curated/portwatch_daily.parquet")
    targets,_=prepare_targets(raw_t,release_lag,gateways)
    return normalized_daily(raw_d),targets

def experiment_specs():
    specs=[{"experiment_id":f"lag{lag}_release{release}","flow_lag_days":lag,"target_release_lag_days":release,"gateways":GATEWAYS,"role":"primary" if (lag,release)==(7,60) else "reporting_lag_sensitivity"} for lag in (7,14,28) for release in (60,90)]
    specs += [{"experiment_id":f"leave_out_{g}","flow_lag_days":7,"target_release_lag_days":60,"gateways":[x for x in GATEWAYS if x!=g],"role":"changed_target_gateway_exclusion"} for g in GATEWAYS]
    return specs

def build_features(root,config):
    root=Path(root);d,t=load_inputs(root)
    engine=ForecastEngine(d,t)
    rows=[]
    for m,c in engine.context.items():
        rows.append({"month":m.strftime("%Y-%m"),"valid":c["valid"],"reason":c["reason"],"cutoff":c["cutoff"].isoformat(),"features":c["values"],"latest_training_target":str(c["latest_training_target"])})
    # Structural coverage is not model-performance inspection.
    out={"status":"complete","available_days":len(d),"gateway_columns":list(d.columns),"target_months":int(t.target_teu.notna().sum()),"contexts":rows,"performance_inspected":False}
    write_json(root/"artifacts/audit/flow_feature_coverage.json",out)
    return {k:v for k,v in out.items() if k!="contexts"}

def validate_models(root,config):
    root=Path(root);path=root/"artifacts/validation_selection.json";inputs=input_hashes(root)
    if path.exists():
        old=json.loads(path.read_text(encoding="utf-8"))
        if old["input_hashes"]!=inputs:raise RuntimeError("Validation inputs changed; preserve old selection and document pre-test correction")
        return {"status":"validated_existing","experiments":len(old["experiments"])}
    selections=[]
    for spec in experiment_specs():
        d,t=load_inputs(root,spec["target_release_lag_days"],spec["gateways"])
        engine=ForecastEngine(d,t,spec["flow_lag_days"],spec["gateways"])
        chosen=select_validation(engine)
        selections.append({**spec,**chosen})
        print(json.dumps({"stage":"F","experiment":spec["experiment_id"],"validation_alphas":chosen["alphas"],"selected_benchmark":chosen["selected_benchmark"]}),flush=True)
    artifact={"created_at_utc":utcnow(),"input_hashes":inputs,"test_outcomes_evaluated":False,"experiments":selections}
    write_json(path,artifact,immutable=True)
    ledger(root,"F","validation_complete",experiments=len(selections),selection_hash=sha256(path),test_results_opened=False)
    return {"status":"complete","experiments":len(selections),"selection_sha256":sha256(path)}

def lock_protocol(root,config):
    root=Path(root);path=root/"artifacts/protocol_lock.json"
    if path.exists():
        verify_lock(root);return {"status":"existing_valid_lock","sha256":sha256(path)}
    selection=root/"artifacts/validation_selection.json"
    if not selection.exists():raise RuntimeError("No validation selection; evaluation cannot be frozen")
    chosen=json.loads(selection.read_text(encoding="utf-8"))
    if chosen["input_hashes"]!=input_hashes(root):raise RuntimeError("Inputs changed since validation")
    # Pilot choices must be committed to a receipt before freezing; full-year processing may continue under it.
    pilot=root/"artifacts/audit/geo_pilot_freeze.json"
    if not pilot.exists():raise RuntimeError("Measurement pilot choices not frozen; Stage G blocked")
    first=json.loads((root/"artifacts/initial_protocol_lock.json").read_text())
    assert_hash(root/"PROJECT_BRIEF.md",first["brief_sha256"])
    assert_hash(root/"RESEARCH_PROTOCOL.md",first["protocol_sha256"])
    assert_hash(root/"configs/project.yaml",first["config_sha256"])
    lock={"created_at_utc":utcnow(),"protocol_version":"1.0","availability_mode":"current_vintage_pseudo_realtime","input_hashes":input_hashes(root),"validation_selection_sha256":sha256(selection),"measurement_pilot_freeze_sha256":sha256(pilot),"experiments":[{k:x[k] for k in ("experiment_id","flow_lag_days","target_release_lag_days","gateways","role","alphas","selected_benchmark")} for x in chosen["experiments"]],"test_results_opened":False,"test_period":"2024-01/2025-12","historical_exposure":"General historical knowledge and separately logged 2024 measurement-pilot trajectories; no test forecast metrics inspected before this lock","bias_correction":"none","prediction_intervals":"not_provided","optional_tonnage":"NOT_INCLUDED","crosswalk_ambiguity_sensitivity":"exclude NYNJ and explicitly change target; same as leave_out_new_york_new_jersey","time_shift_placebo":"diagnostic_only_future_calls_shifted_28_days; frozen primary alphas; forbidden_production","common_policy":"all_model_seasonal_fallback_on_incomplete_core_source_window","primary_metric":"composite_teu_wape"}
    write_json(path,lock,immutable=True)
    ledger(root,"G","final_protocol_locked",sha256=sha256(path),test_results_opened=False)
    return {"status":"locked","sha256":sha256(path)}

def verify_lock(root):
    root=Path(root);path=root/"artifacts/protocol_lock.json"
    if not path.exists():raise RuntimeError("evaluate-locked requires a valid protocol lock")
    lock=json.loads(path.read_text(encoding="utf-8"))
    for name,h in lock["input_hashes"].items():assert_hash(root/name,h)
    assert_hash(root/"artifacts/validation_selection.json",lock["validation_selection_sha256"])
    assert_hash(root/"artifacts/audit/geo_pilot_freeze.json",lock["measurement_pilot_freeze_sha256"])
    return lock

def evaluate_locked(root,config):
    root=Path(root);lock=verify_lock(root);locksha=sha256(root/"artifacts/protocol_lock.json")
    path=root/"artifacts/metrics/locked_results.json"
    if path.exists():
        old=json.loads(path.read_text())
        if old["protocol_sha256"]!=locksha:raise RuntimeError("Existing results have another protocol; never overwrite")
        for name,h in old["prediction_hashes"].items():assert_hash(root/name,h)
        return {"status":"verified_existing","claim_status":old["claim_status"]}
    all_results=[];prediction_hashes={};all_records=[]
    for spec in lock["experiments"]:
        d,t=load_inputs(root,spec["target_release_lag_days"],spec["gateways"])
        engine=ForecastEngine(d,t,spec["flow_lag_days"],spec["gateways"])
        filename=f"artifacts/predictions/{spec['experiment_id']}.json"
        per_receipt=root/f"artifacts/predictions/{spec['experiment_id']}.receipt.json"
        if (root/filename).exists() and per_receipt.exists():
            prior=json.loads(per_receipt.read_text())
            if prior["protocol_sha256"]!=locksha:raise RuntimeError("Partial predictions use another lock")
            assert_hash(root/filename,prior["sha256"])
            records=json.loads((root/filename).read_text())
        else:
            records=evaluate_origins(engine,pd.date_range("2024-01-01","2025-12-01",freq="MS"),spec["alphas"],locksha,list(lock["input_hashes"].values()))
            for r in records:r.update({"experiment_id":spec["experiment_id"],"target_release_lag_days":spec["target_release_lag_days"],"availability_mode":"current_vintage_pseudo_realtime","generated_at_utc":utcnow()})
            if (root/filename).exists():
                prior=json.loads((root/filename).read_text())
                without_time=lambda rows:[{k:v for k,v in r.items() if k!="generated_at_utc"} for r in rows]
                if without_time(prior)!=without_time(records):raise RuntimeError("Unreceipted partial predictions do not reproduce; preserve and investigate")
                records=prior
            else:
                write_json(root/filename,records,immutable=True)
            write_json(per_receipt,{"protocol_sha256":locksha,"sha256":sha256(root/filename),"records":len(records)},immutable=True)
        prediction_hashes[filename]=sha256(root/filename)
        summaries=[{"model_id":m,**metrics([r for r in records if r["model_id"]==m])} for m in MODELS]
        comparisons=comparison(records,spec["selected_benchmark"])
        common=[r for r in records if not r["fallback_used"]]
        valid_metrics=[{"model_id":m,**metrics([r for r in common if r["model_id"]==m])} for m in MODELS]
        years={str(y):[{"model_id":m,**metrics([r for r in records if r["model_id"]==m and r["target_month"].startswith(str(y))])} for m in MODELS] for y in (2024,2025)}
        all_results.append({**spec,"metrics":summaries,"comparisons":comparisons,"common_valid_feature_metrics":valid_metrics,"year_diagnostics":years,"prediction_artifact":filename,"prediction_sha256":prediction_hashes[filename]})
        all_records.extend(records)
        print(json.dumps({"stage":"H","experiment":spec["experiment_id"],"completed_forecast_records":len(records)}),flush=True)
    primary=next(x for x in all_results if x["role"]=="primary")
    primary_gate=classify(primary["comparisons"])
    robust_failed=any(c["relative_lift"]<=0 for x in all_results if x["role"]=="reporting_lag_sensitivity" for c in x["comparisons"])
    claim=classify(primary["comparisons"],robustness_undermines=robust_failed)
    result={"created_at_utc":utcnow(),"protocol_sha256":locksha,"claim_status":claim,"primary_gate_status":primary_gate,"reporting_lag_robustness_undermines":robust_failed,"primary_experiment":primary["experiment_id"],"experiments":all_results,"prediction_hashes":prediction_hashes,"full_policy_is_primary":True,"total_prediction_records":len(all_records),"n_independent_test_months":24,"no_publication":True}
    write_json(path,result,immutable=True)
    ledger(root,"H","locked_evaluation_completed",claim_status=claim,records=len(all_records),independent_months=24)
    return {"status":"complete","claim_status":claim,"records":len(all_records)}

def run_robustness(root,config):
    root=Path(root);lock=verify_lock(root)
    results=json.loads((root/"artifacts/metrics/locked_results.json").read_text())
    path=root/"artifacts/metrics/robustness.json"
    if path.exists():return {"status":"existing","receipt":str(path.relative_to(root))}
    d,t=load_inputs(root);primary=next(x for x in lock["experiments"] if x["role"]=="primary")
    base=ForecastEngine(d,t);a=base.forecast("2024-01-01","geography_ridge",primary["alphas"]["geography_ridge"])
    dd=d.copy();dd.loc[dd.index>=pd.Timestamp("2024-01-15")]=999999
    tt=t.copy();tt.loc[tt.index>=pd.Timestamp("2023-11-01"),["target_teu",*GATEWAYS]]*=100
    b=ForecastEngine(dd,tt).forecast("2024-01-01","geography_ridge",primary["alphas"]["geography_ridge"])
    # Jan2024 is a documented source fallback. Also challenge a valid-feature origin.
    valid_origin=next(pd.Timestamp(r["target_month"]+"-01") for r in json.loads((root/"artifacts/predictions/lag7_release60.json").read_text()) if r["model_id"]=="geography_ridge" and not r["fallback_used"])
    v=base.forecast(valid_origin,"geography_ridge",primary["alphas"]["geography_ridge"])
    cutoff=pd.Timestamp(v["feature_cutoff_utc"]).tz_localize(None)
    dd=d.copy();dd.loc[dd.index>=cutoff]=888888
    tt=t.copy();future=tt.available_at>pd.Timestamp(v["forecast_origin_utc"]);tt.loc[future,["target_teu",*GATEWAYS]]*=100
    w=ForecastEngine(dd,tt).forecast(valid_origin,"geography_ridge",primary["alphas"]["geography_ridge"])
    checks={"fallback_origin_invariant":a["prediction_teu"]==b["prediction_teu"],"valid_origin_invariant":v["prediction_teu"]==w["prediction_teu"],"valid_origin_parameters_invariant":v["model_parameters"]==w["model_parameters"]}
    if not all(checks.values()):raise RuntimeError("Critical future-data leakage check failed")
    shifted=d.copy();shifted.index=shifted.index-pd.Timedelta(days=28)
    placebo_engine=ForecastEngine(shifted,t)
    placebo=evaluate_origins(placebo_engine,pd.date_range("2024-01-01","2025-12-01",freq="MS"),primary["alphas"])
    for r in placebo:r.update({"forbidden_in_production":True,"diagnostic":"future_28day_time_shift_placebo"})
    write_json(root/"artifacts/audit/time_shift_placebo_forbidden.json",placebo,immutable=True)
    shares=t.loc["2024-01-01":"2025-12-01",GATEWAYS].sum()/t.loc["2024-01-01":"2025-12-01","target_teu"].sum()
    out={"created_at_utc":utcnow(),"future_append_tests":checks,"valid_test_origin":valid_origin.strftime("%Y-%m"),"lag_and_target_release_checks":[x["experiment_id"] for x in results["experiments"] if x["role"] in ("primary","reporting_lag_sensitivity")],"leave_one_out_changed_targets":[x["experiment_id"] for x in results["experiments"] if x["role"]=="changed_target_gateway_exclusion"],"ambiguity_exclusion":"leave_out_new_york_new_jersey","optional_tonnage":{"status":"NOT_APPLICABLE","reason":"No tonnage feature was included in the frozen primary or optional model"},"gateway_target_concentration":shares.to_dict(),"time_shift_placebo":{"forbidden_in_production":True,"metrics":[{"model_id":m,**metrics([r for r in placebo if r["model_id"]==m])} for m in MODELS]},"geometry_sensitivity":"Separate measurement audit; never used to retune H1"}
    write_json(path,out,immutable=True)
    ledger(root,"I","robustness_complete",future_append_checks=checks)
    return {"status":"complete","future_append_checks":checks}
