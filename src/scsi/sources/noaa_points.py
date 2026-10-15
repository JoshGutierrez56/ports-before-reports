"""Bounded, hash-verified NOAA 2024 broadcast point acquisition (CC0).

Never assume Range is honored; status and Content-Range are checked before reading.
National files are temporary, cropped raw observations are retained. No forecast data.
"""
from __future__ import annotations
import base64
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
import threading
import random
from email.utils import parsedate_to_datetime
from concurrent.futures import ThreadPoolExecutor
import urllib.error
import urllib.request

BASE = "https://ocmgeodatastor1.blob.core.windows.net/marinecadastre/ais2024/"
README = "https://raw.githubusercontent.com/ocm-marinecadastre/ais-vessel-traffic/main/data/ais-broadcast-points-2024-readme.md"
GIB = 1024 ** 3
BBOXES = {
    "san_pedro_bay": (-118.42, 33.53, -118.02, 33.88),
    "new_york_new_jersey": (-74.28, 40.38, -73.75, 40.83),
    "savannah": (-81.23, 31.70, -80.65, 32.22),
}
_last_request = 0.0
_request_lock=threading.Lock()
_ledger_lock=threading.RLock()

def utcnow():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def ledger(root, event, **fields):
    p = Path(root) / "artifacts/audit/geo_ledger.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with _ledger_lock:
        with p.open("a", encoding="utf8") as f:
            f.write(json.dumps(dict(timestamp_utc=utcnow(), event=event, **fields), default=str) + "\n")

def _request(url, method="GET", headers=None):
    global _last_request
    with _request_lock:
        time.sleep(max(0, 1.01 - (time.monotonic() - _last_request)))
        _last_request = time.monotonic()
    req = urllib.request.Request(url, method=method, headers={"User-Agent": "SCSI-local-research/1.0", **(headers or {})})
    return urllib.request.urlopen(req, timeout=90)

def _retry_delay(header, attempt):
    """Never shorten a provider's numeric or HTTP-date Retry-After deadline."""
    value=(header or "").strip()
    if value.isascii() and value.isdigit():return float(value)
    if value:
        try:
            deadline=parsedate_to_datetime(value)
            if deadline.tzinfo is None:deadline=deadline.replace(tzinfo=dt.timezone.utc)
            return max(0.0,deadline.timestamp()-time.time())
        except (TypeError,ValueError,OverflowError):pass
    return 2**attempt+random.uniform(0,1)

def _sleep_retry(delay):
    while delay>0:
        interval=min(60.0,delay);time.sleep(interval);delay-=interval

def _retryable(exc):
    return not isinstance(exc,urllib.error.HTTPError) or exc.code==429 or 500<=exc.code<600

def _head_metadata(root,url,retries=5):
    for attempt in range(retries):
        try:
            with _request(url,"HEAD") as response:return dict(response.headers)
        except (urllib.error.URLError,TimeoutError,IOError) as exc:
            if not _retryable(exc) or attempt==retries-1:raise
            delay=_retry_delay(exc.headers.get("Retry-After") if isinstance(exc,urllib.error.HTTPError) else None,attempt)
            ledger(root,"head_retry",url=url,attempt=attempt+1,http_status=getattr(exc,"code",None),delay_seconds=delay,error=str(exc))
            _sleep_retry(delay)

def _network_bytes(root):
    path = Path(root) / "artifacts/audit/geo_ledger.jsonl"
    if not path.exists():
        return 0
    with _ledger_lock:
        records=[json.loads(x) for x in path.read_text().splitlines()]
        return sum(x.get("network_bytes",0) for x in records if x.get("event") not in {"pilot_frozen","network_accounting_correction"})

def _budget(root, config, extra=0):
    r = config.get("resources", {})
    if shutil.disk_usage(root).free - extra < r.get("minimum_free_disk_gib", 20) * GIB:
        raise RuntimeError("NOAA stopped: 20 GiB free-disk reserve would be breached")
    total = sum(p.stat().st_size for p in Path(root).rglob("*") if p.is_file())
    if total + extra > r.get("project_disk_cap_gib", 80) * GIB:
        raise RuntimeError("NOAA stopped: project disk cap")
    cache=Path(root)/"data/raw_cropped/.national_cache"
    cache_bytes=sum(p.stat().st_size for p in cache.glob("*") if p.is_file())
    if cache_bytes+extra>r.get("raw_cache_cap_gib",16)*GIB:
        raise RuntimeError("NOAA stopped: rolling national cache cap")
    # Reserve 2 GiB for non-NOAA sources; parent additionally enforces global total.
    if _network_bytes(root) + extra > (r.get("network_transfer_cap_gib", 200) - 2) * GIB:
        raise RuntimeError("NOAA stopped: cumulative network budget")

