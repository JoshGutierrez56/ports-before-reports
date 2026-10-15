"""Install the built wheel into an isolated target and verify its code/CLI."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


root = Path(__file__).resolve().parents[1]
wheels = sorted((root / "release").glob("supply_chain_shadow_index-*.whl"))
if len(wheels) != 1:
    raise ValueError("Require exactly one current project wheel in release/")
wheel = wheels[0]
wheel_hash = sha256(wheel)
target = root / "artifacts/package_smoke" / wheel_hash[:16]
target.mkdir(parents=True, exist_ok=True)
code_hashes = {}
with zipfile.ZipFile(wheel) as archive:
    for source in sorted((root / "src/scsi").rglob("*.py")):
        name = source.relative_to(root / "src").as_posix()
        body = archive.read(name)
        if body != source.read_bytes():
            raise ValueError(f"Built wheel has stale source: {name}")
        code_hashes[name] = hashlib.sha256(body).hexdigest()
install = subprocess.run([sys.executable, "-m", "pip", "install", "--no-index", "--disable-pip-version-check", "--no-deps", "--no-compile", "--target", str(target), str(wheel)], cwd=target, capture_output=True, text=True, encoding="utf-8")
(root / "artifacts/audit/wheel_install_smoke.log").write_text(install.stdout + install.stderr, encoding="utf-8")
if install.returncode:
    raise RuntimeError("Isolated wheel installation failed")
for name, expected in code_hashes.items():
    if sha256(target / name) != expected:
        raise ValueError(f"Installed wheel code differs: {name}")
code = "import sys;from pathlib import Path;p=Path.cwd();sys.path.insert(0,str(p));import scsi;assert Path(scsi.__file__).resolve().is_relative_to(p);from scsi.cli import main;raise SystemExit(main(['--help']))"
cli = subprocess.run([sys.executable, "-I", "-c", code], cwd=target, capture_output=True, text=True, encoding="utf-8")
(root / "artifacts/audit/wheel_cli_smoke.log").write_text(cli.stdout + cli.stderr, encoding="utf-8")
if cli.returncode or "build-geospatial" not in cli.stdout or "verify-release" not in cli.stdout:
    raise RuntimeError("Installed-wheel CLI smoke failed")
receipt = {"status": "passed", "executed_at_utc": datetime.now(timezone.utc).isoformat(),
           "wheel": wheel.name, "sha256": wheel_hash, "byte_count": wheel.stat().st_size,
           "source_modules_verified": len(code_hashes), "installed_code_hashes": code_hashes,
           "isolated_target_import_verified": True, "cli_help_exit_code": cli.returncode,
           "environment": "Isolated wheel target using existing pinned project dependencies; not a fresh dependency installation",
           "network_acquisition": False}
(root / "artifacts/audit/package_build_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
print(json.dumps({k: receipt[k] for k in ("status", "wheel", "sha256", "source_modules_verified", "cli_help_exit_code")}))
