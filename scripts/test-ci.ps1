# test-ci.ps1 — Run tests with code coverage (used in CI/CD pipeline)
$RepoRoot = (Resolve-Path "$PSScriptRoot\..").Path
$VenvRoot = Join-Path $RepoRoot ".venv\Scripts"
if (-not (Test-Path (Join-Path $VenvRoot "python.exe"))) {
    if (Test-Path (Join-Path $RepoRoot "venv\Scripts\python.exe")) {
        $VenvRoot = Join-Path $RepoRoot "venv\Scripts"
    }
}
$Python = Join-Path $VenvRoot "python.exe"

$env:PYTHONPATH = "src"
Write-Host "Running unit and integration tests (mocked)..."
& $Python -m pytest tests/ --cov=src --cov-report=term-missing -v
