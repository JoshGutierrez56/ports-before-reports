import json
import pytest
from scsi.publishing.exports import public_safe
from scsi.research.prospective import validate_packet,safe_project_path

def packet():
    return {"forecast_origin_utc":"2026-11-22T00:00:00Z","outcome_known":False,
            "flow":{"retrieved_at_utc":"2026-11-21T22:00:00Z","sha256":"abc","manifest_path":"flow.json"},
            "targets":{"retrieved_at_utc":"2026-11-21T22:00:00Z","sha256":"def","manifest_path":"target.json"}}

def test_null_is_not_zero_in_public_export():
    x=public_safe({"observations":[{"queue_age":None,"verified_zero_queue":False}]})
    assert json.loads(json.dumps(x))["observations"][0]["queue_age"] is None

def test_public_source_url_is_not_a_windows_drive_path():
    assert public_safe({"url":"https://portwatch.imf.org/"})["url"].startswith("https://")

@pytest.mark.parametrize("x",[{"mmsi":"123456789"},{"nested":[{"imo":123}]},{"path":"C:\\private\\file"},{"path":"/Users/name/private"},{"secret":{"access_token":"hidden"}}])
def test_public_export_rejects_identifiers_and_local_paths(x):
    with pytest.raises(ValueError):public_safe(x)

def test_shadow_packet_requires_current_origin_not_backfilled_claim():
    validate_packet(packet(),"2026-11-22T01:00:00Z")
    with pytest.raises(ValueError,match="following its cutoff"):validate_packet(packet(),"2026-12-22T01:00:00Z")
    with pytest.raises(ValueError,match="following its cutoff"):validate_packet(packet(),"2026-11-21T23:00:00Z")

def test_shadow_rejects_after_cutoff_snapshot_and_known_outcome():
    x=packet();x["flow"]["retrieved_at_utc"]="2026-11-22T00:01:00Z"
    with pytest.raises(ValueError,match="after the forecast cutoff"):validate_packet(x,"2026-11-22T01:00:00Z")
    x=packet();x["outcome_known"]=True
    with pytest.raises(ValueError,match="unknown"):validate_packet(x,"2026-11-22T01:00:00Z")

def test_shadow_rejects_escape_from_project(tmp_path):
    with pytest.raises(ValueError,match="remain in this project"):safe_project_path(tmp_path,"../other_project/data.parquet")

def test_core_release_cannot_pass_with_only_ais_pilot(tmp_path,monkeypatch):
    from scsi.publishing import exports
    from scsi.provenance import write_json
    results={"claim_status":"REAL_DATA_BLOCKED","experiments":[]}
    monkeypatch.setattr(exports,"read_results",lambda root:(results,{}))
    monkeypatch.setattr(exports,"verify_public_evidence",lambda *args:None)
    write_json(tmp_path/"data/public/site_data.json",{"claim":{"status":"REAL_DATA_BLOCKED","text":exports.claim_text(results,{})}})
    write_json(tmp_path/"artifacts/metrics/robustness.json",{"future_append_tests":{"valid":True}})
    with pytest.raises(ValueError,match="actual raw-AIS measurement"):exports.verify_release(tmp_path,{})
    write_json(tmp_path/"artifacts/audit/geo_measurement_receipt.json",{"source_days":14,"measurement_start":"2024-01-01","measurement_end":"2024-01-14"})
    with pytest.raises(ValueError,match="all366"):exports.verify_release(tmp_path,{})


@pytest.fixture
def synthetic_public_evidence(tmp_path):
    """Synthetic publication-contract records, never empirical outputs."""
    from scsi.provenance import write_json
    from scsi.publishing.exports import FORECAST_FIELDS,LIMITS,claim_text,public_result_rows
    experiment={"experiment_id":"synthetic","role":"primary","flow_lag_days":7,"target_release_lag_days":60,"gateways":["synthetic_gateway"],"selected_benchmark":"synthetic_benchmark","metrics":[{"model_id":str(i),"wape":1.0} for i in range(5)],"comparisons":[],"year_diagnostics":{"synthetic":[]},"common_valid_feature_metrics":[],"prediction_artifact":"artifacts/predictions/synthetic.json"}
    predictions=[]
    for month in range(24):
        for model in range(5):
            row=dict.fromkeys(FORECAST_FIELDS)
            row.update(model_id=str(model),target_month=str(month),experiment_id="synthetic",prediction_teu=float(month+model),actual_teu=100.0)
            predictions.append(row)
    write_json(tmp_path/experiment["prediction_artifact"],predictions)
    results={"claim_status":"REAL_DATA_BLOCKED","primary_gate_status":"REAL_DATA_BLOCKED","reporting_lag_robustness_undermines":True,"protocol_sha256":"synthetic","prediction_hashes":{},"experiments":[experiment]}
    forecasts,metrics,sensitivity=public_result_rows(tmp_path,results)
    site={"metadata":{"protocol_sha256":"synthetic","prediction_hashes":{}},"claim":{"status":results["claim_status"],"text":claim_text(results,experiment),"limitations":LIMITS},"forecasts":forecasts,"metrics":metrics,"sensitivity":sensitivity,"comparisons":experiment["comparisons"],"primary_gate_status":results["primary_gate_status"],"reporting_lag_robustness_undermines":True,"selected_benchmark":experiment["selected_benchmark"]}
    return tmp_path,results,experiment,json.loads(json.dumps(site))


