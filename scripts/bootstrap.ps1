param(
    [switch]$InitializeNewRun,
    [string]$WebsiteRepo = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
Push-Location $ProjectRoot
try {
    if (-not (Test-Path -LiteralPath $Python)) {
        & py -3.12 -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Python environment creation failed.' }
    }
    & $Python -m pip install --only-binary=:all: -r requirements.lock
    if ($LASTEXITCODE -ne 0) { throw 'Locked dependency installation failed.' }
    & $Python -m pip install --no-deps -e .
    if ($LASTEXITCODE -ne 0) { throw 'Project installation failed.' }
    if ($InitializeNewRun) {
        $initializeArgs = @('scripts/initialize_config.py', '--root', $ProjectRoot)
        if ($WebsiteRepo) { $initializeArgs += @('--website-repo', $WebsiteRepo) }
        & $Python @initializeArgs
        if ($LASTEXITCODE -ne 0) { throw 'New-run configuration initialization refused; existing evidence was preserved.' }
    }
    if (Test-Path -LiteralPath (Join-Path $ProjectRoot 'configs\project.yaml')) {
        & $Python -m scsi.cli preflight --config configs/project.yaml
        if ($LASTEXITCODE -ne 0) { throw 'Preflight failed.' }
    } else {
        Write-Host 'Package installed. No machine-specific configs/project.yaml is present; no acquisition or preflight was run.'
        Write-Host 'For the public bundle, run: .venv/Scripts/python.exe scripts/reproduce_public.py'
        Write-Host 'For a genuinely fresh source run, see docs/REPRODUCIBILITY.md before using -InitializeNewRun.'
    }
} finally { Pop-Location }
