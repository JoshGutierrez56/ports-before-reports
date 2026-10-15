"""Recompute all displayed forecast metrics from the small public real-output bundle.

This does not reacquire proprietary/raw source data or pretend to retrain from it.
Run from the extracted source bundle after installing its locked environment.
"""
from pathlib import Path
import json
import math
from scsi.research.evaluation import metrics,comparison
from scsi.provenance import write_json,utcnow

root=Path(__file__).resolve().parents[1]
data=json.loads((root/"data/public/site_data.json").read_text(encoding="utf-8"))
checked=[]
for saved in data["metrics"]:
    rows=[r for r in data["forecasts"] if r["experiment_id"]==saved["experiment_id"] and r["model_id"]==saved["model_id"]]
    calc=metrics(rows)
    for k,v in calc.items():
        if not math.isclose(v,saved[k],rel_tol=1e-12,abs_tol=1e-9):raise AssertionError(f"Metric mismatch: {saved['experiment_id']} / {saved['model_id']} / {k}")
    checked.append({"experiment_id":saved["experiment_id"],"model_id":saved["model_id"],"fields_reproduced":len(calc)})
rows=[r for r in data["forecasts"] if r["experiment_id"]=="lag7_release60"]
again=comparison(rows,data["selected_benchmark"])
if again!=data["comparisons"]:raise AssertionError("Primary block bootstrap/paired comparison does not reproduce")
receipt={"status":"reproduced_public_metrics","created_at_utc":utcnow(),"metric_rows":len(checked),"forecast_rows":len(data["forecasts"]),"primary_comparisons":len(again),"bootstrap_replicates_per_comparison_and_block":10000,"protocol_sha256":data["metadata"]["protocol_sha256"],"source_acquisition_or_refitting":False,"checks":checked}
write_json(root/"artifacts/audit/public_reproduction_receipt.json",receipt)
print(json.dumps({k:v for k,v in receipt.items() if k!="checks"},indent=2))
