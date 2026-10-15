"""Synthetic source fixtures cannot enter empirical paths."""
import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest
from scsi.sources.official_teu import INDICATOR, parse_bts, parse_la_html
from scsi.sources.portwatch import reconcile_batches, validate_layer, complete_id_batch
from scsi.sources.operational import fetch,SOURCE_LINEAGES


def target_row(**changes):
    row=dict(id="synthetic",date="2020-01-01",indicator=INDICATOR,measure1="Los Angeles",value1="125.25",units="TEUs",source="synthetic fixture")
    return {**row,**changes}


@pytest.mark.parametrize("change",[{"units":"tons"},{"indicator":"Total TEUs"},{"indicator":"Loaded Export Containers at Select U.S. Ports in TEUs"}])
def test_sources_target_rejects_unit_or_definition_substitution(change):
    with pytest.raises(ValueError,match="loaded import TEUs"):
        parse_bts([target_row(**change)],"synthetic")


def test_sources_target_revisions_never_double_count():
    with pytest.raises(ValueError,match="Duplicate/revised"):
        parse_bts([target_row(),target_row(id="revised",value1="126")],"synthetic")


def test_sources_target_fractional_teus_and_month_retained():
    result=parse_bts([target_row()],"synthetic")
    assert result.teu.iloc[0]==125.25
    assert result.month.iloc[0]==pd.Timestamp("2020-01-01")
    assert result.direction.iloc[0]=="import" and result.load_status.iloc[0]=="loaded"
    assert result.first_release_at_utc.isna().all()


def test_sources_arcgis_count_and_duplicate_reconciliation():
    valid=[{"features":[{"attributes":{"ObjectId":2}},{"attributes":{"ObjectId":1}}]}]
    assert len(reconcile_batches(valid,[1,2]))==2
    with pytest.raises(ValueError,match="count/set"):
        reconcile_batches(valid,[1,2,3])
    with pytest.raises(ValueError,match="Duplicate"):
        reconcile_batches(valid+valid,[1,2])


def test_sources_transfer_limit_never_silent_truncation():
    with pytest.raises(ValueError,match="subdivide"):
        reconcile_batches([{"features":[{"attributes":{"ObjectId":1}}],"exceededTransferLimit":True}],[1,2])


def test_sources_transfer_limit_actually_subdivides_and_reconciles():
    calls=[]
    def query(name,params):
        ids=list(map(int,params['objectIds'].split(',')));calls.append(ids)
        return {'features':[{'attributes':{'ObjectId':i}} for i in ids[:2]],'exceededTransferLimit':len(ids)>2},{'snapshot_id':name}
    batches,receipts=complete_id_batch(query,[1,2,3,4,5],'synthetic')
    assert len(calls)>1 and len(receipts)==3
    assert len(reconcile_batches(batches,[1,2,3,4,5]))==5


def test_sources_schema_needs_container_calls_not_total():
    with pytest.raises(ValueError,match="container-specific"):
        validate_layer({"fields":[{"name":"portcalls","type":"esriFieldTypeInteger"}]})


def test_sources_resume_rejects_corrupted_cached_bytes(tmp_path):
    directory=tmp_path/"data/manifests/source_snapshots/synthetic";directory.mkdir(parents=True)
    path=directory/"object.json";path.write_text("changed")
    path.with_name(path.name+".receipt.json").write_text(json.dumps({"sha256":hashlib.sha256(b"original").hexdigest()}))
    with pytest.raises(ValueError,match="hash mismatch"):
        fetch(tmp_path,"synthetic","https://invalid.example/object","object.json")


def test_sources_resume_accepts_only_verified_cache_without_network(tmp_path):
    directory=tmp_path/"data/manifests/source_snapshots/synthetic";directory.mkdir(parents=True)
    path=directory/"object.json";path.write_bytes(b"original")
    path.with_name(path.name+".receipt.json").write_text(json.dumps({"sha256":hashlib.sha256(b"original").hexdigest(),"http_status":200}))
    actual,_=fetch(tmp_path,"synthetic","https://invalid.example/object","object.json")
    assert actual.read_bytes()==b"original"


