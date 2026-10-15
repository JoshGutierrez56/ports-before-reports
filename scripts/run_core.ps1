$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python)) { throw 'Run scripts/bootstrap.ps1 first.' }
if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot 'configs\project.yaml'))) {
    throw 'No machine-local configuration. Read docs/REPRODUCIBILITY.md; public bundle replay does not need this orchestrator.'
}
$stages = @(
    @('preflight'), @('audit-sources'), @('acquire-targets'), @('acquire-flow'),
    @('build-crosswalk'), @('acquire-ais','--pilot'), @('audit-ais'),
    @('acquire-ais','--resume'), @('build-geospatial'), @('build-features'),
    @('validate-models'), @('lock-protocol'), @('evaluate-locked'),
    @('run-robustness'), @('build-report'), @('build-site-data')
)
$runLock = $null
$threadVariables = @('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS')
$previousThreadValues = @{}
Push-Location $ProjectRoot
try {
    foreach ($name in $threadVariables) {
        $previousThreadValues[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
        [Environment]::SetEnvironmentVariable($name, '1', 'Process')
    }
    # OS-enforced exclusive orchestration lock; no global execution-policy/config changes.
    [System.IO.Directory]::CreateDirectory((Join-Path $ProjectRoot 'artifacts')) | Out-Null
    $runLock = [System.IO.File]::Open((Join-Path $ProjectRoot 'artifacts\execution.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
    foreach ($stage in $stages) {
        & $Python -m scsi.cli @stage --config configs/project.yaml
        if ($LASTEXITCODE -ne 0) { throw ('Stage failed: ' + $stage[0] + '. Read its preserved receipt; resume after resolving it.') }
    }
    & $Python notebooks/verify_locked_predictions.py
    if ($LASTEXITCODE -ne 0) { throw 'Independent arithmetic audit failed.' }
    & $Python notebooks/execute.py
    if ($LASTEXITCODE -ne 0) { throw 'Final notebook execution failed.' }
    & $Python -m pytest tests -q --junitxml=artifacts/test-results/pytest.xml
    if ($LASTEXITCODE -ne 0) { throw 'Research tests failed.' }
    & $Python -m scsi.cli verify-release --config configs/project.yaml
    if ($LASTEXITCODE -ne 0) { throw 'Research release verification failed.' }
    & $Python scripts/check_public_bundle.py
    if ($LASTEXITCODE -ne 0) { throw 'Isolated public-bundle reproduction failed.' }
    Write-Host 'Research evidence verified. Local portfolio build/browser QA and the final handoff remain separate gates; nothing was published.'
} finally {
    if ($null -ne $runLock) { $runLock.Dispose() }
    foreach ($name in $threadVariables) {
        if ($previousThreadValues.ContainsKey($name)) {
            [Environment]::SetEnvironmentVariable($name, $previousThreadValues[$name], 'Process')
        }
    }
    Pop-Location
}
