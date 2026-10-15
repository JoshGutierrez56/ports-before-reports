import base64
import hashlib
import json
import pytest
from scsi.sources import noaa_points as n

class Response:
    def __init__(self,status=200,body=b"bad",headers=None):self.status=status;self.body=body;self.headers=headers or {};self.read_called=False
    def __enter__(self):return self
    def __exit__(self,*a):pass
    def read(self,*a):self.read_called=True;body=self.body;self.body=b"";return body

def test_ignored_resume_range_aborts_before_body(tmp_path,monkeypatch):
    target=tmp_path/"source.parquet";target.with_suffix(".partial").write_bytes(b"x")
    head=Response(headers={"Content-Length":"10","ETag":"fixed"});body=Response(status=200,body=b"national data must not be consumed")
    monkeypatch.setattr(n,"_request",lambda url,method="GET",headers=None:head if method=="HEAD" else body)
    monkeypatch.setattr(n,"_budget",lambda *a:None)
    with pytest.raises(RuntimeError,match="Resume refused"):n._download(tmp_path,{},"2024-01-01",target)
    assert not body.read_called

def test_retained_source_hash_mismatch_rejected(tmp_path,monkeypatch):
    target=tmp_path/"source.parquet";target.write_bytes(b"abc")
    head=Response(headers={"Content-Length":"3","ETag":"fixed","Content-MD5":base64.b64encode(hashlib.md5(b"xyz").digest()).decode()})
    monkeypatch.setattr(n,"_request",lambda *a,**k:head);monkeypatch.setattr(n,"_budget",lambda *a:None)
    with pytest.raises(ValueError,match="hash changed"):n._download(tmp_path,{},"2024-01-01",target)

def test_gate_required_before_bulk(tmp_path):
    with pytest.raises(RuntimeError,match="bulk gate closed"):n.acquire_ais(tmp_path,{},True)

def test_full_year_requires_pilot_freeze(tmp_path):
    p=tmp_path/"artifacts/audit";p.mkdir(parents=True)
    (p/"geo_feasibility_gate.json").write_text(json.dumps({"target_and_portwatch_checked":True}))
    with pytest.raises(RuntimeError,match="validated pilot freeze"):n.acquire_ais(tmp_path,{},False)

def test_accounting_does_not_double_count_cumulative_receipt(tmp_path):
    n.ledger(tmp_path,"network_transfer",network_bytes=123)
    n.ledger(tmp_path,"pilot_frozen",network_bytes=123)
    n.ledger(tmp_path,"network_accounting_correction",network_bytes=-123)
    assert n._network_bytes(tmp_path)==123

def test_empty_spatial_crop_has_stable_string_schema(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq
    from shapely.geometry import Point
    import pandas as pd
    source=tmp_path/"source.parquet";target=tmp_path/"crop.parquet"
    table=pa.table(dict(mmsi=[123456789],base_date_time=pd.to_datetime(["2024-01-01"]),sog=[0.1],cog=[20.],vessel_type=[70],geometry=[Point(0,0).wkb]))
    table=table.replace_schema_metadata({b"geo":json.dumps({"columns":{"geometry":{"geometry_types":["Point"],"crs":{"id":{"code":4326}}}}}).encode()})
    pq.write_table(table,source)
    receipt=n.crop_day(source,target,"2024-01-01")
    assert receipt["source_rows"]==1 and receipt["cropped_rows"]==0
    assert pq.read_schema(target).field("source_partition").type==pa.string()

def test_head_429_http_date_honored_then_recovers(tmp_path,monkeypatch):
    from email.utils import formatdate
    from urllib.error import HTTPError
    monkeypatch.setattr(n.time,"time",lambda:1000.)
    attempts=[];waits=[]
    def request(*args,**kwargs):
        attempts.append(args)
        if len(attempts)==1:raise HTTPError("https://example.invalid",429,"rate limited",{"Retry-After":formatdate(1125,usegmt=True)},None)
        return Response(headers={"Content-Length":"3"})
    monkeypatch.setattr(n,"_request",request);monkeypatch.setattr(n,"_sleep_retry",waits.append)
    assert n._head_metadata(tmp_path,"https://example.invalid")=={"Content-Length":"3"}
    assert waits==[125.] and len(attempts)==2

def test_get_429_numeric_deadline_not_truncated(tmp_path,monkeypatch):
    from urllib.error import HTTPError
    attempts=[];waits=[]
    def request(url,method="GET",headers=None):
        if method=="HEAD":return Response(headers={"Content-Length":"3","ETag":"fixed"})
        attempts.append(url)
        if len(attempts)==1:raise HTTPError(url,429,"rate limited",{"Retry-After":"125"},None)
        return Response(body=b"abc")
    monkeypatch.setattr(n,"_request",request);monkeypatch.setattr(n,"_budget",lambda *args:None);monkeypatch.setattr(n,"_sleep_retry",waits.append)
    target=tmp_path/"source.parquet"
    assert n._download(tmp_path,{},"2024-01-01",target)["byte_count"]==3
    assert waits==[125.] and target.read_bytes()==b"abc" and n._network_bytes(tmp_path)==3

def test_retry_sleep_chunks_without_shortening_and_backoff_has_jitter(monkeypatch):
    waits=[];monkeypatch.setattr(n.time,"sleep",waits.append)
    n._sleep_retry(125.5)
    assert waits==[60.,60.,5.5]
    monkeypatch.setattr(n.random,"uniform",lambda *args:.5)
    assert n._retry_delay("invalid",3)==8.5

def test_head_permanent_error_not_retried(tmp_path,monkeypatch):
    from urllib.error import HTTPError
    attempts=[]
    def request(*args,**kwargs):
        attempts.append(1);raise HTTPError("https://example.invalid",403,"forbidden",{},None)
    monkeypatch.setattr(n,"_request",request)
    with pytest.raises(HTTPError):n._head_metadata(tmp_path,"https://example.invalid")
    assert len(attempts)==1
