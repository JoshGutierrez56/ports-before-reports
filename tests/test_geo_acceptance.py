"""Synthetic filesystem fixtures exercise immutable geospatial release replay."""
import json
from types import SimpleNamespace
import pandas as pd
import pytest
from scsi.features.friction import add_friction
from scsi.geo import finalize
from scsi.geo.pipeline import EXECUTION_MODULES
from scsi.sources.noaa_points import BBOXES,digest


@pytest.fixture
def current_build(tmp_path,monkeypatch):
    out=tmp_path/"artifacts/audit";out.mkdir(parents=True)
    def write(relative,body):
        path=tmp_path/relative;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(body) if not isinstance(body,str) else body)
        return path
    config={"geospatial":{"trailing_standardization_days":90,"minimum_standardization_days":30}}
    geometry=write("data/geography/geofences_v1.geojson",{"features":[]})
    audit=out/"geo_trajectory_audit.csv"
    pd.DataFrame({"audit_id":range(60),"review_status":"agent_visual_reviewed"}).to_csv(audit,index=False)
    write("artifacts/audit/geo_pilot_freeze.json",{"geospatial":config["geospatial"],"geometry_sha256":digest(geometry),"audit_sha256":digest(audit)})
    records=[]
    for day in pd.date_range("2024-01-01","2024-12-31"):
        day=day.strftime("%Y-%m-%d");path=write(f"data/raw_cropped/synthetic-{day}.parquet","synthetic hash-verification fixture only")
        records.append({"day":day,"crop_path":path.relative_to(tmp_path).as_posix(),"cropped_bytes":path.stat().st_size,"cropped_sha256":digest(path),"sha256":digest(path)})
    manifest=write("data/manifests/noaa_points.jsonl","\n".join(json.dumps(r) for r in records)+"\n")
    for name in EXECUTION_MODULES:write(name,"synthetic module hash fixture\n")
    daily=pd.DataFrame([{"gateway_id":g,"date":d.strftime("%Y-%m-%d"),"source_complete":True,"anchorage_hours":1.,"median_active_age_hours":0.} for g in BBOXES for d in pd.date_range("2024-01-01","2024-12-31")])
    add_friction(daily).to_csv(out/"geo_daily_features.csv",index=False)
    site=write("artifacts/audit/geo_site_data.json",{"metadata":{"finalization_status":"pending","source_manifest_sha256":digest(manifest),"completed_source_days":366,"measurement_start":"2024-01-01","measurement_end":"2024-12-31"}})
    receipt={"status":"full_year_measured_pending_correction_review","finalization_status":"pending","source_days":366,"measurement_start":"2024-01-01","measurement_end":"2024-12-31","geometry_sha256":digest(geometry),"daily_sha256":digest(out/"geo_daily_features.csv"),"site_export_sha256":digest(site),"audit_sha256":digest(audit),"executed_code_sha256":{name:digest(tmp_path/name) for name in EXECUTION_MODULES},"lineage":{"source_snapshot_ids":[f'noaa_ais_2024_points-{r["day"]}-{r["sha256"][:16]}' for r in records]}}
    write("artifacts/audit/geo_measurement_receipt.json",receipt)
    monkeypatch.setattr(finalize,"compare_operational",lambda root:{"status":"synthetic_test_not_available"})
    return tmp_path,config,receipt


def test_fresh_build_acceptance_does_not_invent_legacy_correction(current_build,monkeypatch):
    root,config,receipt=current_build
    (root/"artifacts/audit/geo_measurement_receipt.json").unlink()
    calls=[]
    monkeypatch.setattr(finalize,"build_geospatial",lambda *a,**kw:(calls.append(kw) or receipt))
    accepted=finalize.build_accepted_geospatial(root,config)
    assert len(calls)==1 and calls[0]["finalization_pending"]
    assert accepted["acceptance_mode"]=="current_implementation_no_legacy_rebuild"
    assert not (root/"artifacts/audit/geo_postfreeze_correction_receipt.json").exists()
    assert not (root/"artifacts/audit/geo_pre_censor_correction").exists()
    evidence=json.loads((root/accepted["acceptance_receipt_path"]).read_text())
    assert evidence["legacy_outputs_rebuilt"] is False


