"""Validated project configuration; critical choices are immutable after locking."""
from pathlib import Path
import hashlib
import json
import yaml

GATEWAYS = ["san_pedro_bay", "new_york_new_jersey", "savannah"]
MODELS = ["seasonal_naive", "released_target_ridge", "aggregate_activity_ridge", "geography_ridge", "simple_calls_to_teu"]

def load_config(path="configs/project.yaml"):
    path = Path(path).resolve()
    c = yaml.safe_load(path.read_text(encoding="utf-8"))
    if c["project"]["allow_remote_writes"] or c["project"]["allow_spending"]:
        raise ValueError("Remote writes and spending are prohibited by the contract")
    if c["scope"]["gateways"] != GATEWAYS:
        raise ValueError("Locked gateway definitions cannot be substituted")
    r = c["research"]
    required = {"locked_test_years":[2024,2025],"validation_years":[2023],"development_years":[2020,2021,2022],"ridge_alphas":[1.,10.,100.],"shipping_windows_days":[7,28],"mandatory_models":MODELS,"bootstrap_replicates":10000,"bootstrap_block_months":[3,6]}
    for k,v in required.items():
        if r[k] != v:
            raise ValueError(f"Research-critical {k} differs from supplied protocol")
    if r["max_core_feature_columns"] > 12 or c["resources"]["max_threads"] > 8:
        raise ValueError("Contract resource/feature budget exceeded")
    if c["scope"]["forecast_day"] != 21 or c["geospatial"]["retrospective_queue_matching_allowed_in_predictors"]:
        raise ValueError("Invalid cutoff or retrospective predictor contamination")
    if c["publishing"]["deploy"] or c["publishing"]["create_recurring_job"]:
        raise ValueError("Deployment/scheduling is not authorized")
    return c

def config_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def canonical_hash(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(",",":"),default=str,allow_nan=False).encode()).hexdigest()
