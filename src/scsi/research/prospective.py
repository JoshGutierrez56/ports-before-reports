"""Append-only shadow packets; no scheduler, no simulated prospective history.

A future operator must acquire both snapshots before that month's day-21 cutoff.
The command runs within the following UTC day and refuses already-known outcomes.
The packet is a separate prospective extension, never a change to the locked test.
"""
from pathlib import Path
import json
import pandas as pd
from scsi.config import GATEWAYS,MODELS
from scsi.provenance import sha256,assert_hash,write_json,utcnow,ledger
from scsi.features.asof import origin,utc
from scsi.features.flow import normalized_daily
from scsi.research.models import ForecastEngine
from scsi.research.pipeline import verify_lock

def validate_packet(packet,now):
    at=utc(packet["forecast_origin_utc"]);now=utc(now)
    if at!=origin(at.tz_localize(None)):
        raise ValueError("Prospective origin must be the exclusive start of UTC day 22")
    if not pd.Timedelta(0)<=now-at<pd.Timedelta(days=1):
        raise ValueError("Prospective packet must be created during the UTC day immediately following its cutoff")
    if packet.get("outcome_known",True):raise ValueError("Current-month outcome must be explicitly unknown")
    for role in ("flow","targets"):
        s=packet[role]
        if not s.get("retrieved_at_utc") or utc(s["retrieved_at_utc"])>at:
            raise ValueError("A snapshot acquired after the forecast cutoff is not admissible")
        if not s.get("sha256") or not s.get("manifest_path"):
            raise ValueError("Snapshots require a hash and acquisition receipt")
    return at

def safe_project_path(root,value):
    path=(root/value).resolve()
    if not path.is_relative_to(root.resolve()):raise ValueError("Snapshot paths must remain in this project")
    return path

def save_shadow_forecast(root,snapshot,now=None):
    root=Path(root);lock=verify_lock(root)
    packet_path=Path(snapshot);packet=json.loads(packet_path.read_text(encoding="utf-8"))
    at=validate_packet(packet,now or utcnow())
    paths={}
    for role in ("flow","targets"):
        s=packet[role];p=safe_project_path(root,s["path"]);assert_hash(p,s["sha256"])
        receipt=json.loads(safe_project_path(root,s["manifest_path"]).read_text(encoding="utf-8"))
        if receipt.get("sha256")!=s["sha256"] or receipt.get("retrieved_at_utc")!=s["retrieved_at_utc"]:
            raise ValueError("Prospective packet does not match its immutable acquisition receipt")
        paths[role]=p
    daily=normalized_daily(pd.read_parquet(paths["flow"]))
    t=pd.read_parquet(paths["targets"]).copy()
    required={"month","target_teu","available_at",*GATEWAYS}
    if not required.issubset(t.columns):raise ValueError("Prospective targets need the documented canonical monthly schema")
    t["month"]=pd.to_datetime(t.month).dt.to_period("M").dt.to_timestamp()
    if t.month.duplicated().any():raise ValueError("Duplicate prospective target month")
    t=t.set_index("month").sort_index();t["available_at"]=pd.to_datetime(t.available_at,utc=True)
    month=at.tz_localize(None).to_period("M").start_time
    full=pd.date_range(t.index.min(),month,freq="MS")
    t=t.reindex(full)
    if t.loc[t.index>=month,"target_teu"].notna().any():raise ValueError("Current-month target already present; cannot call this a shadow forecast")
    valid=t.target_teu.notna()
    if not t.loc[valid,GATEWAYS].sum(axis=1,min_count=3).eq(t.loc[valid,"target_teu"]).all():raise ValueError("Prospective target composition mismatch")
    if (t.loc[valid,"target_teu"]<=0).any():raise ValueError("Invalid target units/values")
    p=next(x for x in lock["experiments"] if x["role"]=="primary")
    engine=ForecastEngine(daily,t,p["flow_lag_days"])
    rows=[engine.forecast(month,m,p["alphas"].get(m,0),sha256(root/"artifacts/protocol_lock.json"),[packet[k]["sha256"] for k in ("flow","targets")]) for m in MODELS]
    if any(r is None for r in rows):raise ValueError("Insufficient released seasonal base for prospective forecast")
    output={"mode":"prospective_shadow_forecast","created_at_utc":utcnow(),"forecast_origin_utc":at.isoformat(),"actual_teu":None,"outcome_known":False,"source_packet_sha256":sha256(packet_path),"source_snapshots":packet,"historical_training_vintage":"Current snapshots known at this prospective cutoff; not a claim of archived earlier training vintages","predictions":rows,"scheduler_enabled":False}
    dest=root/f"artifacts/prospective/{month:%Y-%m}.json"
    if dest.exists():raise RuntimeError("Prospective forecast already recorded; append-only packets cannot be replaced")
    write_json(dest,output,immutable=True);ledger(root,"L","prospective_shadow_saved",month=f"{month:%Y-%m}",sha256=sha256(dest))
    return {"status":"saved","artifact":str(dest.relative_to(root)),"sha256":sha256(dest)}