def test_accepted_cli_replay_is_read_only_and_never_rebuilds(current_build,monkeypatch):
    from scsi.cli import dispatch
    root,config,receipt=current_build
    accepted=finalize._accept_current_build(root,config,receipt)
    before={p.relative_to(root).as_posix():digest(p) for p in root.rglob("*") if p.is_file()}
    def forbidden(*a,**kw):raise AssertionError("An accepted build must not run again")
    monkeypatch.setattr(finalize,"build_geospatial",forbidden)
    monkeypatch.setattr(finalize,"finalize_measurement",forbidden)
    assert dispatch("build-geospatial",root,config,SimpleNamespace())==accepted
    assert before=={p.relative_to(root).as_posix():digest(p) for p in root.rglob("*") if p.is_file()}


@pytest.mark.parametrize("relative",[
    "artifacts/audit/geo_daily_features.csv",
    "artifacts/audit/geo_site_data.json",
    "artifacts/audit/geo_build_acceptance_receipt.json",
    "artifacts/audit/geo_trajectory_audit.csv",
    "artifacts/audit/geo_pilot_freeze.json",
    "src/scsi/geo/episodes.py",
    "data/manifests/noaa_points.jsonl",
    "data/raw_cropped/synthetic-2024-01-01.parquet",
])
def test_accepted_replay_rejects_changed_artifacts_and_sources(current_build,relative):
    root,config,receipt=current_build
    finalize._accept_current_build(root,config,receipt)
    state=root/"artifacts/audit/geo_finalization_state.json";before=state.read_bytes()
    path=root/relative;path.write_bytes(path.read_bytes()+b"\n ")
    with pytest.raises(ValueError):finalize.build_accepted_geospatial(root,config)
    assert state.read_bytes()==before


def test_accepted_replay_rejects_changed_geospatial_settings(current_build):
    root,config,receipt=current_build
    finalize._accept_current_build(root,config,receipt)
    config["geospatial"]["trailing_standardization_days"]=89
    with pytest.raises(ValueError,match="Frozen"):finalize.build_accepted_geospatial(root,config)


def test_fresh_acceptance_rejects_incomplete_daily_output_even_if_hash_matches(current_build):
    root,config,receipt=current_build
    path=root/"artifacts/audit/geo_daily_features.csv"
    pd.read_csv(path).iloc[:-1].to_csv(path,index=False)
    receipt["daily_sha256"]=digest(path)
    with pytest.raises(ValueError,match="1098 unique"):finalize._accept_current_build(root,config,receipt)


def test_unaccepted_current_build_resumes_without_remeasuring(current_build,monkeypatch):
    root,config,receipt=current_build
    def forbidden(*a,**kw):raise AssertionError("A complete current build only needs acceptance")
    monkeypatch.setattr(finalize,"build_geospatial",forbidden)
    accepted=finalize.build_accepted_geospatial(root,config)
    assert accepted["finalization_status"]=="completed"


def test_legacy_acceptance_replay_verifies_preserved_evidence(current_build):
    root,config,receipt=current_build
    receipt=finalize._accept_current_build(root,config,receipt)
    out=root/"artifacts/audit"
    preserved=out/"synthetic_preserved_daily.csv";preserved.write_text("preserved synthetic legacy fixture")
    evidence=out/"geo_postfreeze_correction_receipt.json"
    evidence.write_text(json.dumps({"preserved_artifacts":[{"preserved_path":preserved.relative_to(root).as_posix(),"sha256":digest(preserved)}]}))
    state_path=out/"geo_finalization_state.json";state=json.loads(state_path.read_text())
    for item in (receipt,state):
        item.update(acceptance_mode="corrected_legacy_full_year",acceptance_receipt_path=evidence.relative_to(root).as_posix(),acceptance_receipt_sha256=digest(evidence))
    receipt["postfreeze_correction_receipt_sha256"]=digest(evidence)
    receipt_path=out/"geo_measurement_receipt.json";receipt_path.write_text(json.dumps(receipt))
    state.update(correction_receipt_sha256=digest(evidence),measurement_receipt_sha256=digest(receipt_path))
    state_path.write_text(json.dumps(state))
    assert finalize.verify_accepted_measurement(root,config)==receipt
    preserved.write_text("tampered preserved evidence")
    with pytest.raises(ValueError,match="Preserved pre-correction"):finalize.verify_accepted_measurement(root,config)