def test_sources_html_rejects_total_import_header(tmp_path):
    path=tmp_path/"synthetic.html"
    path.write_text("<table><tr><td>Month</td><td>Total Imports</td></tr><tr><td>January</td><td>1</td></tr></table>")
    with pytest.raises(ValueError,match="Loaded Imports"):
        parse_la_html(path,2020)


def test_sources_mirror_is_same_measurement_lineage():
    assert SOURCE_LINEAGES['portwatch']==SOURCE_LINEAGES['portwatch_hdx']


def test_sources_interrupted_request_retries_and_atomic_resume(tmp_path,monkeypatch):
    import requests
    from scsi.sources import operational
    attempts=[]
    def response(*args,**kwargs):
        attempts.append(1)
        if len(attempts)==1:raise requests.ConnectionError('synthetic interruption')
        r=requests.Response();r.status_code=200;r._content=b'{"ok":true}';r.url='https://example.invalid/data'
        return r
    monkeypatch.setattr(operational.requests,'get',response)
    monkeypatch.setattr(operational.time,'sleep',lambda _:None)
    path,receipt=fetch(tmp_path,'synthetic','https://example.invalid/data','fixture.json')
    assert receipt['attempts']==2 and len(attempts)==2
    assert not path.with_name(path.name+'.partial').exists()
    fetch(tmp_path,'synthetic','https://example.invalid/data','fixture.json')
    assert len(attempts)==2


@pytest.mark.parametrize("retry_after,expected_delay",[
    ("Thu, 15 Oct 2026 20:02:05 GMT",125.0),
    ("125",125.0),
    ("invalid-date",2.25),
])
def test_sources_retry_after_waits_for_provider_deadline(tmp_path,monkeypatch,retry_after,expected_delay):
    """A long HTTP-date must not be truncated to 60s before the second request."""
    import requests
    from datetime import datetime, timezone
    from scsi.sources import operational
    start=datetime(2026,10,15,20,0,0,tzinfo=timezone.utc).timestamp()
    elapsed=[0.0];sleeps=[];request_times=[]
    def sleep(seconds):
        sleeps.append(seconds);elapsed[0]+=seconds
    def response(*args,**kwargs):
        request_times.append(elapsed[0])
        r=requests.Response();r.url='https://retry-fixture.invalid/data'
        r.status_code=429 if len(request_times)==1 else 200
        r.headers['Retry-After']=retry_after;r._content=b'{"ok":true}'
        return r
    monkeypatch.setattr(operational,'_LAST_REQUEST',{})
    monkeypatch.setattr(operational.time,'time',lambda:start+elapsed[0])
    monkeypatch.setattr(operational.time,'monotonic',lambda:1000+elapsed[0])
    monkeypatch.setattr(operational.time,'sleep',sleep)
    monkeypatch.setattr(operational.random,'uniform',lambda low,high:0.25)
    monkeypatch.setattr(operational.requests,'get',response)
    path,receipt=fetch(tmp_path,'synthetic','https://retry-fixture.invalid/data','fixture.json')
    assert request_times==pytest.approx([0.0,expected_delay])
    assert max(sleeps)<=60.0 and receipt['attempts']==2
    assert path.read_bytes()==b'{"ok":true}'


def test_sources_real_snapshot_contracts():
    root=Path(__file__).resolve().parents[2]
    path=root/"data/curated/portwatch_daily.parquet"
    if not path.exists():pytest.skip("Local source acquisition absent")
    flow=pd.read_parquet(path)
    target=pd.read_parquet(root/"data/curated/official_teu_monthly.parquet")
    assert len(flow)==7671 and not flow.duplicated(["source_port_id","observation_date"]).any()
    assert flow.port_calls.isna().sum()==9
    assert set(flow.loc[flow.port_calls.isna(),"observation_date"].dt.strftime('%Y-%m-%d'))=={'2022-05-12','2023-02-14','2024-01-09'}
    assert len(target)==336 and target.groupby('official_port_id').size().eq(84).all()
    assert target.units.eq('TEUs').all()
    assert target.first_release_at_utc.isna().all()
