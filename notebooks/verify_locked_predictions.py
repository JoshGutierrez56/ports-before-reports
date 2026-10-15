"""Independent arithmetic audit, not an alternative forecasting implementation.

Reads frozen forecasts; never refits, selects, acquires data, or changes the lock.
The scalar bootstrap intentionally does not call scsi.research.bootstrap.
"""
from __future__ import annotations
import calendar
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import time

for variable in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
    os.environ[variable] = "1"
import numpy as np
import pandas as pd
import psutil

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def released(month, lag):
    year, number = map(int, month.split("-"))
    return datetime(year, number, calendar.monthrange(year, number)[1], tzinfo=timezone.utc) + timedelta(days=lag + 1)


def recalculate(rows):
    pairs = [r for r in rows if r["actual_teu"] is not None and r["prediction_teu"] is not None]
    error = [r["prediction_teu"] - r["actual_teu"] for r in pairs]
    denominator = math.fsum(r["actual_teu"] for r in pairs)
    sign = lambda value: (value > 0) - (value < 0)
    return {
        "n_months": len(pairs), "wape": math.fsum(abs(x) for x in error) / denominator,
        "mae": math.fsum(abs(x) for x in error) / len(pairs),
        "rmse": math.sqrt(math.fsum(x*x for x in error) / len(pairs)),
        "bias": math.fsum(error) / len(pairs),
        "direction_accuracy": sum(sign(r["prediction_teu"] - r["seasonal_base_teu"]) == sign(r["actual_teu"] - r["seasonal_base_teu"]) for r in pairs) / len(pairs),
        "fallback_rate": sum(r["fallback_used"] for r in rows) / len(rows),
        "source_coverage_rate": sum(r["source_features_valid"] for r in rows) / len(rows),
        "denominator_teu": denominator, "total_origins": len(rows),
    }


def independent_bootstrap(rows, comparator, block):
    months = [f"{year}-{month:02d}" for year in (2024, 2025) for month in range(1, 13)]
    lookup = {(r["target_month"], r["model_id"]): r for r in rows}
    triples = []
    for month in months:
        candidate = lookup.get((month, "geography_ridge"), {})
        baseline = lookup.get((month, comparator), {})
        triples.append((candidate.get("actual_teu"), candidate.get("prediction_teu"), baseline.get("prediction_teu")))
    rng = np.random.default_rng(20261015 + block)
    lifts = []
    for _ in range(10000):
        starts = rng.integers(0, len(months)-block+1, size=math.ceil(len(months)/block))
        sampled = [triples[index] for start in starts for index in range(int(start), int(start)+block)][:len(months)]
        valid = [(y,c,b) for y,c,b in sampled if all(v is not None and math.isfinite(v) for v in (y,c,b))]
        denominator = math.fsum(y for y,_,_ in valid)
        candidate_error = math.fsum(abs(y-c) for y,c,_ in valid)
        baseline_error = math.fsum(abs(y-b) for y,_,b in valid)
        if denominator > 0 and baseline_error > 0:
            lifts.append(1 - candidate_error / baseline_error)
    lower, upper = np.quantile(lifts, [.025, .975])
    return {"block_months": block, "replicates": 10000, "valid_replicates": len(lifts), "lower": float(lower), "upper": float(upper)}


