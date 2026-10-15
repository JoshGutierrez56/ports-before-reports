"""IMF PortWatch adapter: typed container calls, stable IDs and count reconciliation."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

import pandas as pd
from .operational import fetch_json

LAYER = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Daily_Ports_Data/FeatureServer/0"
PORT_LAYER = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/PortWatch_ports_database/FeatureServer/0"
TERMS = "https://www.imf.org/en/about/copyright-and-terms"
PORTS = {"port664": "san_pedro_bay", "port815": "new_york_new_jersey", "port1170": "savannah"}
WHERE = "portid IN ('port664','port815','port1170') AND date >= '2019-01-01' AND date <= '2025-12-31'"
BLACKOUTS = {"2022-05-12", "2023-02-14", "2024-01-09"}


def validate_layer(metadata: dict) -> None:
    fields = {field["name"]: field["type"] for field in metadata.get("fields", [])}
    required = {"ObjectId", "date", "portid", "portcalls_container", "import_container", "export_container"}
    if not required.issubset(fields):
        raise ValueError(f"PortWatch schema missing container-specific fields: {required-set(fields)}")
    if fields["portcalls_container"] not in {"esriFieldTypeInteger", "esriFieldTypeSmallInteger"}:
        raise ValueError("Container calls must be an integer count, never tons or total cargo calls")
    if fields["date"] not in {"esriFieldTypeDateOnly", "esriFieldTypeDate"}:
        raise ValueError("Unrecognized PortWatch observation date type")


def reconcile_batches(batches: list[dict], object_ids: list[int], oid="ObjectId") -> list[dict]:
    records = []
    for batch in batches:
        if "error" in batch:
            raise ValueError(f"ArcGIS query failed: {batch['error']}")
        if batch.get("exceededTransferLimit"):
            raise ValueError("ArcGIS transfer limit: subdivide object-ID batch; do not accept truncation")
        records.extend(feature["attributes"] for feature in batch.get("features", []))
    found = [record[oid] for record in records]
    if len(found) != len(set(found)):
        raise ValueError("Duplicate ArcGIS object IDs")
    if set(found) != set(object_ids):
        raise ValueError("ArcGIS object-ID count/set reconciliation failed")
    return records


def _query(root, name, params):
    params = {"f": "json", "returnGeometry": "false", **params}
    return fetch_json(root, "portwatch", LAYER + "/query", name, params=params, terms_url=TERMS)


def complete_id_batch(query, selected: list[int], label: str) -> tuple[list[dict],list[dict]]:
    """Recursively paginate when the server applies a smaller transfer limit."""
    batch,receipt=query(label+".json", {"objectIds": ",".join(map(str,selected)),
        "outFields":"ObjectId,date,portid,portname,portcalls_container,import_container,export_container", "orderByFields":"ObjectId ASC"})
    if not batch.get("exceededTransferLimit"):
        return [batch],[receipt]
    if len(selected)<2:
        raise ValueError("ArcGIS cannot return a single complete record")
    midpoint=len(selected)//2
    first,first_receipts=complete_id_batch(query,selected[:midpoint],label+"a")
    last,last_receipts=complete_id_batch(query,selected[midpoint:],label+"b")
    return first+last,first_receipts+last_receipts


def build_crosswalk(root: str | Path) -> dict:
    root = Path(root)
    path = root / "data/manifests/source_snapshots/portwatch/selected_ports.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    targets = {"port664": "Los Angeles + Long Beach", "port815": "New York-New Jersey", "port1170": "Savannah"}
    urls = {"port664": "https://portoflosangeles.org/business/statistics/container-statistics;https://polb.com/business/port-statistics/",
            "port815": "https://www.panynj.gov/port/en/our-port/facts-and-figures.html",
            "port1170": "https://gaports.com/sales/by-the-numbers/"}
    for feature in data["features"]:
        record = feature["attributes"]
        pid = record["portid"]
        if pid not in PORTS:
            continue
        rows.append({"gateway_id": PORTS[pid], "source_id": "portwatch", "source_port_id": pid,
                     "official_target_label": targets[pid], "source_port_name": record["portname"],
                     "latitude": record["lat"], "longitude": record["lon"], "un_locode": record.get("LOCODE"),
                     "reporting_scope": "Combined LA/LB; one PortWatch record, two nonoverlapping authority targets" if pid=="port664" else "Named authority gateway; exact terminal-boundary equivalence not independently proven",
                     "valid_from": "2019-01-01", "valid_to": "2025-12-31", "geometry_version": "portwatch-current-2026-10-15",
                     "mapping_evidence_url": PORT_LAYER+";"+urls[pid], "confidence": "high_identity_medium_boundary",
                     "reviewer_type": "agent_assisted_source_name_coordinates_and_authority_scope",
                     "exclusions": "Brunswick and other GPA locations" if pid=="port1170" else "No separate Newark/Elizabeth or separate LA/LB PortWatch IDs added",
                     "boundary_ambiguity": pid=="port815"})
    frame = pd.DataFrame(rows)
    if len(frame)!=3 or set(frame.source_port_id)!=set(PORTS):
        raise ValueError("Gateway crosswalk incomplete")
    directory = root / "data/geography"
    directory.mkdir(parents=True, exist_ok=True)
    frame.to_csv(directory / "gateway_crosswalk.csv", index=False)
    frame.to_parquet(directory / "gateway_crosswalk.parquet", index=False)
    return {"rows": len(frame), "path": "data/geography/gateway_crosswalk.parquet", "ny_nj_terminal_boundary_ambiguity": True}


def acquire_flow(root: str | Path) -> dict:
    root = Path(root)
    # Explicit provider documentation permits API port-ID iteration. Save this evidence before extraction.
    faq_path = root / "data/manifests/source_snapshots/portwatch/faqs_data.json"
    if not faq_path.exists() or "programmatically retrieve" not in faq_path.read_text(encoding="utf-8"):
        raise ValueError("PortWatch data-specific programmatic-access evidence required before extraction")
    before, _ = fetch_json(root, "portwatch", LAYER, "acquisition_layer_before.json", params={"f":"json"}, terms_url=TERMS)
    validate_layer(before)
    count, _ = _query(root, "acquisition_count_before.json", {"where":WHERE,"returnCountOnly":"true"})
    ids, _ = _query(root, "selected_object_ids.json", {"where":WHERE,"returnIdsOnly":"true"})
    object_ids = sorted(ids["objectIds"])
    if len(object_ids) != count["count"] or len(set(object_ids)) != len(object_ids):
        raise ValueError("PortWatch initial ID/count mismatch")
    batches, receipts = [], []
    # Keep URL lengths bounded and stay below the live 1000-record transfer limit.
    for start in range(0, len(object_ids), 100):
        pieces,piece_receipts=complete_id_batch(lambda name,params:_query(root,name,params),object_ids[start:start+100],f"daily_ids100_{start:05d}")
        batches.extend(pieces);receipts.extend(piece_receipts)
    records = reconcile_batches(batches, object_ids)
    after, _ = fetch_json(root, "portwatch", LAYER, "acquisition_layer_after.json", params={"f":"json"}, terms_url=TERMS)
    count_after, _ = _query(root, "acquisition_count_after.json", {"where":WHERE,"returnCountOnly":"true"})
    if before.get("editingInfo") != after.get("editingInfo") or count != count_after:
        raise ValueError("PortWatch changed during extraction; preserve snapshot and reacquire explicitly")
    frame = pd.DataFrame(records).sort_values(["portid","date"])
    if frame.duplicated(["portid","date"]).any() or set(frame.portid)!=set(PORTS):
        raise ValueError("PortWatch duplicate port-day or unmatched source ID")
    dates = pd.to_datetime(frame.date, utc=True)
    if (frame.portcalls_container.dropna()<0).any():
        raise ValueError("Negative container-call count")
    expected_grid=pd.MultiIndex.from_product([list(PORTS),pd.date_range('2019-01-01','2025-12-31',freq='D').strftime('%Y-%m-%d')],names=['portid','date'])
    missing_grid=expected_grid.difference(pd.MultiIndex.from_frame(frame[['portid','date']]))
    snapshot_hash = hashlib.sha256("".join(r["sha256"] for r in receipts).encode()).hexdigest()
    frame = frame.rename(columns={"portid":"source_port_id", "portcalls_container":"port_calls", "import_container":"incoming_volume", "export_container":"outgoing_volume", "ObjectId":"source_object_id"})
    frame["gateway_id"] = frame.source_port_id.map(PORTS)
    frame["observation_date"] = dates.dt.tz_localize(None)
    frame["observation_interval_end_utc"] = dates + pd.Timedelta(days=1)
    frame["vessel_category"] = "container"
    frame["incoming_volume_unit"] = "metric_tons_estimated"
    frame["outgoing_volume_unit"] = "metric_tons_estimated"
    frame["snapshot_id"] = "portwatch-panel-"+snapshot_hash[:16]
    frame["source_published_at_utc"] = pd.NaT
    frame["availability_basis"] = "current_vintage_pseudo_realtime"
    frame["quality_flags"] = "current_vintage_post_test_methodology_revisions"
    blackout = frame.date.isin(BLACKOUTS)
    frame["source_reported_port_calls"] = frame.port_calls
    frame.loc[blackout, "port_calls"] = float("nan")
    frame.loc[blackout, "quality_flags"] += ";provider_documented_blackout_unknown_coverage"
    frame["verified_available_at_utc"] = pd.to_datetime(max(r["retrieved_at_utc"] for r in receipts), utc=True)
    frame["assumed_available_at_utc"] = frame.observation_interval_end_utc + pd.Timedelta(days=7)
    directory = root / "data/curated"
    directory.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(directory / "portwatch_daily.parquet", index=False)
    coverage = frame.groupby("gateway_id").agg(rows=("port_calls","size"), usable_days=("port_calls","count"), first=("observation_date","min"), last=("observation_date","max")).reset_index()
    coverage.to_csv(root / "data/manifests/source_flow_coverage.csv", index=False)
    receipt = {"status":"complete" if len(missing_grid)==0 else "incomplete", "row_count":len(frame), "missing_port_days":len(missing_grid), "server_count_before":count["count"], "server_count_after":count_after["count"], "unique_object_ids":len(object_ids), "blackout_port_days":int(blackout.sum()),
               "snapshot_id":frame.snapshot_id.iloc[0], "source_snapshot_ids":[r["snapshot_id"] for r in receipts],
               "schema_hash":hashlib.sha256(json.dumps([(c,str(t)) for c,t in frame.dtypes.items()]).encode()).hexdigest(),
               "path":"data/curated/portwatch_daily.parquet", "sha256":hashlib.sha256((directory/"portwatch_daily.parquet").read_bytes()).hexdigest()}
    (root / "data/manifests/source_flow.json").write_text(json.dumps(receipt,indent=2),encoding="utf-8")
    return receipt


def audit_sources(root: str | Path) -> dict:
    root=Path(root)
    from .discovery import discover_sources
    discovery=discover_sources(root)
    return {"discovery":discovery,"flow":json.loads((root/"data/manifests/source_flow.json").read_text()) if (root/"data/manifests/source_flow.json").exists() else {"status":"not_acquired"},
            "targets":json.loads((root/"data/manifests/source_targets.json").read_text()) if (root/"data/manifests/source_targets.json").exists() else {"status":"not_acquired"}}
