# test-host.ps1 — Run integration and verification tests natively on the host
$RepoRoot = (Resolve-Path "$PSScriptRoot\..").Path
$VenvRoot = Join-Path $RepoRoot ".venv\Scripts"
if (-not (Test-Path (Join-Path $VenvRoot "python.exe"))) {
    if (Test-Path (Join-Path $RepoRoot "venv\Scripts\python.exe")) {
        $VenvRoot = Join-Path $RepoRoot "venv\Scripts"
    }
}
$Python = Join-Path $VenvRoot "python.exe"

$env:PYTHONPATH = "src"
Write-Host "Running native verification tests..."
& $Python -m pytest tests/ -v
