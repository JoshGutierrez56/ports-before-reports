"""Bounded public-source fetching and separately scoped operational comparisons."""
from __future__ import annotations

import hashlib
import json
import random
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlsplit

import requests

_LAST_REQUEST: dict[str, float] = {}
SOURCE_LINEAGES={"portwatch":"imf_portwatch_ais_estimates","portwatch_hdx":"imf_portwatch_ais_estimates"}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _retry_delay(header: str | None, attempt: int) -> float:
    """Honor both HTTP Retry-After forms; malformed values use jittered backoff."""
    value = (header or "").strip()
    if value.isascii() and value.isdigit():
        return float(value)
    if value:
        try:
            deadline = parsedate_to_datetime(value)
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
            return max(0.0, deadline.timestamp() - time.time())
        except (TypeError, ValueError, OverflowError):
            pass
    return 2 ** attempt + random.uniform(0.0, 1.0)


def _sleep_retry(delay: float) -> None:
    """Do not shorten provider deadlines; bound each individual sleep to a minute."""
    while delay > 0:
        interval = min(60.0, delay)
        time.sleep(interval)
        delay -= interval


def fetch(root: str | Path, source_id: str, url: str, name: str, *, params=None,
          terms_url: str | None = None, refresh: bool = False) -> tuple[Path, dict]:
    """Save exact response bytes with a hash receipt; cached objects verify hashes."""
    root = Path(root)
    directory = root / "data" / "manifests" / "source_snapshots" / source_id
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    receipt_path = path.with_name(path.name + ".receipt.json")
    if path.exists() and receipt_path.exists() and not refresh:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if hashlib.sha256(path.read_bytes()).hexdigest() != receipt["sha256"]:
            raise ValueError(f"Cached source hash mismatch: {path}")
        if receipt.get("http_status",200) >= 400:
            raise requests.HTTPError(f"Cached failed HTTP {receipt['http_status']} response at {path}; retained as failure evidence")
        return path, receipt
    host = urlsplit(url).netloc
    response = None
    for attempt in range(1, 6):
        time.sleep(max(0, 1.05 - (time.monotonic() - _LAST_REQUEST.get(host, 0))))
        _LAST_REQUEST[host] = time.monotonic()
        try:
            response = requests.get(url, params=params, timeout=(20, 90),
                                    headers={"User-Agent": "SupplyChainShadowIndex/1.0 public academic research"})
            if response.status_code == 429 or 500 <= response.status_code < 600:
                if attempt < 5:
                    _sleep_retry(_retry_delay(response.headers.get("Retry-After"), attempt))
                    continue
            break
        except requests.RequestException as exc:
            if attempt == 5:
                audit = root / "artifacts" / "audit" / "source_ledger.jsonl"
                audit.parent.mkdir(parents=True, exist_ok=True)
                with audit.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps({"at": utcnow(), "source_id": source_id, "url": url,
                                             "status": "failed", "attempts": attempt, "error": str(exc)}) + "\n")
                raise
            _sleep_retry(_retry_delay(None, attempt))
    assert response is not None
    body = response.content
    digest = hashlib.sha256(body).hexdigest()
    now = utcnow()
    receipt = {"source_id": source_id, "snapshot_id": source_id + "-" + digest[:16],
               "retrieved_at_utc": now, "source_published_at_utc": None, "first_seen_at_utc": now,
               "source_url": url, "resolved_url": response.url, "etag": response.headers.get("ETag"),
               "last_modified": response.headers.get("Last-Modified"), "sha256": digest,
               "byte_count": len(body), "row_count": None, "schema_hash": None,
               "terms_url": terms_url, "redistribution_status": "review_required",
               "vintage_notes": "Current retrieval is not historical first release.",
               "http_status": response.status_code, "attempts": attempt,
               "path": str(path.relative_to(root)).replace("\\", "/")}
    if path.exists():
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f"Refusing to overwrite immutable changed source: {path}")
    else:
        temporary = path.with_name(path.name + ".partial")
        temporary.write_bytes(body)
        temporary.replace(path)
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    for ledger in [root / "data/manifests/source_downloads.jsonl", root / "artifacts/audit/source_ledger.jsonl"]:
        ledger.parent.mkdir(parents=True, exist_ok=True)
        with ledger.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(receipt) + "\n")
    response.raise_for_status()
    return path, receipt


def fetch_json(root, source_id, url, name, **kwargs):
    path, receipt = fetch(root, source_id, url, name, **kwargs)
    return json.loads(path.read_text(encoding="utf-8")), receipt