def test_public_evidence_exact_projection_passes(synthetic_public_evidence):
    from scsi.publishing.exports import verify_public_evidence
    verify_public_evidence(*synthetic_public_evidence)


@pytest.mark.parametrize("change,field",[
    (lambda x:x["forecasts"].__setitem__(0,x["forecasts"][1]),"forecasts"),
    (lambda x:x["forecasts"][0].pop("prediction_teu"),"forecasts"),
    (lambda x:x["forecasts"].append(x["forecasts"][0]),"forecasts"),
    (lambda x:x["metrics"].append(x["metrics"][0]),"metrics"),
    (lambda x:x["comparisons"].append({"relative_lift":1}),"comparisons"),
    (lambda x:x["sensitivity"][0]["year_diagnostics"].update(synthetic=[999]),"sensitivity"),
    (lambda x:x.update(primary_gate_status="HISTORICAL_LIFT_SUPPORTED"),"primary_gate_status"),
    (lambda x:x.update(selected_benchmark="geography_ridge"),"selected_benchmark"),
    (lambda x:x["metadata"].update(protocol_sha256="another study"),"metadata protocol_sha256"),
])
def test_public_evidence_rejects_tampered_display(synthetic_public_evidence,change,field):
    from scsi.publishing.exports import verify_public_evidence
    root,results,primary,site=synthetic_public_evidence
    change(site)
    with pytest.raises(ValueError,match=f"Public {field} differs from locked evidence"):
        verify_public_evidence(root,results,primary,site)


def test_source_bundle_is_reproducible_and_manifests_every_generated_member(tmp_path):
    import hashlib
    import zipfile
    import yaml
    from scsi.publishing.exports import make_source_bundle
    from scsi.provenance import write_json
    (tmp_path/"configs").mkdir()
    (tmp_path/"configs/project.yaml").write_text(yaml.safe_dump({"project":{"workspace_root":str(tmp_path),"website_repo":"private-local-site"}}),encoding="utf-8")
    write_json(tmp_path/"artifacts/protocol_lock.json",{"synthetic_test_fixture":True})
    write_json(tmp_path/"data/raw_cropped/private.json",{"mmsi":"123456789"})
    (tmp_path/"README.md").write_text("Synthetic packaging fixture, not empirical data.",encoding="utf-8")
    first=make_source_bundle(tmp_path)
    second=make_source_bundle(tmp_path)
    assert first==second
    expected={r["path"]:r for r in second["members"]}
    with zipfile.ZipFile(tmp_path/"release/reviewed-source.zip") as archive:
        assert set(archive.namelist())==set(expected)
        assert "data/raw_cropped/private.json" not in expected
        assert {"configs/project.template.yaml","BUNDLE_METADATA.json"}<=set(expected)
        assert yaml.safe_load(archive.read("configs/project.template.yaml"))["project"]=={"workspace_root":None,"website_repo":None}
        for name,row in expected.items():
            body=archive.read(name)
            assert len(body)==row["bytes"]
            assert hashlib.sha256(body).hexdigest()==row["sha256"]


def test_release_rejects_notebook_executed_against_old_measurement(tmp_path):
    from scsi.publishing.exports import verify_execution_receipts
    from scsi.provenance import write_json,sha256
    (tmp_path/"artifacts/test-results").mkdir(parents=True)
    (tmp_path/"artifacts/test-results/pytest.xml").write_text('<testsuites><testsuite tests="7" failures="0" errors="0" skipped="0"/></testsuites>')
    write_json(tmp_path/"artifacts/audit/geo_measurement_receipt.json",{"synthetic_fixture_days":14})
    rows=[]
    for name in ("01_measurement_audit.ipynb","02_locked_research.ipynb"):
        write_json(tmp_path/"notebooks"/name,{"synthetic_fixture":True})
        rows.append({"notebook":name,"status":"executed","code_cells":1,"executed_code_cells":1,"executed_notebook_sha256":sha256(tmp_path/"notebooks"/name),"input_hashes":{"artifacts/audit/geo_measurement_receipt.json":sha256(tmp_path/"artifacts/audit/geo_measurement_receipt.json")}})
    write_json(tmp_path/"artifacts/audit/notebook_execution.json",{"status":"executed","notebooks":rows})
    (tmp_path/"notebooks/verify_locked_predictions.py").write_text("# Synthetic acceptance-test fixture")
    write_json(tmp_path/"artifacts/metrics/locked_results.json",{"synthetic_fixture":True})
    write_json(tmp_path/"artifacts/audit/independent_research_audit.json",{"status":"passed","prediction_records_checked":1080,"audit_script_sha256":sha256(tmp_path/"notebooks/verify_locked_predictions.py"),"locked_results_sha256":sha256(tmp_path/"artifacts/metrics/locked_results.json")})
    assert verify_execution_receipts(tmp_path)["executed_notebooks"]==2
    write_json(tmp_path/"artifacts/audit/geo_measurement_receipt.json",{"synthetic_fixture_days":366})
    with pytest.raises(ValueError,match="Notebook input changed after execution"):
        verify_execution_receipts(tmp_path)