def audit_noaa(root, config):
    root = Path(root)
    out = root / "artifacts/audit"
    out.mkdir(parents=True, exist_ok=True)
    with _request(README) as response:
        doc = response.read(1024 * 1024)
    (out / "geo_noaa_readme.md").write_bytes(doc)
    ledger(root, "documentation_acquired", url=README, network_bytes=len(doc), sha256=hashlib.sha256(doc).hexdigest())
    url = BASE + "ais-2024-01-01.parquet"
    meta=_head_metadata(root,url,config.get("resources",{}).get("retries",5))
    size = int(meta["Content-Length"])
    # Explicit offsets work with old Azure blob API, suffix ranges may be ignored.
    with _request(url, headers={"Range": f"bytes={size-8}-{size-1}", "x-ms-version": "2020-10-02"}) as response:
        status = response.status
        if status == 206:
            footer = response.read(9)
            if len(footer) != 8 or footer[-4:] != b"PAR1":
                raise ValueError("Invalid Parquet trailer")
            ledger(root, "bounded_footer_probe", url=url, network_bytes=len(footer))
            meta["parquet_metadata_length"] = int.from_bytes(footer[:4], "little")
        else:
            footer = None  # close without consuming the national file
    report = dict(source_id="noaa_ais_2024_points", url=url, terms_url=README,
                  license="CC0-1.0", retrieved_at_utc=utcnow(), head=meta,
                  explicit_range_status=status, historical_availability="not established; archive modified 2025",
                  units="AIS cargo-vessel proxy, not confirmed containerships")
    if footer:
        length = meta["parquet_metadata_length"]
        with _request(url, headers={"Range": f"bytes={size-length-8}-{size-1}", "x-ms-version": "2020-10-02"}) as response:
            if response.status != 206:
                raise RuntimeError("Range status changed; aborting before body")
            tail = response.read(length + 9)
        ledger(root, "bounded_metadata_probe", network_bytes=len(tail), url=url)
        import io
        import pyarrow.parquet as pq
        schema = pq.ParquetFile(io.BytesIO(b"PAR1" + tail))
        report.update(schema=str(schema.schema_arrow), row_count=schema.metadata.num_rows,
                      row_groups=schema.metadata.num_row_groups,
                      geo_metadata=json.loads(schema.schema_arrow.metadata[b"geo"]))
        (out / "geo_noaa_parquet_footer.bin").write_bytes(tail)
    (out / "geo_noaa_access.json").write_text(json.dumps(report, indent=2), encoding="utf8")
    return report

def _manifest_records(root):
    p = Path(root) / "data/manifests/noaa_points.jsonl"
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []

