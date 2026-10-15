"""Bounded official-source discovery for a clean workspace, before panel extraction."""
from __future__ import annotations

import json
from pathlib import Path
import re

from scsi.provenance import sha256, write_json, utcnow
from scsi.sources.operational import fetch_json

ITEM_ROOT = "https://www.arcgis.com/sharing/rest/content/items/"
DAILY_ID = "83b1bbc7b3354c5fb1f40673bb8f852e"
PORTS_ID = "acc668d199d1472abaaf2467133d4ca4"
FAQ_ID = "640b69a4a96f41a6937cb4d2984f26da"
METHOD_ID = "19b92a4413c34407878791299acde8d7"
BTS_METADATA = "https://data.bts.gov/api/views/y5ut-ibwt.json"


def discover_sources(root: Path) -> dict:
    from scsi.sources.official_teu import INDICATOR, PORTS as TARGET_PORTS, URL, parse_bts
    from scsi.sources.portwatch import LAYER, PORT_LAYER, PORTS, TERMS, validate_layer

    root = Path(root)
    if (root / "artifacts/protocol_lock.json").exists():
        raise ValueError("Discovery cannot replace a locked vintage; use CLI audit-sources to verify its frozen inputs")
    receipts = []

    def get(source, url, name, **kwargs):
        data, receipt = fetch_json(root, source, url, name, **kwargs)
        if isinstance(data, dict) and "error" in data:
            raise ValueError(f"Source discovery returned an error: {name}")
        receipts.append(receipt)
        return data

    metadata = get("bts_freight_indicators", BTS_METADATA, "metadata.json")
    columns = {field["fieldName"] for field in metadata.get("columns", [])}
    if metadata.get("id") != "y5ut-ibwt" or not {"id", "date", "indicator", "measure1", "value1", "units", "source"} <= columns:
        raise ValueError("BTS identity or target schema changed; source review required")
    license_info = metadata.get("license", {})
    if license_info.get("name") != "Public Domain U.S. Government" or not license_info.get("termsLink"):
        raise ValueError("BTS data-specific license changed; source review required")
    sample_where = f"indicator='{INDICATOR}' AND measure1 IN ('Los Angeles','Long Beach','NY-NJ','Savannah') AND date >= '2019-01-01T00:00:00' AND date < '2019-02-01T00:00:00'"
    sample = get("bts_freight_indicators", URL, "discovery_loaded_import_sample.json", params={"$where": sample_where, "$order": "id ASC", "$limit": 5}, terms_url=license_info["termsLink"])
    parsed = parse_bts(sample, "source_discovery_only_not_canonical")
    if len(parsed) != 4 or set(parsed.measure1) != set(TARGET_PORTS):
        raise ValueError("The bounded target sample must contain exactly all four reporting ports")

    for item_id, name, expected in ((DAILY_ID, "daily_item.json", LAYER), (PORTS_ID, "ports_item.json", PORT_LAYER)):
        item = get("portwatch", ITEM_ROOT + item_id, name, params={"f": "json"}, terms_url=TERMS)
        if item.get("id") != item_id or item.get("owner") != "IMF-portwatch_imf_dataviz" or str(item.get("url", "")).rstrip("/") + "/0" != expected:
            raise ValueError("Official PortWatch catalog ownership/service changed; review rather than substituting a similarly named layer")
    daily = get("portwatch", LAYER, "daily_layer.json", params={"f": "json"}, terms_url=TERMS)
    validate_layer(daily)
    ports = get("portwatch", PORT_LAYER, "ports_layer.json", params={"f": "json"}, terms_url=TERMS)
    if not {"portid", "portname", "ISO3", "lat", "lon"} <= {field["name"] for field in ports.get("fields", [])}:
        raise ValueError("Port catalog lacks identity/coordinate fields")
    faq = get("portwatch", ITEM_ROOT + FAQ_ID + "/data", "faqs_data.json", params={"f": "json"}, terms_url=TERMS)
    if "programmatically retrieve" not in json.dumps(faq, ensure_ascii=False).lower():
        raise ValueError("Official FAQ no longer establishes data-specific API permission; stop before panel extraction")
    method = get("portwatch", ITEM_ROOT + METHOD_ID + "/data", "method_data.json", params={"f": "json"}, terms_url=TERMS)
    if not method:
        raise ValueError("Empty methodology evidence")
    selected = get("portwatch", PORT_LAYER + "/query", "selected_ports.json", params={"f": "json", "where": "portid IN ('port664','port815','port1170')", "outFields": "*", "returnGeometry": "false", "orderByFields": "portid ASC"}, terms_url=TERMS)
    features = selected.get("features", [])
    if selected.get("exceededTransferLimit") or len(features) != 3:
        raise ValueError("Selected-port response incomplete or truncated")
    attrs = [feature["attributes"] for feature in features]
    if {row["portid"] for row in attrs} != set(PORTS):
        raise ValueError("Selected-port identifiers changed or duplicated")
    references = {"port664": ("los angeles", "long beach", 33.756, -118.244), "port815": ("new york", "new jersey", 40.68, -74.10), "port1170": ("savannah", "savannah", 32.10, -81.13)}
    for row in attrs:
        first, second, lat, lon = references[row["portid"]]
        normalized = re.sub(r"[^a-z]+", " ", row["portname"].lower())
        if row.get("ISO3") != "USA" or first not in normalized or second not in normalized or abs(float(row["lat"]) - lat) > 0.5 or abs(float(row["lon"]) - lon) > 0.5:
            raise ValueError("Port identity/location inconsistent with the reviewed gateway mapping")

    receipt = {"status": "source_feasibility_verified", "created_at_utc": utcnow(), "bounded_target_sample_rows": len(parsed), "selected_gateway_records": len(attrs), "source_files_checked": len(receipts), "snapshot_hashes": {r["path"]: r["sha256"] for r in receipts}, "terms_checked": True, "raw_panel_acquired": False, "historical_availability_verified": False, "scope_note": "Identity and units verified; NYNJ facility boundary ambiguity remains and is not resolved by matching names/coordinates."}
    write_json(root / "artifacts/audit/source_discovery_receipt.json", receipt)
    registry = root / "data/source_registry.yaml"
    if not registry.exists():
        import yaml
        registry.parent.mkdir(parents=True, exist_ok=True)
        registry.write_text(yaml.safe_dump({"version": 1, "created_before_bulk_acquisition": True, "sources": {"portwatch": {"status": "feasibility_verified_not_bulk_acquired", "resolved_service": LAYER, "terms_url": TERMS, "permission_evidence": ITEM_ROOT + FAQ_ID + "/data", "attribution": "Sources: Kpler; UN Global Platform; IMF PortWatch", "redistribution": "attributed_transformed_aggregates_only_no_raw_export", "availability": "current_vintage_pseudo_realtime"}, "bts_freight_indicators": {"status": "sample_verified_not_bulk_acquired", "seed": BTS_METADATA, "resolved_service": URL, "exact_indicator": INDICATOR, "units": "TEUs", "terms_url": license_info["termsLink"], "historical_first_releases": "not_established"}, "noaa_points_2024": {"status": "not_acquired", "seed": "https://github.com/ocm-marinecadastre/ais-vessel-traffic", "license": "Check current NOAA 2024 point README before acquisition"}}}, sort_keys=False), encoding="utf-8")
    receipt["source_registry_sha256"] = sha256(registry)
    write_json(root / "artifacts/audit/source_discovery_receipt.json", receipt)
    return receipt
