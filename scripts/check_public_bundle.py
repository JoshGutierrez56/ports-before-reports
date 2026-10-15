"""Exercise the portable public aggregate bundle in an isolated extraction directory."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import zipfile
from scsi.provenance import sha256,write_json,utcnow

root=Path(__file__).resolve().parents[1]
private_home=Path.home()
private_prefixes={str(private_home),private_home.as_posix(),json.dumps(str(private_home))[1:-1]}
bundle=root/"release/reviewed-source.zip";h=sha256(bundle)
manifest=json.loads((root/"release/source_bundle_manifest.json").read_text(encoding="utf-8"))
if manifest["sha256"]!=h or manifest["byte_count"]!=bundle.stat().st_size:raise ValueError("Source bundle differs from its manifest")
expected={r["path"]:r for r in manifest["members"]}
if len(expected)!=len(manifest["members"]):raise ValueError("Duplicate member in source manifest")
dest=root/"artifacts/public_bundle_smoke"/h[:16]
dest.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(bundle) as z:
    names=z.namelist()
    if len(set(names))!=len(names) or set(names)!=set(expected):raise ValueError("Archive member set differs from manifest")
    for member in z.infolist():
        name=member.filename.replace("\\","/")
        target=(dest/name).resolve()
        if not target.is_relative_to(dest.resolve()):raise ValueError("Archive member escapes extraction directory")
        if any(x in name for x in ["data/curated/","data/raw_cropped/","source_snapshots/","notebook_runtime/",".venv/","geo_episodes.parquet"]):raise ValueError("Private source/runtime file included in bundle")
        body=z.read(member)
        if len(body)!=expected[name]["bytes"] or hashlib.sha256(body).hexdigest()!=expected[name]["sha256"]:raise ValueError(f"Archive member hash mismatch: {name}")
        if name.endswith((".json",".csv",".py",".md",".yaml",".ipynb",".toml",".lock")):
            txt=body.decode("utf-8")
            if any(prefix in txt for prefix in private_prefixes):
                raise ValueError(f"Unnecessary private machine path in public file: {name}")
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists() and target.read_bytes()!=body:raise ValueError("Hash-keyed extraction directory changed")
        target.write_bytes(body)
    count=len(z.infolist())
code="import sys,runpy;from pathlib import Path;p=Path.cwd();sys.path.insert(0,str(p/'src'));import scsi;assert Path(scsi.__file__).resolve().is_relative_to(p);runpy.run_path(str(p/'scripts/reproduce_public.py'),run_name='__main__')"
result=subprocess.run([sys.executable,"-c",code],cwd=dest,capture_output=True,text=True,encoding="utf-8")
if result.returncode:raise RuntimeError(result.stderr)
actual=json.loads((dest/"artifacts/audit/public_reproduction_receipt.json").read_text(encoding="utf-8"))
receipt={"status":"passed","executed_at_utc":utcnow(),"source_zip_sha256":h,"archive_members_checked":count,"actual_extracted_source_import":True,"raw_sources_included":False,"private_machine_paths_found":False,"reproduced_forecast_rows":actual["forecast_rows"],"reproduced_metric_rows":actual["metric_rows"],"primary_comparisons":actual["primary_comparisons"],"environment":"Existing pinned project dependency environment; package code and inputs loaded from isolated public bundle, not a fresh dependency installation"}
write_json(root/"artifacts/audit/public_bundle_smoke_receipt.json",receipt)
print(json.dumps(receipt,indent=2))