def _download(root, config, day, target):
    url = BASE + f"ais-{day}.parquet"
    meta=_head_metadata(root,url,config.get("resources",{}).get("retries",5))
    expected = int(meta["Content-Length"])
    _budget(root, config, expected * 2)
    if target.exists():
        if target.stat().st_size != expected:
            raise ValueError("Retained national source size changed")
        md5 = hashlib.md5(target.read_bytes()).digest()
        if meta.get("Content-MD5") and base64.b64encode(md5).decode() != meta["Content-MD5"]:
            raise ValueError("Retained national source hash changed")
        return dict(url=url, etag=meta.get("ETag"), last_modified=meta.get("Last-Modified"),byte_count=expected,sha256=digest(target))
    partial = target.with_suffix(".partial")
    checkpoint = target.with_suffix(".partial.json")
    if checkpoint.exists():
        old = json.loads(checkpoint.read_text())
        if old["etag"] != meta.get("ETag") or old["byte_count"] != expected:
            raise ValueError(f"Changed NOAA source vintage at {url}; refusing replacement")
    checkpoint.write_text(json.dumps(dict(etag=meta.get("ETag"), byte_count=expected)), encoding="utf8")
    for attempt in range(config.get("resources", {}).get("retries", 5)):
        offset = partial.stat().st_size if partial.exists() else 0
        if offset == expected:
            break
        headers = {"x-ms-version": "2020-10-02"}
        if offset:
            headers.update(Range=f"bytes={offset}-{expected-1}", **{"If-Match": meta["ETag"]})
        actual = 0
        try:
            with _request(url, headers=headers) as response:
                if offset and (response.status != 206 or not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-")):
                    raise RuntimeError("Resume refused: server did not honor exact range")
                with partial.open("ab" if offset else "wb") as f:
                    for block in iter(lambda: response.read(4 * 1024 * 1024), b""):
                        actual += len(block)
                        f.write(block)
                        if offset + actual > expected:
                            raise RuntimeError("Source exceeded declared size")
            if partial.stat().st_size != expected:
                raise IOError("Interrupted NOAA transfer")
            break
        except (urllib.error.URLError, TimeoutError, IOError) as exc:
            if not _retryable(exc) or attempt == config.get("resources", {}).get("retries", 5) - 1:
                ledger(root,"download_failure",day=day,attempt=attempt+1,http_status=getattr(exc,"code",None),error=str(exc))
                raise
            delay=_retry_delay(exc.headers.get("Retry-After") if isinstance(exc,urllib.error.HTTPError) else None,attempt)
            ledger(root,"download_retry",day=day,attempt=attempt+1,http_status=getattr(exc,"code",None),delay_seconds=delay,error=str(exc))
            _sleep_retry(delay)
        finally:
            ledger(root, "network_transfer", day=day, network_bytes=actual, attempt=attempt + 1)
    if partial.stat().st_size != expected:
        raise IOError("NOAA size mismatch")
    md5 = hashlib.md5()
    with partial.open("rb") as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b""):
            md5.update(block)
    if meta.get("Content-MD5") and base64.b64encode(md5.digest()).decode() != meta["Content-MD5"]:
        raise ValueError("NOAA source MD5 mismatch")
    partial.replace(target)
    checkpoint.unlink()
    return dict(url=url, etag=meta.get("ETag"), last_modified=meta.get("Last-Modified"),
                byte_count=expected, sha256=digest(target))

def crop_day(source, destination, day):
    import numpy as np
    import pyarrow as pa
    import pyarrow.parquet as pq
    import shapely
    pf = pq.ParquetFile(source)
    required = {"mmsi", "base_date_time", "sog", "cog", "vessel_type", "geometry"}
    if not required.issubset(pf.schema_arrow.names):
        raise ValueError(f"NOAA schema change: missing {required-set(pf.schema_arrow.names)}")
    geo = json.loads(pf.schema_arrow.metadata.get(b"geo", b"{}"))
    if geo.get("columns", {}).get("geometry", {}).get("geometry_types") != ["Point"]:
        raise ValueError("NOAA source is not a documented Point product")
    if geo["columns"]["geometry"].get("crs",{}).get("id",{}).get("code")!=4326:
        raise ValueError("NOAA CRS changed: expected EPSG4326")
    source_rows = kept_rows = 0
    counts = {g: 0 for g in BBOXES}
    writer = None
    tmp = Path(destination).with_suffix(".partial.parquet")
    try:
        for batch in pf.iter_batches(batch_size=250_000, use_threads=False):
            table = pa.Table.from_batches([batch])
            source_rows += len(table)
            geom_array=batch.column(batch.schema.get_field_index("geometry"))
            offsets=np.frombuffer(geom_array.buffers()[1],dtype="<i4",count=len(geom_array)+1,offset=geom_array.offset*4)
            if not geom_array.null_count and np.all(np.diff(offsets)==21):
                wkb=np.frombuffer(geom_array.buffers()[2],dtype=np.dtype([("order","u1"),("type","<u4"),("x","<f8"),("y","<f8")]),count=len(geom_array),offset=int(offsets[0]))
                if np.all(wkb["order"]==1) and np.all(wkb["type"]==1):x,y=wkb["x"],wkb["y"]
                else:
                    geometries=shapely.from_wkb(table["geometry"].to_numpy(),on_invalid="ignore");x,y=shapely.get_x(geometries),shapely.get_y(geometries)
            else:
                geometries=shapely.from_wkb(table["geometry"].to_numpy(),on_invalid="ignore");x,y=shapely.get_x(geometries),shapely.get_y(geometries)
            ids = np.full(len(table), "", dtype=object)
            for gateway, (west, south, east, north) in BBOXES.items():
                mask = (x >= west) & (x <= east) & (y >= south) & (y <= north)
                ids[mask] = gateway
                counts[gateway] += int(mask.sum())
            mask = ids != ""
            selected = table.filter(pa.array(mask)).append_column("longitude", pa.array(x[mask])).append_column("latitude", pa.array(y[mask])).append_column("gateway_id", pa.array(ids[mask], type=pa.string())).append_column("source_partition", pa.array([day] * int(mask.sum()),type=pa.string()))
            kept_rows += len(selected)
            if writer is None:
                writer = pq.ParquetWriter(tmp, selected.schema, compression="zstd")
            writer.write_table(selected)
    finally:
        if writer:
            writer.close()
    if source_rows != pf.metadata.num_rows or pq.ParquetFile(tmp).metadata.num_rows != kept_rows:
        raise ValueError("NOAA crop row reconciliation failed")
    tmp.replace(destination)
    return dict(source_rows=source_rows, cropped_rows=kept_rows, gateway_rows=counts,
                schema_sha256=hashlib.sha256(str(pf.schema_arrow).encode()).hexdigest(),
                cropped_sha256=digest(destination), cropped_bytes=Path(destination).stat().st_size)

