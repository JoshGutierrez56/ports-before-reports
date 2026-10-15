"""Offline, audited post-freeze software-correction rebuild from verified crops.

No requests or forecast outputs are read. Run only after the managed acquisition
and its initial measurement process have exited.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import numpy as np
import pandas as pd
from scsi.geo.pipeline import build_geospatial,compare_operational,process_resource_snapshot,EXECUTION_MODULES
from scsi.features.friction import add_friction
from scsi.sources.noaa_points import _manifest_records,_network_bytes,digest,ledger,utcnow,BBOXES

def _configure_measurement_resources(config):
    """Process-local computational limits, not machine or OpenClaw configuration."""
    import psutil
    import pyarrow
    from threadpoolctl import threadpool_limits
    settings=config.get("resources",{})
    workers=min(settings.get("max_threads",8),8,max(1,(psutil.cpu_count() or 2)//2))
    for name in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS"):
        os.environ[name]="1"
    threadpool_limits(limits=1)
    pyarrow.set_cpu_count(min(4,max(1,workers-2)));pyarrow.set_io_thread_count(1)
    process=psutil.Process()
    if hasattr(process,"cpu_affinity"):process.cpu_affinity(process.cpu_affinity()[:workers])
    memory_limit=min(settings.get("max_memory_gib",48)*1024**3,48*1024**3,psutil.virtual_memory().total//2)
    if process.memory_info().rss>memory_limit:raise RuntimeError("Measurement process exceeds analytical memory budget")

def _verified_source_records(root):
    records=_manifest_records(root)
    expected={d.strftime("%Y-%m-%d") for d in pd.date_range("2024-01-01","2024-12-31")}
    if len(records)!=366 or {r["day"] for r in records}!=expected:
        raise ValueError("Finalization requires exactly366 unique2024 partitions")
    for r in records:
        path=root/r["crop_path"]
        if path.stat().st_size!=r["cropped_bytes"] or digest(path)!=r["cropped_sha256"]:
            raise ValueError(f'Crop verification failed: {r["day"]}')
    return records

def _verified_frozen_inputs(root,config):
    out=root/"artifacts/audit"
    frozen=json.loads((out/"geo_pilot_freeze.json").read_text())
    if config["geospatial"]!=frozen["geospatial"] or digest(root/"data/geography/geofences_v1.geojson")!=frozen["geometry_sha256"]:
        raise ValueError("Frozen geospatial settings/geometry changed")
    audit=out/"geo_trajectory_audit.csv"
    if digest(audit)!=frozen["audit_sha256"]:raise ValueError("Reviewed pilot audit differs from frozen copy")
    rows=pd.read_csv(audit)
    if len(rows)!=60 or not rows.review_status.astype(str).str.contains("agent_visual_reviewed").all():
        raise ValueError("60 reviewed pilot audit rows required")
    return frozen

def _verified_daily_scope(root):
    daily=pd.read_csv(root/"artifacts/audit/geo_daily_features.csv")
    expected={(g,d.strftime("%Y-%m-%d")) for g in BBOXES for d in pd.date_range("2024-01-01","2024-12-31")}
    if len(daily)!=len(expected) or set(zip(daily.gateway_id,daily.date))!=expected or not daily.source_complete.all():
        raise ValueError("Accepted daily measurements must contain1098 unique complete gateway-days")
    return daily

def verify_accepted_measurement(root,config):
    """Verify an accepted build without mutating it or making network requests."""
    root=Path(root).resolve();out=root/"artifacts/audit"
    state=json.loads((out/"geo_finalization_state.json").read_text())
    receipt_path=out/"geo_measurement_receipt.json";receipt=json.loads(receipt_path.read_text())
    if state.get("status")!="completed" or receipt.get("finalization_status")!="completed":
        raise ValueError("Geospatial measurement finalization is not accepted")
    if receipt.get("status")!="full_year_measured" or receipt.get("source_days")!=366 or receipt.get("measurement_start")!="2024-01-01" or receipt.get("measurement_end")!="2024-12-31":
        raise ValueError("Accepted measurement must cover all366 documented2024source days")
    if digest(receipt_path)!=state.get("measurement_receipt_sha256"):
        raise ValueError("Accepted measurement receipt changed")
    for name,key in (("geo_daily_features.csv","daily_sha256"),("geo_site_data.json","site_export_sha256"),("geo_trajectory_audit.csv","audit_sha256")):
        if digest(out/name)!=receipt.get(key) or receipt.get(key)!=state.get(key):
            raise ValueError(f"Accepted measurement artifact changed: {name}")
    if digest(out/"geo_pilot_freeze.json")!=state.get("pilot_freeze_sha256"):
        raise ValueError("Accepted pilot freeze changed")
    frozen=_verified_frozen_inputs(root,config)
    if receipt.get("geometry_sha256")!=frozen["geometry_sha256"]:raise ValueError("Accepted measurement geometry changed")
    current_code={name:digest(root/name) for name in EXECUTION_MODULES}
    if receipt.get("executed_code_sha256")!=current_code or state.get("executed_code_sha256")!=current_code:
        raise ValueError("Accepted measurement code changed; use a separately audited rebuild")
    mode=state.get("acceptance_mode","corrected_legacy_full_year")
    if mode=="corrected_legacy_full_year":
        evidence=out/"geo_postfreeze_correction_receipt.json"
        if digest(evidence)!=receipt.get("postfreeze_correction_receipt_sha256") or digest(evidence)!=state.get("correction_receipt_sha256"):
            raise ValueError("Accepted measurement correction receipt changed")
        for item in json.loads(evidence.read_text()).get("preserved_artifacts",[]):
            if digest(root/item["preserved_path"])!=item["sha256"]:raise ValueError("Preserved pre-correction artifact changed")
    elif mode=="current_implementation_no_legacy_rebuild":
        evidence=out/"geo_build_acceptance_receipt.json"
    else:raise ValueError("Unknown geospatial acceptance mode")
    if receipt.get("acceptance_mode",mode)!=mode:raise ValueError("Measurement acceptance mode mismatch")
    for item in (receipt,state):
        if item.get("acceptance_receipt_path")!=evidence.relative_to(root).as_posix() or item.get("acceptance_receipt_sha256")!=digest(evidence):
            raise ValueError("Accepted measurement acceptance receipt changed")
    for name,expected in receipt.get("lineage",{}).get("protocol_artifact_sha256",{}).items():
        if digest(root/name)!=expected:raise ValueError("Accepted measurement protocol lineage changed")
    exported=json.loads((out/"geo_site_data.json").read_text())
    if exported["metadata"].get("finalization_status")!="completed" or exported["metadata"].get("source_manifest_sha256")!=digest(root/"data/manifests/noaa_points.jsonl"):
        raise ValueError("Accepted measurement source manifest changed")
    if exported["metadata"].get("completed_source_days")!=366 or exported["metadata"].get("measurement_start")!="2024-01-01" or exported["metadata"].get("measurement_end")!="2024-12-31":
        raise ValueError("Accepted site export has incomplete source-date metadata")
    _verified_daily_scope(root)
    records=_verified_source_records(root)
    expected_snapshots=[f'noaa_ais_2024_points-{r["day"]}-{r["sha256"][:16]}' for r in records]
    if receipt.get("lineage",{}).get("source_snapshot_ids")!=expected_snapshots:
        raise ValueError("Accepted measurement source snapshot identities changed")
    return receipt

def _accept_current_build(root,config,receipt):
    """Seal a current-code build honestly; no legacy correction is invented."""
    out=root/"artifacts/audit";_verified_frozen_inputs(root,config)
    _verified_source_records(root)
    if receipt.get("source_days")!=366 or receipt.get("measurement_start")!="2024-01-01" or receipt.get("measurement_end")!="2024-12-31":
        raise ValueError("Current measurement acceptance requires the full2024year")
    if receipt.get("executed_code_sha256")!={name:digest(root/name) for name in EXECUTION_MODULES}:
        raise ValueError("Current build execution code cannot be verified")
    if digest(out/"geo_daily_features.csv")!=receipt["daily_sha256"] or digest(out/"geo_site_data.json")!=receipt["site_export_sha256"]:
        raise ValueError("Current build outputs changed before acceptance")
    daily=_verified_daily_scope(root)
    expected=add_friction(daily,config["geospatial"]["trailing_standardization_days"],config["geospatial"]["minimum_standardization_days"]).friction_index
    if not np.isclose(daily.friction_index,expected,equal_nan=True,rtol=1e-10,atol=1e-10).all():
        raise ValueError("Current build friction differs from previous90valid-day rule")
    mode="current_implementation_no_legacy_rebuild"
    evidence=out/"geo_build_acceptance_receipt.json"
    evidence.write_text(json.dumps(dict(completed_at_utc=utcnow(),acceptance_mode=mode,measurement_only=True,thresholds_or_geometry_changed=False,legacy_outputs_rebuilt=False,preserved_legacy_artifacts=[],explanation="Fresh build or interrupted fresh-build acceptance using the corrected implementation. No historical legacy-output correction is claimed.",daily_sha256=receipt["daily_sha256"],executed_code_sha256=receipt["executed_code_sha256"],operational_comparison=compare_operational(root)),indent=2,allow_nan=False),encoding="utf8")
    exported=json.loads((out/"geo_site_data.json").read_text());exported["metadata"]["finalization_status"]="completed"
    (out/"geo_site_data.json").write_text(json.dumps(exported,allow_nan=False),encoding="utf8")
    receipt.update(status="full_year_measured",finalization_status="completed",acceptance_mode=mode,acceptance_receipt_path=evidence.relative_to(root).as_posix(),acceptance_receipt_sha256=digest(evidence),site_export_sha256=digest(out/"geo_site_data.json"))
    (out/"geo_measurement_receipt.json").write_text(json.dumps(receipt,indent=2,allow_nan=False),encoding="utf8")
    accepted=dict(status="completed",completed_at_utc=utcnow(),source_days=366,acceptance_mode=mode,acceptance_receipt_path=receipt["acceptance_receipt_path"],acceptance_receipt_sha256=receipt["acceptance_receipt_sha256"],measurement_receipt_sha256=digest(out/"geo_measurement_receipt.json"),daily_sha256=receipt["daily_sha256"],site_export_sha256=receipt["site_export_sha256"],executed_code_sha256=receipt["executed_code_sha256"],pilot_freeze_sha256=digest(out/"geo_pilot_freeze.json"),audit_sha256=receipt["audit_sha256"])
    (out/"geo_finalization_state.json").write_text(json.dumps(accepted,indent=2),encoding="utf8")
    ledger(root,"current_implementation_measurement_accepted",**accepted)
    return verify_accepted_measurement(root,config)

def build_accepted_geospatial(root,config):
    """Canonical resumable CLI stage; accepted evidence is never overwritten."""
    root=Path(root).resolve();out=root/"artifacts/audit";state=out/"geo_finalization_state.json"
    if state.exists() and json.loads(state.read_text()).get("status")=="completed":
        return verify_accepted_measurement(root,config)
    _verified_frozen_inputs(root,config);_verified_source_records(root)
    path=out/"geo_measurement_receipt.json"
    receipt=json.loads(path.read_text()) if path.exists() else {}
    if (out/"geo_pre_censor_correction/geo_preservation_receipt.json").exists():
        return finalize_measurement(root,config)
    full=receipt.get("source_days")==366 and receipt.get("status") in {"full_year_measured","full_year_measured_pending_correction_review"}
    current=receipt.get("executed_code_sha256")=={name:digest(root/name) for name in EXECUTION_MODULES}
    if full and not current:return finalize_measurement(root,config)
    _configure_measurement_resources(config)
    state.write_text(json.dumps(dict(status="pending",started_at_utc=utcnow(),acceptance_mode="current_implementation_no_legacy_rebuild"),indent=2),encoding="utf8")
    try:
        if not full:receipt=build_geospatial(root,config,pilot=False,run_audit=False,finalization_pending=True)
        return _accept_current_build(root,config,receipt)
    except BaseException as exc:
        state.write_text(json.dumps(dict(status="failed",failed_at_utc=utcnow(),error=str(exc),release_allowed=False),indent=2),encoding="utf8")
        ledger(root,"measurement_finalization_failed",error=str(exc),release_allowed=False)
        raise

def _preserve(root,config=None):
    out=root/"artifacts/audit";archive=out/"geo_pre_censor_correction";archive.mkdir(exist_ok=True)
    receipt=archive/"geo_preservation_receipt.json"
    if receipt.exists():
        saved=json.loads(receipt.read_text())
        for item in saved["artifacts"]:
            if digest(root/item["preserved_path"])!=item["sha256"]:raise ValueError("Preserved pre-correction artifact changed")
        return saved
    names=["geo_measurement_receipt.json","geo_daily_features.csv","geo_daily_features.parquet","geo_cleaning_receipt.json","geo_coverage_calendar.csv","geo_sensitivity.csv","geo_site_data.json","geo_operational_comparison.csv","geo_operational_comparison.png","geo_operational_summary.json"]
    names.extend(p.name for p in out.glob("geo_map_*.png"))
    files=[out/name for name in names if (out/name).exists()]
    if (out/"geo_episodes.parquet").exists():files.append(out/"geo_episodes.parquet")
    required_bytes=sum(p.stat().st_size for p in files)
    limits=(config or {}).get("resources",{});free=shutil.disk_usage(root).free
    project_bytes=sum(p.stat().st_size for p in root.rglob("*") if p.is_file())
    if free-required_bytes<limits.get("minimum_free_disk_gib",20)*1024**3:raise RuntimeError("Pre-correction archive would breach free-disk reserve")
    if project_bytes+required_bytes>limits.get("project_disk_cap_gib",80)*1024**3:raise RuntimeError("Pre-correction archive would breach project cap")
    artifacts=[]
    for name in names:
        source=out/name
        if not source.exists():continue
        target=archive/name
        if target.exists() and digest(target)!=digest(source):raise ValueError("Refusing to overwrite earlier preserved evidence")
        shutil.copy2(source,target)
        artifacts.append(dict(original_path=source.relative_to(root).as_posix(),preserved_path=target.relative_to(root).as_posix(),sha256=digest(target),bytes=target.stat().st_size))
    source=out/"geo_episodes.parquet"
    if source.exists():
        target=root/"data/raw_cropped/geo_pre_censor_correction_episodes.parquet"
        if target.exists() and digest(target)!=digest(source):raise ValueError("Refusing to replace preserved private episodes")
        shutil.copy2(source,target)
        artifacts.append(dict(original_path=source.relative_to(root).as_posix(),preserved_path=target.relative_to(root).as_posix(),sha256=digest(target),bytes=target.stat().st_size,private=True))
    saved=dict(preserved_at_utc=utcnow(),reason="Initial full-year worker loaded state engine before UNKNOWN_GAP left-censor software correction. Frozen geometry/settings and reviewed60 pilot audit unchanged.",artifacts=artifacts,copy_budget=dict(required_bytes=required_bytes,free_disk_before=free,project_bytes_before=project_bytes,actual_copied_bytes=sum(a["bytes"] for a in artifacts)))
    receipt.write_text(json.dumps(saved,indent=2),encoding="utf8")
    ledger(root,"pre_correction_outputs_preserved",receipt_sha256=digest(receipt),artifacts=len(artifacts))
    return saved

def _require_initial_full_measurement(root):
    out=root/"artifacts/audit";archive=out/"geo_pre_censor_correction"
    base=archive if (archive/"geo_preservation_receipt.json").exists() else out
    receipt=json.loads((base/"geo_measurement_receipt.json").read_text())
    if receipt.get("status")!="full_year_measured" or receipt.get("source_days")!=366 or receipt.get("measurement_start")!="2024-01-01" or receipt.get("measurement_end")!="2024-12-31":raise ValueError("Initial full-year measurement has not completed")
    if receipt.get("daily_sha256")!=digest(base/"geo_daily_features.csv"):raise ValueError("Initial full-year daily output does not match receipt")
    return receipt

def _legacy_calendar_friction(daily,window,minimum):
    """Auditable counterfactual of the pre-correction reference-window definition."""
    result=pd.Series(np.nan,index=daily.index,dtype=float)
    for _,group in daily.groupby("gateway_id",sort=False):
        group=group.sort_values("date")
        for position,(idx,current) in enumerate(group.iterrows()):
            history=group.iloc[:position]
            history=history.loc[pd.to_datetime(history.date)>=pd.Timestamp(current.date)-pd.Timedelta(days=window)]
            history=history.dropna(subset=["anchorage_hours","median_active_age_hours"])
            if len(history)<minimum or pd.isna(current.median_active_age_hours) or pd.isna(current.anchorage_hours):continue
            values=[]
            for column in ("anchorage_hours","median_active_age_hours"):
                x=np.log1p(history[column].to_numpy(dtype=float));median=np.median(x);scale=1.4826*np.median(np.abs(x-median))
                if scale==0:scale=float(np.std(x))
                if scale==0:scale=1.
                values.append((np.log1p(float(current[column]))-median)/scale)
            result.loc[idx]=np.mean(values)
    return result

def _correction_checks(before,after,config):
    """Accept only documented censor/window changes and conservative nullification."""
    close=lambda a,b:np.isclose(a.to_numpy(dtype=float),b.to_numpy(dtype=float),equal_nan=True,rtol=1e-10,atol=1e-10)
    for column in ("anchorage_hours","berth_hours"):
        if not close(before[column],after[column]).all():raise ValueError(f"Unexpected correction impact on {column}")
    allowed=(before.queue_stock.notna() & after.queue_stock.isna() & before.median_active_age_hours.notna() & after.median_active_age_hours.isna() & before.observed_hours_of_day.eq(24) & after.observed_hours_of_day.lt(24) & after.retained_invalid_observation_count.gt(0) & before.source_complete & after.source_complete)
    nullified=[]
    for column in ("queue_stock","median_active_age_hours"):
        changed=~close(before[column],after[column])
        if (changed & ~allowed.to_numpy()).any():raise ValueError(f"Undocumented correction impact on {column}")
    for key in after.index[allowed]:
        nullified.append(dict(gateway_id=key[0],date=key[1],previous_queue_stock=float(before.loc[key,"queue_stock"]),previous_active_age_hours=float(before.loc[key,"median_active_age_hours"]),valid_signal_hour_buckets=int(after.loc[key,"observed_hours_of_day"]),invalid_retained_observations=int(after.loc[key,"retained_invalid_observation_count"]),reason="Previously represented24hours included UNKNOWN-only bucket(s); conservative nullification, not zero"))
    if (after.observed_arrivals>before.observed_arrivals).fillna(False).any():raise ValueError("Left-censor correction unexpectedly increased observed candidate arrivals")
    settings=config["geospatial"];window=settings["trailing_standardization_days"];minimum=settings["minimum_standardization_days"]
    previous=before.reset_index();final=after.reset_index()
    legacy_initial=_legacy_calendar_friction(previous,window,minimum)
    legacy_final=_legacy_calendar_friction(final,window,minimum)
    expected_final=add_friction(final,window,minimum).friction_index
    if not close(previous.friction_index,legacy_initial).all():raise ValueError("Initial friction not reproduced by documented old calendar definition")
    if not close(final.friction_index,expected_final).all():raise ValueError("Corrected friction differs from previous90valid-day rule")
    comparison=final[["gateway_id","date"]].copy()
    comparison["initial_calendar_index"]=previous.friction_index
    comparison["calendar_index_on_corrected_daily_inputs"]=legacy_final
    comparison["valid_day_index_on_corrected_daily_inputs"]=expected_final
    comparison["coverage_input_effect"]=legacy_final-previous.friction_index
    comparison["valid_day_window_effect"]=expected_final-legacy_final
    return nullified,comparison

def _finalize_measurement(root,config):
    root=Path(root).resolve();out=root/"artifacts/audit"
    _require_initial_full_measurement(root)
    records=_manifest_records(root);expected={d.strftime("%Y-%m-%d") for d in pd.date_range("2024-01-01","2024-12-31")}
    if len(records)!=366 or {r["day"] for r in records}!=expected:raise ValueError("Finalization requires exactly366 unique2024 partitions")
    for r in records:
        path=root/r["crop_path"]
        if path.stat().st_size!=r["cropped_bytes"] or digest(path)!=r["cropped_sha256"]:raise ValueError(f'Crop verification failed: {r["day"]}')
    freeze_path=out/"geo_pilot_freeze.json";freeze_hash=digest(freeze_path);frozen=json.loads(freeze_path.read_text())
    audit=out/"geo_trajectory_audit.csv";audit_hash=digest(audit)
    if audit_hash!=frozen["audit_sha256"]:raise ValueError("Reviewed pilot audit differs from frozen copy")
    audit_rows=pd.read_csv(audit)
    if len(audit_rows)!=60 or not audit_rows.review_status.str.contains("agent_visual_reviewed").all():raise ValueError("60 reviewed pilot audit rows required")
    preserved=_preserve(root,config)
    ledger(root,"corrected_full_year_measurement_started",resource_observations=process_resource_snapshot(root),source_manifest_sha256=digest(root/"data/manifests/noaa_points.jsonl"),no_downloads=True)
    receipt=build_geospatial(root,config,pilot=False,run_audit=False,finalization_pending=True)
    comparison=compare_operational(root)
    before=pd.read_csv(out/"geo_pre_censor_correction/geo_daily_features.csv").set_index(["gateway_id","date"]).sort_index()
    after=pd.read_csv(out/"geo_daily_features.csv").set_index(["gateway_id","date"]).sort_index()
    if not before.index.equals(after.index):raise ValueError("Correction must retain same source-day/gateway scope")
    changed={}
    for column in after.select_dtypes(include="number").columns:
        if column not in before:continue
        a=before[column].to_numpy();b=after[column].to_numpy();mask=~np.isclose(a,b,equal_nan=True,rtol=1e-10,atol=1e-10)
        if mask.any():changed[column]=dict(changed_rows=int(mask.sum()),max_absolute_change=float(np.nanmax(np.abs(a-b))) if np.isfinite(a-b).any() else None)
    nullified,friction_check=_correction_checks(before,after,config)
    friction_path=out/"geo_friction_correction_comparison.csv";friction_check.to_csv(friction_path,index=False)
    if digest(freeze_path)!=freeze_hash or digest(audit)!=audit_hash:raise ValueError("Immutable pilot or reviewed audit changed")
    events=[json.loads(x) for x in (out/"geo_ledger.jsonl").read_text().splitlines()]
    resources=dict(known_response_body_bytes=_network_bytes(root),unmetered_discovery_reserve_bytes=sum(e.get("unmetered_small_discovery_upper_bound_bytes",0) for e in events),national_source_bytes=sum(r["byte_count"] for r in records),national_source_rows=sum(r["source_rows"] for r in records),retained_crop_bytes=sum(r["cropped_bytes"] for r in records),retained_crop_rows=sum(r["cropped_rows"] for r in records),retained_national_cache_bytes=sum(p.stat().st_size for p in (root/"data/raw_cropped/.national_cache").glob("*") if p.is_file()),retry_event_count=sum(e["event"] in {"download_retry","head_retry"} for e in events),free_disk_bytes=shutil.disk_usage(root).free)
    correction=dict(completed_at_utc=utcnow(),correction="After any invalid-position/unknown-speed marker, following candidate episode is left censored even if timestamp gap<=30min. Prior logic reset persistence but omitted this censor flag. Hourly coverage representation now excludes invalid-position/unknown-speed markers; all-unknown signals cannot establish zero queue. Added daily retained-invalid count/rate diagnostics. Friction uses previous90valid observations as frozen protocol9.5 requires, not valid observations inside90calendar days; no current/future input.",measurement_only=True,thresholds_or_geometry_changed=False,pilot_freeze_sha256=freeze_hash,preserved_artifacts=preserved["artifacts"],changed_daily_columns=changed,added_daily_columns=[c for c in after if c not in before],unaffected_core_columns=["anchorage_hours","berth_hours","queue_stock","median_active_age_hours"],operational_comparison=comparison,resources=resources,acquisition_retry_version_note="Managed acquisition worker loaded prior retry implementation; consult retry_event_count. Corrected HEAD/Retry-After implementation is for future resumes. No acquisition requests made by this finalizer.",executed_code_sha256=receipt["executed_code_sha256"])
    correction_path=out/"geo_postfreeze_correction_receipt.json"
    correction.update(coverage_nullified_days=nullified,friction_comparison_sha256=digest(friction_path),friction_comparison_method="Reproduce original calendar rule on original daily inputs; compare old calendar versus required90valid-day rule on identical corrected daily inputs; final index must match required rule")
    correction["unaffected_core_columns"]=["anchorage_hours","berth_hours"]+([] if nullified else ["queue_stock","median_active_age_hours"])
    correction_path.write_text(json.dumps(correction,indent=2,allow_nan=False),encoding="utf8")
    site=out/"geo_site_data.json";exported=json.loads(site.read_text());exported["metadata"]["finalization_status"]="completed"
    temporary=site.with_suffix(".partial.json");temporary.write_text(json.dumps(exported,allow_nan=False),encoding="utf8");temporary.replace(site)
    receipt.update(status="full_year_measured",finalization_status="completed",acceptance_mode="corrected_legacy_full_year",acceptance_receipt_path=correction_path.relative_to(root).as_posix(),acceptance_receipt_sha256=digest(correction_path),postfreeze_correction_receipt_sha256=digest(correction_path),pre_correction_outputs_preserved=True,resource_acquisition_summary=resources,finalization_resource_observations=process_resource_snapshot(root),site_export_sha256=digest(site))
    (out/"geo_measurement_receipt.json").write_text(json.dumps(receipt,indent=2,allow_nan=False),encoding="utf8")
    ledger(root,"corrected_full_year_measurement_completed",measurement_receipt_sha256=digest(out/"geo_measurement_receipt.json"),correction_receipt_sha256=digest(correction_path),source_days=366,resources=resources)
    return receipt

def finalize_measurement(root,config):
    root=Path(root).resolve();out=root/"artifacts/audit";state=out/"geo_finalization_state.json"
    if state.exists() and json.loads(state.read_text()).get("status")=="completed":
        return verify_accepted_measurement(root,config)
    state.write_text(json.dumps(dict(status="pending",started_at_utc=utcnow(),pid=__import__("os").getpid()),indent=2),encoding="utf8")
    try:
        _configure_measurement_resources(config)
        receipt=_finalize_measurement(root,config)
        accepted=dict(status="completed",completed_at_utc=utcnow(),source_days=366,acceptance_mode="corrected_legacy_full_year",acceptance_receipt_path=receipt["acceptance_receipt_path"],acceptance_receipt_sha256=receipt["acceptance_receipt_sha256"],measurement_receipt_sha256=digest(out/"geo_measurement_receipt.json"),daily_sha256=receipt["daily_sha256"],site_export_sha256=receipt["site_export_sha256"],correction_receipt_sha256=receipt["postfreeze_correction_receipt_sha256"],executed_code_sha256=receipt["executed_code_sha256"],pilot_freeze_sha256=digest(out/"geo_pilot_freeze.json"),audit_sha256=receipt["audit_sha256"])
        state.write_text(json.dumps(accepted,indent=2),encoding="utf8")
        ledger(root,"measurement_finalization_accepted",acceptance_receipt_sha256=digest(state),**accepted)
        return verify_accepted_measurement(root,config)
    except BaseException as exc:
        state.write_text(json.dumps(dict(status="failed",failed_at_utc=utcnow(),error=str(exc),release_allowed=False),indent=2),encoding="utf8")
        ledger(root,"measurement_finalization_failed",error=str(exc),release_allowed=False)
        raise

if __name__=="__main__":
    import yaml
    import pyarrow
    pyarrow.set_cpu_count(4);pyarrow.set_io_thread_count(1)
    print(json.dumps(finalize_measurement(Path.cwd(),yaml.safe_load(Path("configs/project.yaml").read_text())),indent=2),flush=True)
