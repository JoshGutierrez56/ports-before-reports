"""Real NOAA measurement orchestration, audit sampling and de-identified exports."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import time
import os
import shutil
import numpy as np
import pandas as pd
import pyarrow.dataset as ds
from shapely.geometry import shape
from scsi.geo.cleaning import clean_points
from scsi.geo.geofences import build_geofences,classify_zones,LOCAL_CRS
from scsi.geo.episodes import reconstruct
from scsi.geo.coverage import daily_features
from scsi.features.friction import add_friction
from scsi.sources.noaa_points import _manifest_records, BBOXES, digest, ledger, utcnow

LABELS={"san_pedro_bay":"San Pedro Bay (Los Angeles + Long Beach)","new_york_new_jersey":"New York / New Jersey","savannah":"Savannah"}

EXECUTION_MODULES=("src/scsi/sources/noaa_points.py","src/scsi/geo/pipeline.py","src/scsi/geo/geofences.py","src/scsi/geo/cleaning.py","src/scsi/geo/episodes.py","src/scsi/geo/coverage.py","src/scsi/geo/finalize.py","src/scsi/features/friction.py")

def measurement_lineage(root,records):
    root=Path(root)
    protocol={name:digest(root/name) for name in ("RESEARCH_PROTOCOL.md","artifacts/initial_protocol_lock.json","artifacts/protocol_lock.json","artifacts/audit/geo_pilot_freeze.json") if (root/name).exists()}
    return dict(protocol_sha256=protocol.get("artifacts/protocol_lock.json"),protocol_artifact_sha256=protocol,
                source_snapshot_ids=[f'noaa_ais_2024_points-{r["day"]}-{r["sha256"][:16]}' for r in records],
                source_snapshots=[dict(snapshot_id=f'noaa_ais_2024_points-{r["day"]}-{r["sha256"][:16]}',source_id="noaa_ais_2024_points",day=r["day"],sha256=r["sha256"],cropped_sha256=r["cropped_sha256"],retrieved_at_utc=r["retrieved_at_utc"],availability_mode="retrospective_descriptive") for r in records])

def process_resource_snapshot(root):
    """Measured current-process values, distinct from configured resource caps."""
    result=dict(pid=os.getpid(),sampled_at_utc=utcnow(),process_cpu_seconds=time.process_time(),free_disk_bytes=shutil.disk_usage(root).free)
    import psutil
    import pyarrow
    process=psutil.Process()
    result.update(os_thread_count=process.num_threads(),logical_cpu_count=psutil.cpu_count(),physical_memory_bytes=psutil.virtual_memory().total,arrow_cpu_pool_threads=pyarrow.cpu_count(),arrow_io_pool_threads=pyarrow.io_thread_count(),thread_pool_environment={name:os.environ.get(name) for name in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS")})
    if hasattr(process,"cpu_affinity"):result["cpu_affinity"]=process.cpu_affinity()
    if os.name=="nt":
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_=[("cb",wintypes.DWORD),("PageFaultCount",wintypes.DWORD)]+[(name,ctypes.c_size_t) for name in ("PeakWorkingSetSize","WorkingSetSize","QuotaPeakPagedPoolUsage","QuotaPagedPoolUsage","QuotaPeakNonPagedPoolUsage","QuotaNonPagedPoolUsage","PagefileUsage","PeakPagefileUsage")]
        counters=Counters();counters.cb=ctypes.sizeof(counters)
        kernel=ctypes.WinDLL("kernel32");kernel.GetCurrentProcess.restype=wintypes.HANDLE
        psapi=ctypes.WinDLL("psapi");psapi.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
        if psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(),ctypes.byref(counters),counters.cb):
            result.update(working_set_bytes=counters.WorkingSetSize,process_lifetime_peak_working_set_bytes=counters.PeakWorkingSetSize,process_lifetime_peak_pagefile_bytes=counters.PeakPagefileUsage)
    return result

def _json_safe(obj):
    return json.loads(pd.DataFrame(obj).to_json(orient="records",date_format="iso")) if isinstance(obj,list) else obj

def read_cargo(root,days=None):
    records=_manifest_records(root)
    if days:records=[r for r in records if r["day"] in days]
    files=[str(Path(root)/r["crop_path"]) for r in records]
    if not files:raise RuntimeError("No verified real NOAA crops")
    fields=["mmsi","base_date_time","sog","cog","vessel_type","length","width","draft","longitude","latitude","gateway_id","source_partition"]
    table=ds.dataset(files,format="parquet").to_table(columns=fields,filter=(ds.field("vessel_type")>=70)&(ds.field("vessel_type")<=79),use_threads=False)
    return table.to_pandas(),records

def _draw_geometries(ax,geofences,gateway):
    colors={"anchorage":"#ec9e40","container_berth":"#3988a7","transit":"#bac5c9"}
    for f in geofences["features"]:
        pr=f["properties"]
        if pr.get("gateway_id")!=gateway or pr.get("zone") not in colors:continue
        geom=shape(f["geometry"])
        for part in getattr(geom,"geoms",[geom]):
            if part.geom_type!="Polygon":continue
            x,y=part.exterior.xy;ax.fill(x,y,facecolor=colors[pr["zone"]],alpha=.22,edgecolor=colors[pr["zone"]],linewidth=.4)

def trajectory_audit(root,p,geofences):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    root=Path(root);out=root/"artifacts/audit/geo_panels";out.mkdir(parents=True,exist_ok=True)
    p=p.copy();p["date"]=p.timestamp.dt.strftime("%Y-%m-%d")
    rows=[]; selected=[]
    for gateway in BBOXES:
        q=p.loc[p.gateway_id.eq(gateway)]
        candidates=[]
        for (mmsi,day),track in q.groupby(["mmsi","date"],sort=True):
            if len(track)<8:continue
            states=set(track.state)
            strata=[]
            if "ANCHORAGE_CANDIDATE" in states:strata.append("anchorage")
            if "BERTH_CANDIDATE" in states:strata.append("berth")
            if "TRANSIT" in states:strata.append("transit")
            if (track.interval_minutes>30).any():strata.append("missing_intervals")
            if track.left_censored.any():strata.append("left_censoring")
            changes=int(track.raw_state.ne(track.raw_state.shift()).sum())
            if changes>=8:strata.append("boundary_or_speed_jitter")
            if track.timestamp.max().hour>=23:strata.append("right_boundary")
            candidates.append((mmsi,day,track,strata,changes))
        used=set()
        # Deterministic round-robin strata, not selection by a favorable story.
        strata_order=["anchorage","berth","transit","boundary_or_speed_jitter","missing_intervals","left_censoring","right_boundary"]
        while len(used)<min(20,len(candidates)):
            progress=False
            for stratum in strata_order:
                available=[x for x in candidates if (x[0],x[1]) not in used and stratum in x[3]]
                if not available:continue
                example=available[0];used.add((example[0],example[1]));selected.append((gateway,stratum,example));progress=True
                if len(used)>=20:break
            if not progress:break
    palette={"ANCHORAGE_CANDIDATE":"#dc8b22","BERTH_CANDIDATE":"#207eac","TRANSIT":"#36535e","APPROACH":"#a3a6a8","PERSISTENCE_PENDING":"#b79cba","UNKNOWN_GAP":"#c12d4d"}
    for i,(gateway,stratum,(mmsi,day,track,strata,changes)) in enumerate(selected):
        audit_id=f"GEO-{i+1:03d}"
        fig,axes=plt.subplots(1,2,figsize=(10,4),layout="constrained")
        ax=axes[0];_draw_geometries(ax,geofences,gateway)
        # Never draw lines across >30minute gaps: missing track is not invented.
        segment=(track.interval_minutes.gt(30)|track.interval_minutes.isna()).cumsum()
        for _,part in track.groupby(segment):ax.plot(part.longitude,part.latitude,color="#61727a",lw=.7,alpha=.6)
        for state,part in track.groupby("state"):
            ax.scatter(part.longitude,part.latitude,s=4,color=palette.get(state,"gray"),label=state.replace("_CANDIDATE",""))
        ax.set_xlim(track.longitude.min()-.008,track.longitude.max()+.008);ax.set_ylim(track.latitude.min()-.008,track.latitude.max()+.008)
        ax.set_xlabel("Longitude (WGS84)");ax.set_ylabel("Latitude");ax.set_aspect(1/np.cos(np.radians(track.latitude.mean())))
        axes[1].scatter(track.timestamp.dt.hour+track.timestamp.dt.minute/60,track.sog,s=3,c=[palette.get(s,"gray") for s in track.state]);axes[1].axhline(1,color="#cf7931",ls="--",lw=.8);axes[1].set_xlabel("UTC hour");axes[1].set_ylabel("Reported speed (knots)");axes[1].set_ylim(-.2,max(3,float(track.sog.quantile(.99))+1))
        fig.suptitle(f"{audit_id} | {LABELS[gateway]} | {day} | {stratum}",fontsize=10)
        fig.text(.01,.01,"Actual NOAA cargo-vessel proxy points. Agent-assisted audit; no independent human validation.",fontsize=7)
        panel=out/f"{audit_id}.png";fig.savefig(panel,dpi=110);plt.close(fig)
        rows.append(dict(audit_id=audit_id,gateway_id=gateway,date=day,selected_stratum=stratum,available_strata=";".join(strata),point_count=len(track),state_changes=changes,large_gap_count=int(track.interval_minutes.gt(30).sum()),left_censored=bool(track.left_censored.any()),right_day_boundary=bool(track.timestamp.max().hour>=23),classification="cargo-vessel proxy",panel_path=panel.relative_to(root).as_posix(),private_trace_key=hashlib.sha256(f"{mmsi}:{day}".encode()).hexdigest()[:16],reviewer_type="agent_assisted",review_status="algorithmic_checks_complete;visual_review_pending",review_notes="Position/speed/persistence and gaps annotated; terminal corridors approximate; no verified stop reason"))
    table=pd.DataFrame(rows);table.to_csv(root/"artifacts/audit/geo_trajectory_audit.csv",index=False)
    # Contact sheets make every selected panel directly reviewable.
    from PIL import Image,ImageOps,ImageDraw
    for page in range((len(rows)+11)//12):
        canvas=Image.new("RGB",(1600,1800),"white")
        for j,row in enumerate(rows[page*12:(page+1)*12]):
            with Image.open(root/row["panel_path"]) as im:
                thumb=ImageOps.contain(im,(800,300));canvas.paste(thumb,((j%2)*800,(j//2)*300))
        canvas.save(out/f"contact-{page+1:02d}.png")
    return table

def _map_figures(root,p,geofences):
    import matplotlib.pyplot as plt
    output=[]
    for gateway in BBOXES:
        q=p.loc[p.gateway_id.eq(gateway)]
        fig,ax=plt.subplots(figsize=(8,7),layout="constrained");_draw_geometries(ax,geofences,gateway)
        sample=q.iloc[::max(1,len(q)//30000)]
        ax.scatter(sample.longitude,sample.latitude,s=.15,alpha=.15,c="#23414f",rasterized=True)
        ax.set(xlabel="Longitude (WGS84)",ylabel="Latitude",title=f"{LABELS[gateway]}\nObserved cargo-vessel proxy positions")
        ax.set_aspect(1/np.cos(np.radians(q.latitude.mean())))
        fig.text(.02,.01,"NOAA AIS 2024 / NOAA designated anchorages; interpreted candidate berth corridors. Not a live vessel map.",fontsize=7)
        name=Path(root)/f"artifacts/audit/geo_map_{gateway}.png";fig.savefig(name,dpi=150);plt.close(fig);output.append(name.name)
    return output

def _site_export(root,p,daily,geofences,records):
    q=p.copy();q["date"]=q.timestamp.dt.strftime("%Y-%m-%d")
    q["lon"]=(np.floor(q.longitude/.005)+.5)*.005;q["lat"]=(np.floor(q.latitude/.005)+.5)*.005
    cells=q.groupby(["gateway_id","date","lon","lat"]).agg(ping_count=("mmsi","size"),eligible_vessels=("mmsi","nunique")).reset_index()
    # Do not expose individual positions. Cell center, >=3 distinct cargo proxies.
    cells=cells.loc[cells.eligible_vessels>=3].sort_values(["gateway_id","date","ping_count"],ascending=[True,True,False]).groupby(["gateway_id","date"],sort=False).head(32)
    cols=["gateway_id","date","observed_arrivals","anchorage_hours","berth_hours","queue_stock","median_active_age_hours","completed_berth_median_hours","source_complete","ping_continuity","observed_hours_of_day","retained_invalid_observation_count","retained_invalid_observation_rate","quality_flags","friction_index"]
    result=dict(metadata=dict(sources=[dict(name="NOAA 2024 broadcast points",url="https://github.com/ocm-marinecadastre/ais-vessel-traffic",license="CC0-1.0"),dict(name="NOAA designated anchorages / Coast Pilot",url="https://coast.noaa.gov/arcgis/rest/services/OceanReports/DesignatedAnchorageAreas/MapServer",license="US federal source, attributed")],availability_mode="retrospective_descriptive",measurement_start=min(r["day"] for r in records),measurement_end=max(r["day"] for r in records),completed_source_days=len(records),expected_source_days=366,coverage_note="Source-partition completeness and ping continuity are proxies, not the percentage of all ships observed. Hours are bounded-interval lower estimates; queue candidates have unverified stop reasons.",geometry_version="scsi-geofences-v1",classification="cargo-vessel proxy; not confirmed containerships",map_aggregation="0.005-degree cells with at least 3 observed cargo proxies; at most 32 cells per gateway/day",units=dict(anchorage_hours="observed candidate vessel-hours",berth_hours="observed candidate vessel-hours",queue_stock="observed active candidates near UTC day end",median_active_age_hours="elapsed observed age, hours",observed_arrivals="observed persistent candidate-zone arrivals; not full port calls"),source_manifest_sha256=digest(Path(root)/"data/manifests/noaa_points.jsonl")),gateways=[dict(id=g,label=LABELS[g],bbox=b) for g,b in BBOXES.items()],daily=json.loads(daily[cols].to_json(orient="records")),cells=json.loads(cells.to_json(orient="records")),geofences=geofences)
    result["metadata"].update(measurement_lineage(root,records))
    result["metadata"]["geometry_sha256"]=digest(Path(root)/"data/geography/geofences_v1.geojson")
    path=Path(root)/"artifacts/audit/geo_site_data.json";temporary=path.with_suffix(".partial.json");temporary.write_text(json.dumps(result,allow_nan=False),encoding="utf8");temporary.replace(path)
    return path

def should_run_audit(root,requested=None):
    if requested is not None:return requested
    return not (Path(root)/"artifacts/audit/geo_pilot_freeze.json").exists()

def build_geospatial(root,config,pilot=False,run_sensitivity=True,run_audit=None,finalization_pending=False):
    root=Path(root);starttime=time.monotonic();out=root/"artifacts/audit";out.mkdir(parents=True,exist_ok=True)
    freeze=out/"geo_pilot_freeze.json"
    if freeze.exists():
        frozen=json.loads(freeze.read_text())
        if digest(root/"data/geography/geofences_v1.geojson")!=frozen["geometry_sha256"] or config["geospatial"]!=frozen["geospatial"]:raise RuntimeError("Frozen geospatial settings/geometry changed")
        if pilot:
            preserved=out/"geo_measurement_receipt_pilot_final.json"
            return json.loads(preserved.read_text()) if preserved.exists() else frozen["measurement_receipt"]
    run_audit=should_run_audit(root,run_audit)
    code_sha256={name:digest(root/name) for name in EXECUTION_MODULES}
    resources_before=process_resource_snapshot(root)
    pilot_days={x.strftime("%Y-%m-%d") for x in pd.date_range(config["scope"]["ais_start"],periods=14)} if pilot else None
    raw,records=read_cargo(root,days=pilot_days);source_days={r["day"] for r in records};start=min(source_days);end=max(source_days)
    if pilot and len(records)!=14:raise RuntimeError("Pilot freeze requires exactly 14 verified source days")
    geofences=build_geofences(root,config);clean,cleaning=clean_points(raw);del raw
    clean["zone"]=classify_zones(clean,geofences)
    settings=config["geospatial"]
    speed=settings["stationary_speed_knots"];minimum=settings["minimum_state_duration_minutes"];gap=settings["maximum_interpolation_gap_minutes"]
    points,intervals,episodes=reconstruct(clean,speed,minimum,gap)
    daily=daily_features(points,intervals,episodes,source_days,start,end,gap)
    daily=add_friction(daily,settings["trailing_standardization_days"],settings["minimum_standardization_days"])
    daily.to_csv(out/"geo_daily_features.csv",index=False);daily.to_parquet(out/"geo_daily_features.parquet",index=False)
    episodes.to_parquet(out/"geo_episodes.parquet",index=False)
    daily[["gateway_id","date","source_complete","eligible_ping_count","retained_invalid_observation_count","retained_invalid_observation_rate","ping_continuity","observed_hours_of_day","quality_flags"]].to_csv(out/"geo_coverage_calendar.csv",index=False)
    (out/"geo_cleaning_receipt.json").write_text(json.dumps(cleaning,indent=2),encoding="utf8")
    if run_sensitivity:
        sensitivity=[]
        scenarios=[("baseline",0,speed,gap),("buffer_100m",100,speed,gap),("buffer_250m",250,speed,gap),("speed_0.5kn",0,.5,gap),("speed_1.5kn",0,1.5,gap),("gap_15min",0,speed,15),("gap_60min",0,speed,60)]
        for name,buffer,sp,gp in scenarios:
            candidate=clean.copy()
            if buffer:candidate["zone"]=classify_zones(candidate,geofences,buffer)
            pp,ii,ee=reconstruct(candidate,sp,minimum,gp);dd=daily_features(pp,ii,ee,source_days,start,end,gp)
            for gateway,group in dd.groupby("gateway_id"):
                sensitivity.append(dict(scenario=name,gateway_id=gateway,buffer_m=buffer,speed_knots=sp,gap_minutes=gp,source_days=len(records),anchorage_hours=float(group.anchorage_hours.sum(min_count=1)),berth_hours=float(group.berth_hours.sum(min_count=1)),mean_queue_stock=float(group.queue_stock.mean()),valid_queue_days=int(group.queue_stock.notna().sum()),measurement_only=True))
        pd.DataFrame(sensitivity).to_csv(out/"geo_sensitivity.csv",index=False)
    maps=_map_figures(root,points,geofences)
    audit=trajectory_audit(root,points,geofences) if run_audit else None
    site=_site_export(root,points,daily,geofences,records)
    audit_rows=len(audit) if audit is not None else (len(pd.read_csv(out/"geo_trajectory_audit.csv")) if (out/"geo_trajectory_audit.csv").exists() else 0)
    receipt=dict(status="pilot_measured" if pilot else ("full_year_measured" if len(records)==366 else "partial_year_measured"),source_days=len(records),expected_days=366,cargo_proxy_points=len(clean),candidate_episodes=int(episodes.state.isin(["ANCHORAGE_CANDIDATE","BERTH_CANDIDATE"]).sum()),measurement_start=start,measurement_end=end,cleaning=cleaning,seconds=round(time.monotonic()-starttime,2),geometry_sha256=digest(root/"data/geography/geofences_v1.geojson"),daily_sha256=digest(out/"geo_daily_features.csv"),site_export_sha256=digest(site),audit_rows=audit_rows,maps=maps,classification="cargo-vessel proxy",availability_mode="retrospective_descriptive",forecast_design_unchanged=True)
    if code_sha256!={name:digest(root/name) for name in EXECUTION_MODULES}:raise RuntimeError("Measurement source changed during execution; rerun from retained crops")
    receipt.update(executed_code_sha256=code_sha256,code_hash_basis="Module files at build entry and exit; unchanged during this fresh-process execution",lineage=measurement_lineage(root,records),resource_limits_configured=config.get("resources",{}),resource_observations={"before":resources_before,"after":process_resource_snapshot(root)},audit_sha256=digest(out/"geo_trajectory_audit.csv"))
    receipt["finalization_status"]="pending" if finalization_pending else "not_requested"
    if finalization_pending:
        receipt["status"]="full_year_measured_pending_correction_review"
        exported=json.loads(site.read_text());exported["metadata"]["finalization_status"]="pending"
        temporary=site.with_suffix(".partial.json");temporary.write_text(json.dumps(exported,allow_nan=False),encoding="utf8");temporary.replace(site)
        receipt["site_export_sha256"]=digest(site)
    (out/"geo_measurement_receipt.json").write_text(json.dumps(receipt,indent=2),encoding="utf8")
    ledger(root,"measurement_build",**receipt)
    return receipt

def freeze_pilot(root,config):
    root=Path(root);freeze=root/"artifacts/audit/geo_pilot_freeze.json"
    if freeze.exists():return json.loads(freeze.read_text())
    p=root/"artifacts/audit/geo_measurement_receipt.json";r=json.loads(p.read_text())
    if r["source_days"]!=14 or not (root/"artifacts/audit/geo_tests_receipt.txt").exists():raise RuntimeError("Pilot measurement and adversarial checks required")
    from scsi.sources.noaa_points import _network_bytes
    import shutil
    result=dict(frozen_at_utc=utcnow(),source_days=14,geospatial=config["geospatial"],initial_geospatial_settings=config["geospatial"],thresholds_changed=False,geometry_sha256=digest(root/"data/geography/geofences_v1.geojson"),initial_geometry_sha256=digest(root/"data/geography/geofences_pilot_initial.geojson"),geometry_amendment="Before freeze: supplement interpreted LA/Savannah corridors with NOAA ENC; replace NY named-terminal hand-locators with NOAA ENC facility perimeters. Documented pilot visual undercoverage; no H1 outcomes.",decision="Retain initial 1kn / 30min persistence / 30min max gap; evaluate prespecified one-factor sensitivity separately. No H1 design change.",exposure="January 2024 measurement only",measurement_receipt=r,test_receipt_sha256=digest(root/"artifacts/audit/geo_tests_receipt.txt"),source_manifest_sha256=digest(root/"data/manifests/noaa_points.jsonl"),audit_sha256=digest(root/"artifacts/audit/geo_trajectory_audit.csv"),network_bytes=_network_bytes(root),free_disk_bytes=shutil.disk_usage(root).free,limitations="Approximate candidate berth/channel functional attribution; current-vintage geometry; missing artificial quay edges; bounded offshore sector; no independent human validation")
    freeze.write_text(json.dumps(result,indent=2),encoding="utf8")
    ledger(root,"pilot_frozen",**{k:v for k,v in result.items() if k!="network_bytes"},network_bytes_at_freeze=result["network_bytes"])
    return result

def compare_operational(root):
    root=Path(root);source=root/"data/curated/operational_waiting_stock_2024.parquet"
    if not source.exists():return {"status":"not_available"}
    reported=pd.read_parquet(source);reported["date"]=pd.to_datetime(reported.observation_date).dt.strftime("%Y-%m-%d")
    daily=pd.read_csv(root/"artifacts/audit/geo_daily_features.csv")
    matched=reported.merge(daily[["gateway_id","date","queue_stock","source_complete","quality_flags"]],on=["gateway_id","date"],how="inner")
    matched["comparison_status"]="descriptive_only;population_footprint_timeofday_differ;not_independent_ground_truth"
    matched.to_csv(root/"artifacts/audit/geo_operational_comparison.csv",index=False)
    summary=[]
    for gateway,group in matched.groupby("gateway_id"):
        valid=group.dropna(subset=["queue_stock","reported_waiting_stock"])
        summary.append(dict(gateway_id=gateway,matched_dates=len(group),valid_pairs=len(valid),noaa_candidate_mean=float(valid.queue_stock.mean()) if len(valid) else None,reported_stock_mean=float(valid.reported_waiting_stock.mean()) if len(valid) else None,comparison="descriptive stock consistency; different ship population/spatial footprint/time of day; no agreement claim"))
    (root/"artifacts/audit/geo_operational_summary.json").write_text(json.dumps(summary,indent=2),encoding="utf8")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,1,figsize=(10,6),layout="constrained")
    for ax,(gateway,group) in zip(axes,matched.groupby("gateway_id")):
        x=pd.to_datetime(group.date);ax.plot(x,group.reported_waiting_stock,"o",ms=3,label="BTS/MARAD reported waiting stock");ax.plot(x,group.queue_stock,"x",ms=4,label="NOAA bounded cargo-proxy candidates")
        ax.set_title(LABELS[gateway]);ax.set_ylabel("Vessels / candidates");ax.legend(fontsize=8)
    fig.suptitle("Descriptive consistency only: populations, area and time of day differ",fontsize=11)
    fig.savefig(root/"artifacts/audit/geo_operational_comparison.png",dpi=150);plt.close(fig)
    return summary