def audit_operational(root: str | Path) -> dict:
    """Operational measurements are not forecast features or independent AIS truth."""
    root = Path(root)
    output = {"status": "discovery_pending", "units": "berthing hours and call counts",
              "source": "https://www.bts.gov/ports", "comparison": "consistency_only",
              "caveat": "Shared AIS origins; reconcile vessel class, calendar and statistic first."}
    return output


def acquire_operational(root: str | Path) -> dict:
    """Acquire the separate 2024 reported waiting-stock comparator, not berth duration."""
    import pandas as pd
    root=Path(root)
    where="year=2024 AND indicator='Number of Containerships Awaiting Berths at all U.S. Ports' AND measure1 IN ('LA-LB','Savannah')"
    url="https://data.bts.gov/resource/y5ut-ibwt.json"
    count,_=fetch_json(root,"bts_operational",url,"awaiting_count.json",params={"$where":where,"$select":"count(*)"})
    rows,receipt=fetch_json(root,"bts_operational",url,"awaiting_2024.json",params={"$where":where,"$order":"id ASC","$limit":500})
    if len(rows)!=int(count[0]['count']) or len({r['id'] for r in rows})!=len(rows):
        raise ValueError("BTS waiting-stock count or ID mismatch")
    frame=pd.DataFrame(rows)
    if not frame.units.eq('Number of vessels').all():raise ValueError("Operational stock unit mismatch")
    frame['observation_date']=pd.to_datetime(frame.date)
    frame['gateway_id']=frame.measure1.map({'LA-LB':'san_pedro_bay','Savannah':'savannah'})
    frame['reported_waiting_stock']=pd.to_numeric(frame.value1,errors='raise')
    frame['snapshot_id']=receipt['snapshot_id']
    frame['source_url']=url
    frame['comparison_scope']='reported_containership_waiting_stock_not_independent_ground_truth'
    frame['time_of_day_utc']=None
    frame.to_parquet(root/'data/curated/operational_waiting_stock_2024.parquet',index=False)
    output={'status':'complete','rows':len(frame),'dates_per_gateway':frame.groupby('gateway_id').size().to_dict(),
            'snapshot_id':receipt['snapshot_id'],'path':'data/curated/operational_waiting_stock_2024.parquet',
            'source':'MARAD Office of Policy and Plans/Marine Exchange of SoCal via BTS',
            'caveats':['LA-LB includes drift/holding areas, not just geometrical anchorages','Containership identities differ from NOAA broad cargo proxy','Snapshot time of day unspecified; compare dates descriptively, not an exact midnight validation','NYNJ is not separately identified','2024 berthing-duration dashboard HTTP403: not acquired or bypassed']}
    (root/'data/manifests/source_operational.json').write_text(json.dumps(output,indent=2),encoding='utf-8')
    return output


def finalize_snapshot_catalog(root: str | Path) -> dict:
    """Enrich factual receipts; original downloaded bytes are never modified."""
    root=Path(root);entries=[]
    for sidecar in sorted((root/'data/manifests/source_snapshots').rglob('*.receipt.json')):
        record=json.loads(sidecar.read_text(encoding='utf-8'))
        path=root/record['path']
        body=path.read_bytes()
        if hashlib.sha256(body).hexdigest()!=record['sha256']:raise ValueError(f'Source hash mismatch: {path}')
        record['lineage_id']=SOURCE_LINEAGES.get(record['source_id'],record['source_id'])
        if record.get('http_status')==200 and path.suffix=='.json':
            value=json.loads(body)
            rows=value if isinstance(value,list) else value.get('features') if isinstance(value,dict) else None
            if isinstance(rows,list):
                record['row_count']=len(rows)
                columns=sorted({k for row in rows if isinstance(row,dict) for k in row.get('attributes',row)})
                record['schema_hash']=hashlib.sha256(json.dumps(columns).encode()).hexdigest()
            elif isinstance(value,dict) and 'fields' in value:
                record['schema_hash']=hashlib.sha256(json.dumps(value['fields'],sort_keys=True).encode()).hexdigest()
        entries.append(record)
    output=root/'data/manifests/source_snapshot_catalog.json'
    output.write_text(json.dumps(entries,indent=2),encoding='utf-8')
    return {'path':str(output.relative_to(root)).replace('\\','/'),'snapshots':len(entries),'actual_retained_response_bytes':sum(r['byte_count'] for r in entries)}
