"""Execute evidence notebooks with an ephemeral project-local kernel only."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time

import nbformat
from nbclient import NotebookClient
from jupyter_client import KernelManager
from jupyter_client.kernelspec import KernelSpecManager

ROOT=Path(__file__).resolve().parents[1]
NOTEBOOKS=("01_measurement_audit.ipynb","02_locked_research.ipynb")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only",choices=NOTEBOOKS)
    args=parser.parse_args()
    expected=ROOT/".venv"/("Scripts/python.exe" if os.name=="nt" else "bin/python")
    if Path(sys.executable).resolve()!=expected.resolve():
        raise RuntimeError("Run with the project's .venv Python interpreter")
    runtime=ROOT/"artifacts/notebook_runtime";runtime.mkdir(parents=True,exist_ok=True)
    receipt_path=ROOT/"artifacts/audit/notebook_execution.json"
    previous=json.loads(receipt_path.read_text(encoding="utf8")) if receipt_path.exists() else {}
    receipts={r["notebook"]:r for r in previous.get("notebooks",[])}
    failure=None
    # TemporaryDirectory removes only its explicitly created subtree on exit.
    with tempfile.TemporaryDirectory(prefix="scsi-",dir=runtime) as temporary:
        local=Path(temporary);spec=local/"kernels/scsi-local";spec.mkdir(parents=True)
        (spec/"kernel.json").write_text(json.dumps({"argv":[str(expected),"-m","ipykernel_launcher","-f","{connection_file}"],"display_name":"SCSI project environment","language":"python"}),encoding="utf8")
        env=os.environ.copy()
        for key,value in {"JUPYTER_RUNTIME_DIR":str(local/"runtime"),"IPYTHONDIR":str(local/"ipython"),"MPLCONFIGDIR":str(local/"matplotlib"),"PYTHONUTF8":"1","MPLBACKEND":"Agg","OMP_NUM_THREADS":"1","MKL_NUM_THREADS":"1","OPENBLAS_NUM_THREADS":"1"}.items():
            env[key]=value
        for folder in ("runtime","ipython","matplotlib"):
            (local/folder).mkdir()
        for name in ([args.only] if args.only else NOTEBOOKS):
            path=ROOT/"notebooks"/name;before=digest(path)
            nb=nbformat.read(path,as_version=4)
            source_hash=hashlib.sha256(json.dumps([{"cell_type":c.cell_type,"source":c.source} for c in nb.cells],sort_keys=True).encode()).hexdigest()
            km=KernelManager(kernel_name="scsi-local",ip="127.0.0.1",kernel_spec_manager=KernelSpecManager(kernel_dirs=[str(local/"kernels")],ensure_native_kernel=False),connection_file=str(local/"runtime"/(name+".json")))
            started=time.monotonic();status="executed";error=None
            try:
                NotebookClient(nb,km=km,timeout=240,allow_errors=False).execute(cwd=str(ROOT),env=env)
            except Exception as exc:
                status="failed";error=type(exc).__name__;failure=exc
            finally:
                if km.has_kernel:
                    km.shutdown_kernel(now=True)
            # No hidden absolute runtime path is stored in notebook metadata.
            nb.metadata["kernelspec"]={"display_name":"SCSI project environment","language":"python","name":"scsi-local"}
            nbformat.write(nb,path)
            code=[c for c in nb.cells if c.cell_type=="code"]
            outputs=[o for c in code for o in c.get("outputs",[])]
            inputs={}
            if name.startswith("01_"):
                candidates=["artifacts/audit/geo_measurement_receipt.json","artifacts/audit/geo_finalization_state.json","artifacts/audit/geo_postfreeze_correction_receipt.json","artifacts/audit/geo_build_acceptance_receipt.json","artifacts/audit/geo_pilot_freeze.json","artifacts/audit/geo_daily_features.csv","artifacts/audit/geo_sensitivity.csv","artifacts/audit/geo_trajectory_audit.csv","artifacts/audit/geo_map_san_pedro_bay.png","data/geography/geofences_v1.geojson","src/scsi/geo/pipeline.py","src/scsi/geo/cleaning.py","src/scsi/geo/geofences.py","src/scsi/geo/episodes.py","src/scsi/geo/coverage.py","src/scsi/geo/finalize.py","src/scsi/features/friction.py"]
                measured=json.loads((ROOT/"artifacts/audit/geo_measurement_receipt.json").read_text(encoding="utf8"))
                for line in (ROOT/"data/manifests/noaa_points.jsonl").read_text(encoding="utf8").splitlines():
                    record=json.loads(line)
                    if record.get("day")==measured["measurement_start"] and "crop_path" in record:
                        candidates.append(record["crop_path"])
            else:
                candidates=["artifacts/protocol_lock.json","artifacts/metrics/locked_results.json","artifacts/predictions/lag7_release60.json","artifacts/audit/independent_research_audit.json","artifacts/figures/benchmark_comparison.png","artifacts/figures/actual_vs_predicted.png","artifacts/figures/availability_sensitivity.png"]
            for relative in candidates:
                if (ROOT/relative).exists():inputs[relative]=digest(ROOT/relative)
            receipts[name]={"notebook":name,"status":status,"executed_at_utc":datetime.now(timezone.utc).isoformat(),"elapsed_seconds":time.monotonic()-started,"source_cells_sha256":source_hash,"input_notebook_sha256":before,"executed_notebook_sha256":digest(path),"code_cells":len(code),"executed_code_cells":sum(c.execution_count is not None for c in code),"output_objects":len(outputs),"png_outputs":sum("image/png" in o.get("data",{}) for o in outputs),"error_type":error,"input_hashes":inputs}
            print(json.dumps({k:receipts[name][k] for k in ("notebook","status","code_cells","executed_code_cells","png_outputs")}),flush=True)
            if failure:break
    report={"status":"failed" if failure else "executed","kernel_scope":"ephemeral project-local .venv kernel; no global installation/configuration","runtime_cleaned":True,"network_acquisition":False,"notebooks":[receipts[name] for name in NOTEBOOKS if name in receipts]}
    receipt_path.write_text(json.dumps(report,indent=2)+"\n",encoding="utf8")
    if failure:
        raise RuntimeError("Notebook execution failed; inspect the saved notebook output and receipt") from failure


if __name__=="__main__":
    main()
