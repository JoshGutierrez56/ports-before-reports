"""Clean-run preconditions and fail-closed discovery; fixtures are not empirical data."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest
import yaml

from scsi.sources import discovery
from scsi.sources.portwatch import LAYER, PORT_LAYER

ROOT = Path(__file__).resolve().parents[2]


def responses():
    fields = [{"name": n, "type": t} for n, t in (("ObjectId", "esriFieldTypeOID"), ("date", "esriFieldTypeDateOnly"), ("portid", "esriFieldTypeString"), ("portcalls_container", "esriFieldTypeInteger"), ("import_container", "esriFieldTypeDouble"), ("export_container", "esriFieldTypeDouble"))]
    rows = [{"id": str(i), "date": "2019-01-01T00:00:00", "indicator": "Loaded Import Containers at Select U.S. Ports in TEUs", "measure1": port, "value1": "100", "units": "TEUs", "source": "SYNTHETIC TEST FIXTURE"} for i, port in enumerate(("Los Angeles", "Long Beach", "NY-NJ", "Savannah"))]
    ports = [{"attributes": {"portid": pid, "portname": name, "ISO3": "USA", "lat": lat, "lon": lon}} for pid, name, lat, lon in (("port664", "Los Angeles-Long Beach", 33.75, -118.24), ("port815", "New York-New Jersey", 40.68, -74.1), ("port1170", "Savannah", 32.1, -81.13))]
    return {"metadata.json": {"id": "y5ut-ibwt", "columns": [{"fieldName": n} for n in rows[0]], "license": {"name": "Public Domain U.S. Government", "termsLink": "https://www.usa.gov/government-works"}}, "discovery_loaded_import_sample.json": rows, "daily_item.json": {"id": discovery.DAILY_ID, "owner": "IMF-portwatch_imf_dataviz", "url": LAYER.rsplit("/", 1)[0]}, "ports_item.json": {"id": discovery.PORTS_ID, "owner": "IMF-portwatch_imf_dataviz", "url": PORT_LAYER.rsplit("/", 1)[0]}, "daily_layer.json": {"fields": fields}, "ports_layer.json": {"fields": [{"name": n} for n in ("portid", "portname", "ISO3", "lat", "lon")]}, "faqs_data.json": {"content": "API allows you to programmatically retrieve daily estimates"}, "method_data.json": {"content": "Synthetic methodology fixture"}, "selected_ports.json": {"features": ports}}


def install_fetch(monkeypatch, payloads):
    calls = []
    def mocked(root, source_id, url, name, **kwargs):
        calls.append(name)
        value = copy.deepcopy(payloads[name])
        destination = root / "data/manifests/source_snapshots" / source_id / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(value), encoding="utf-8")
        return value, {"path": destination.relative_to(root).as_posix(), "sha256": discovery.sha256(destination)}
    monkeypatch.setattr(discovery, "fetch_json", mocked)
    return calls


def test_discovery_populates_actual_adapter_prerequisites(tmp_path, monkeypatch):
    calls = install_fetch(monkeypatch, responses())
    receipt = discovery.discover_sources(tmp_path)
    assert receipt["bounded_target_sample_rows"] == 4 and len(calls) == 9
    for relative in ("bts_freight_indicators/metadata.json", "portwatch/faqs_data.json", "portwatch/selected_ports.json"):
        assert (tmp_path / "data/manifests/source_snapshots" / relative).exists()
    assert yaml.safe_load((tmp_path / "data/source_registry.yaml").read_text())["created_before_bulk_acquisition"]
    assert not (tmp_path / "data/curated").exists()


@pytest.mark.parametrize("mutation", ["license", "identity", "permission", "truncation", "location", "units"])
def test_discovery_refuses_changed_evidence(tmp_path, monkeypatch, mutation):
    payloads = responses()
    if mutation == "license": payloads["metadata.json"]["license"]["name"] = "Restricted"
    elif mutation == "identity": payloads["daily_item.json"]["owner"] = "Unrelated publisher"
    elif mutation == "permission": payloads["faqs_data.json"] = {"content": "No API permission"}
    elif mutation == "truncation": payloads["selected_ports.json"]["exceededTransferLimit"] = True
    elif mutation == "location": payloads["selected_ports.json"]["features"][0]["attributes"]["lat"] = 1.0
    else: payloads["discovery_loaded_import_sample.json"][0]["units"] = "tons"
    install_fetch(monkeypatch, payloads)
    with pytest.raises(ValueError): discovery.discover_sources(tmp_path)
    assert not (tmp_path / "artifacts/audit/source_discovery_receipt.json").exists()


def test_discovery_cannot_modify_locked_vintage(tmp_path, monkeypatch):
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "artifacts/protocol_lock.json").write_text("{}")
    calls = install_fetch(monkeypatch, responses())
    with pytest.raises(ValueError, match="locked vintage"): discovery.discover_sources(tmp_path)
    assert calls == []


def initialize_module():
    spec = importlib.util.spec_from_file_location("scsi_initialize_config", ROOT / "scripts/initialize_config.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fresh_root(tmp_path):
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs/project.template.yaml").write_bytes((ROOT / "configs/project.template.yaml").read_bytes())
    for name in ("PROJECT_BRIEF.md", "RESEARCH_PROTOCOL.md"):
        (tmp_path / name).write_text("Synthetic test fixture; no empirical results.")
    return tmp_path


def test_initializer_creates_new_lock_without_replacing_config(tmp_path):
    root = fresh_root(tmp_path)
    initialize = initialize_module().initialize
    result = initialize(root)
    saved = (root / "configs/project.yaml").read_bytes()
    assert not result["historical_lock_reused"] and not result["portfolio_integration_configured"]
    assert json.loads((root / "artifacts/initial_protocol_lock.json").read_text())["config_sha256"] == result["sha256"]
    with pytest.raises(ValueError, match="never overwritten"): initialize(root)
    assert (root / "configs/project.yaml").read_bytes() == saved


@pytest.mark.parametrize("prior", ["artifacts/protocol_lock.json", "artifacts/predictions/existing.json", "data/manifests/source_targets.json"])
def test_initializer_refuses_historical_evidence(tmp_path, prior):
    root = fresh_root(tmp_path)
    path = root / prior
    path.parent.mkdir(parents=True)
    path.write_text("{}")
    with pytest.raises(ValueError, match="Historical evidence"): initialize_module().initialize(root)
    assert not (root / "configs/project.yaml").exists()
