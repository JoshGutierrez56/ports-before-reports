$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
Push-Location $ProjectRoot
try {
    & $Python -m pytest -q --junitxml=artifacts/test-results/pytest.xml
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed; publication is not ready.' }
    & $Python -m scsi.cli verify-release --config configs/project.yaml
    if ($LASTEXITCODE -ne 0) { throw 'Release verification failed.' }
} finally { Pop-Location }
