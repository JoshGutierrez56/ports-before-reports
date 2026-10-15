"""Immutable snapshots, actual bytes and reproducible execution receipts."""
from pathlib import Path
import datetime as dt
import hashlib
import json
import os
import shutil
import psutil

def utcnow():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def sha256(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):
            h.update(b)
    return h.hexdigest()

def write_json(path,data,immutable=False):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    body=json.dumps(data,indent=2,ensure_ascii=False,default=str,allow_nan=False)+"\n"
    if immutable and path.exists():
        if path.read_text(encoding="utf-8") != body:
            raise RuntimeError(f"Immutable artifact would change: {path.name}")
        return path
    tmp=path.with_name(path.name+f".{os.getpid()}.tmp")
    tmp.write_text(body,encoding="utf-8",newline="\n"); tmp.replace(path)
    return path

def ledger(root,stage,event,**details):
    path=Path(root)/"artifacts/task_ledger.jsonl"
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("a",encoding="utf-8") as f:
        f.write(json.dumps({"timestamp":utcnow(),"stage":stage,"event":event,**details},default=str)+"\n")

def resource_check(root,config,required_bytes=0):
    root=Path(root)
    free=shutil.disk_usage(root).free
    reserve=config["resources"]["minimum_free_disk_gib"]*2**30
    if free-required_bytes < reserve:
        raise RuntimeError("Acquisition stopped before the free-disk reserve would be breached")
    return {"disk_free_bytes":free,"ram_available_bytes":psutil.virtual_memory().available,"checked_at_utc":utcnow()}

def assert_hash(path,expected):
    actual=sha256(path)
    if actual != expected:
        raise ValueError(f"Source/artifact hash mismatch: {Path(path).name}")
    return actual

def snapshot_record(path,source_id,source_url,terms_url,**extra):
    path=Path(path)
    return {"source_id":source_id,"snapshot_id":sha256(path)[:20],"retrieved_at_utc":utcnow(),"source_published_at_utc":None,"first_seen_at_utc":None,"source_url":source_url,"resolved_url":source_url,"etag":None,"last_modified":None,"sha256":sha256(path),"byte_count":path.stat().st_size,"row_count":None,"schema_hash":None,"terms_url":terms_url,"redistribution_status":"not_yet_reviewed","vintage_notes":"Retrieval does not prove historical release availability",**extra}