def acquire_ais(root, config, pilot=True, end_date=None):
    root = Path(root)
    gate = root / "artifacts/audit/geo_feasibility_gate.json"
    if not gate.exists() or not json.loads(gate.read_text()).get("target_and_portwatch_checked"):
        raise RuntimeError("NOAA bulk gate closed: first check target and PortWatch feasibility")
    if not pilot and not (root / "artifacts/audit/geo_pilot_freeze.json").exists():
        raise RuntimeError("Full NOAA acquisition requires validated pilot freeze")
    raw = root / "data/raw_cropped"
    cache = raw / ".national_cache"
    cache.mkdir(parents=True, exist_ok=True)
    manifest = root / "data/manifests/noaa_points.jsonl"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    existing = {r["day"]: r for r in _manifest_records(root)}
    start = dt.date.fromisoformat(config["scope"]["ais_start"])
    end = dt.date.fromisoformat(end_date or (str(start + dt.timedelta(days=13)) if pilot else config["scope"]["ais_end"]))
    todo=[]
    day=start
    while day<=end:
        d = day.isoformat()
        destination = raw / f"noaa-{d}.parquet"
        if d in existing:
            if not destination.exists() or digest(destination) != existing[d]["cropped_sha256"]:
                raise ValueError(f"Retained crop missing/hash changed for {d}")
            day += dt.timedelta(days=1)
            continue
        todo.append(d)
        day += dt.timedelta(days=1)
    # Exactly one downloader, overlapped with one single-threaded crop. This is
    # a managed executor, joined on normal exit and error; no persistent service.
    with ThreadPoolExecutor(max_workers=1,thread_name_prefix="noaa-prefetch") as pool:
        pending=pool.submit(_download,root,config,todo[0],cache/f"ais-{todo[0]}.parquet") if todo else None
        for index,d in enumerate(todo):
            source=cache/f"ais-{d}.parquet";destination=raw/f"noaa-{d}.parquet"
            receipt=pending.result()
            pending=pool.submit(_download,root,config,todo[index+1],cache/f"ais-{todo[index+1]}.parquet") if index+1<len(todo) else None
            receipt.update(crop_day(source,destination,d))
            receipt.update(day=d,retrieved_at_utc=utcnow(),source_id="noaa_ais_2024_points",license="CC0-1.0",availability_basis="retrospective_descriptive",source_retained=(d==str(start)),crop_path=destination.relative_to(root).as_posix())
            with manifest.open("a",encoding="utf8") as f:f.write(json.dumps(receipt)+"\n")
            if d!=str(start):
                if source.resolve().parent!=cache.resolve() or digest(destination)!=receipt["cropped_sha256"]:raise RuntimeError("Refusing unverifiable cache eviction")
                source.unlink()
            ledger(root,"day_cropped",**receipt,free_disk_bytes=shutil.disk_usage(root).free)
            print(json.dumps(dict(day=d,rows=receipt["cropped_rows"],network_gib=round(_network_bytes(root)/GIB,3))),flush=True)
    return dict(status="pilot_acquired" if pilot else "year_acquired", completed_days=len(_manifest_records(root)), network_bytes=_network_bytes(root))
