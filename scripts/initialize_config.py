"""Create a machine-local configuration only for a genuinely new research run."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import yaml

from scsi.config import load_config


def initialize(root: Path, website_repo: str = "") -> dict:
    root = root.resolve()
    destination = root / "configs/project.yaml"
    if destination.exists():
        raise ValueError("Existing configuration is never overwritten")
    historical = (
        "artifacts/protocol_lock.json", "artifacts/initial_protocol_lock.json",
        "artifacts/metrics/locked_results.json", "artifacts/audit/geo_pilot_freeze.json",
        "data/manifests/source_targets.json", "data/manifests/source_flow.json",
        "data/manifests/noaa_points.jsonl",
    )
    if any((root / name).exists() for name in historical) or any((root / "artifacts/predictions").glob("*.json")):
        raise ValueError("Historical evidence is present: use portable replay or a separate fresh directory, not a replacement lock")
    template = root / "configs/project.template.yaml"
    for filename in ("PROJECT_BRIEF.md", "RESEARCH_PROTOCOL.md"):
        if not (root / filename).is_file():
            raise ValueError(f"A new source run requires its reviewed {filename}")
    config = yaml.safe_load(template.read_text(encoding="utf-8"))
    if config["project"]["workspace_root"] is not None or config["project"]["website_repo"] is not None:
        raise ValueError("Template must have null machine-specific paths")
    site = Path(website_repo).resolve() if website_repo else None
    if site is not None and not (site / "package.json").is_file():
        raise ValueError("Website path must identify an inspected local site with package.json")
    config["project"]["workspace_root"] = str(root)
    config["project"]["website_repo"] = str(site) if site else None
    # No website repository means a standalone research run, not completed integration.
    config["publishing"]["integrate_existing_portfolio"] = site is not None
    temporary = destination.with_name("project.initializing.yaml")
    if temporary.exists():
        raise ValueError("An earlier initialization checkpoint exists; inspect it before resuming")
    temporary.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    load_config(temporary)
    # The exclusive create prevents replacing a config created by a competing process.
    with destination.open("x", encoding="utf-8") as output:
        output.write(temporary.read_text(encoding="utf-8"))
    temporary.unlink()
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    stamp = datetime.now(timezone.utc).isoformat()
    initial = {"lock_kind": "new_run_initial_before_source_acquisition", "created_at_utc": stamp, "brief_sha256": digest(root / "PROJECT_BRIEF.md"), "protocol_sha256": digest(root / "RESEARCH_PROTOCOL.md"), "config_sha256": digest(destination), "test_results_opened": False, "final_evaluation_lock": False, "historical_exposure": "The earlier completed portfolio study and its result may already be known. This new-vintage reproduction is not a new untouched historical holdout or prospective registration."}
    artifact_dir = root / "artifacts"
    artifact_dir.mkdir(exist_ok=True)
    with (artifact_dir / "initial_protocol_lock.json").open("x", encoding="utf-8") as output:
        json.dump(initial, output, indent=2)
    return {"status": "new_run_configuration_created", "sha256": digest(destination), "initial_protocol_lock_sha256": digest(artifact_dir / "initial_protocol_lock.json"), "historical_lock_reused": False, "portfolio_integration_configured": site is not None}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--website-repo", default="")
    args = parser.parse_args()
    print(json.dumps(initialize(args.root, args.website_repo)))


if __name__ == "__main__":
    main()