def main():
    started = time.monotonic()
    lock_path = ROOT/"artifacts/protocol_lock.json"
    result_path = ROOT/"artifacts/metrics/locked_results.json"
    lock, result = load(lock_path), load(result_path)
    assert digest(lock_path) == result["protocol_sha256"]
    assert digest(ROOT/"artifacts/validation_selection.json") == lock["validation_selection_sha256"]
    assert digest(ROOT/"artifacts/audit/geo_pilot_freeze.json") == lock["measurement_pilot_freeze_sha256"]
    for name, expected in lock["input_hashes"].items():
        assert digest(ROOT/name) == expected, name
    target = pd.read_parquet(ROOT/"data/curated/official_teu_monthly.parquet")
    assert target.first_release_at_utc.isna().all(), "Audit release calculation must be extended for verified releases"
    target["month_key"] = target.month.dt.strftime("%Y-%m")
    component_targets = target.groupby(["month_key", "gateway_id"]).teu.sum().to_dict()
    metric_checks, temporal_checks, reconstruction_errors, counts = [], 0, [], 0
    primary_records = None
    for experiment in result["experiments"]:
        artifact = ROOT/experiment["prediction_artifact"]
        assert digest(artifact) == result["prediction_hashes"][experiment["prediction_artifact"]]
        rows = load(artifact)
        assert len(rows) == 120 and len({(r["target_month"], r["model_id"]) for r in rows}) == 120
        counts += len(rows)
        if experiment["role"] == "primary":
            primary_records = rows
        for recorded in experiment["metrics"]:
            actual = recalculate([r for r in rows if r["model_id"] == recorded["model_id"]])
            deltas = {k: abs(v-recorded[k]) for k,v in actual.items()}
            for key, value in actual.items():
                assert math.isclose(value, recorded[key], rel_tol=1e-12, abs_tol=1e-8), (experiment["experiment_id"], key)
            metric_checks.append({"experiment_id":experiment["experiment_id"], "model_id":recorded["model_id"], "maximum_absolute_metric_difference":max(deltas.values())})
        for month in sorted({r["target_month"] for r in rows}):
            selected = [r for r in rows if r["target_month"] == month]
            assert len({r["fallback_used"] for r in selected}) == 1
            assert len({r["source_features_valid"] for r in selected}) == 1
            assert len({r["actual_teu"] for r in selected}) == 1
            if selected[0]["fallback_used"]:
                assert len({r["prediction_teu"] for r in selected}) == 1
        for row in rows:
            year, month = map(int, row["target_month"].split("-"))
            at = datetime(year, month, 22, tzinfo=timezone.utc)
            assert datetime.fromisoformat(row["forecast_origin_utc"]) == at
            assert datetime.fromisoformat(row["feature_cutoff_utc"]) == at - timedelta(days=experiment["flow_lag_days"])
            assert datetime.fromisoformat(row["training_label_cutoff"]) == at
            assert row["protocol_sha256"] == result["protocol_sha256"]
            official = math.fsum(component_targets[(row["target_month"], g)] for g in experiment["gateways"])
            assert math.isclose(row["actual_teu"], official, abs_tol=1e-8)
            base_month = f"{year-1}-{month:02d}"
            base = math.fsum(component_targets[(base_month,g)] for g in experiment["gateways"])
            assert math.isclose(row["seasonal_base_teu"], base, abs_tol=1e-8)
            assert released(base_month, experiment["target_release_lag_days"]) <= at
            for training_month in row["training_months"]:
                assert training_month < row["target_month"]
                y, m = map(int, training_month.split("-"))
                assert released(training_month, experiment["target_release_lag_days"]) <= at
                assert released(f"{y-1}-{m:02d}", experiment["target_release_lag_days"]) <= at
                # Even complete-month conversion calls precede origin after the selected source lag.
                assert released(training_month, experiment["flow_lag_days"]) <= at
                temporal_checks += 1
            params = row["model_parameters"]
            if row["model_id"].endswith("_ridge"):
                assert params["alpha"] == experiment["alphas"][row["model_id"]]
            if not row["fallback_used"] and row["model_id"].endswith("_ridge"):
                assert len(params["feature_names"]) <= 8
                growth = params["intercept"] + math.fsum(coef*(row["feature_values"][name]-mean)/scale for name,coef,mean,scale in zip(params["feature_names"],params["coefficients"],params["training_mean"],params["training_scale"]))
                reconstructed = base * math.exp(growth)
                difference = abs(reconstructed-row["prediction_teu"])
                assert math.isclose(reconstructed, row["prediction_teu"], rel_tol=1e-12, abs_tol=1e-7)
                reconstruction_errors.append(difference)
            assert row["interval_lower"] is None and row["interval_upper"] is None
    primary = next(e for e in result["experiments"] if e["role"] == "primary")
    bootstrap_checks = []
    for comparison in primary["comparisons"]:
        candidate = recalculate([r for r in primary_records if r["model_id"] == "geography_ridge"])
        baseline = recalculate([r for r in primary_records if r["model_id"] == comparison["comparator"]])
        assert math.isclose(1-candidate["wape"]/baseline["wape"], comparison["relative_lift"], abs_tol=1e-12)
        for saved in comparison["bootstrap"]:
            checked = independent_bootstrap(primary_records, comparison["comparator"], saved["block_months"])
            assert checked["valid_replicates"] == saved["valid_replicates"]
            assert all(math.isclose(checked[k],saved[k],abs_tol=1e-12) for k in ("lower","upper"))
            bootstrap_checks.append({"comparator":comparison["comparator"], **checked, "maximum_endpoint_difference":max(abs(checked[k]-saved[k]) for k in ("lower","upper"))})
    direct = next(c for c in primary["comparisons"] if c["comparator"] == "aggregate_activity_ridge")
    passes = all(c["relative_lift"] >= .05 and c["n_months"] >= 20 and all(b["lower"] > 0 for b in c["bootstrap"]) for c in primary["comparisons"])
    robust_failed = any(c["relative_lift"] <= 0 for e in result["experiments"] if e["role"] == "reporting_lag_sensitivity" for c in e["comparisons"])
    independent_claim = "NO_INCREMENTAL_LIFT" if direct["relative_lift"] <= 0 else "HISTORICAL_LIFT_SUPPORTED" if passes and not robust_failed else "PROMISING_BUT_UNCERTAIN"
    assert independent_claim == result["claim_status"]
    report = {
        "created_at_utc":datetime.now(timezone.utc).isoformat(), "status":"passed",
        "scope":"Separate arithmetic verification by an AI agent; not independent human review, model replication or source ground-truth validation",
        "protocol_sha256":digest(lock_path), "locked_results_sha256":digest(result_path),
        "audit_script_sha256":digest(Path(__file__)), "prediction_hashes":result["prediction_hashes"],
        "critical_input_hashes_verified":len(lock["input_hashes"]), "prediction_records_checked":counts,
        "metric_comparisons":metric_checks, "primary_bootstrap_comparisons":bootstrap_checks,
        "training_month_release_checks":temporal_checks, "serialized_ridge_predictions_reconstructed":len(reconstruction_errors),
        "maximum_ridge_prediction_difference_teu":max(reconstruction_errors),
        "common_fallback_and_target_pairing":"passed across all nine experiments",
        "independent_claim_status":independent_claim, "retuning_or_data_mutation":False,
        "critical_leakage_findings":[],
        "limitations":[
            "No historical first-release snapshots: release lags are assumptions, not proof of historical availability.",
            "July 2026 PortWatch revisions affect the current-vintage 2019-2025 reconstruction.",
            "Only 24 test months; 1080 forecasts across overlapping experiments are not 1080 independent observations.",
            "NOAA 2024 cargo-proxy measurements are separate descriptive evidence, never a forecast regressor.",
            "Temporal receipts and coefficient reconstruction do not independently re-train or certify every source observation.",
            "Historical market knowledge and measurement-pilot exposure mean this is not globally unseen or prospective research."
        ],
        "resource_review":{
            "audit_elapsed_seconds":time.monotonic()-started, "audit_rss_bytes":psutil.Process().memory_info().rss,
            "free_disk_bytes_at_audit":shutil.disk_usage(ROOT).free,
            "audit_processing":"One process; BLAS thread settings 1; 40,000 scalar bootstrap draws; no network or NOAA full-year load",
            "whole_project_resource_enforcement":"Reviewed configured 48 GiB RAM / 80 GiB project / 16 GiB raw cache / 20 GiB free reserve / 200 GiB network caps; this audit is not a full-run peak-memory monitor"
        }
    }
    path=ROOT/"artifacts/audit/independent_research_audit.json"
    path.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({k:report[k] for k in ("status","prediction_records_checked","training_month_release_checks","serialized_ridge_predictions_reconstructed","maximum_ridge_prediction_difference_teu","independent_claim_status")}))


if __name__ == "__main__":
    main()
