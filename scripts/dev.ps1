# dev.ps1 — Start APRIL in foreground for development / console output
$RepoRoot = (Resolve-Path "$PSScriptRoot\..").Path
$VenvRoot = Join-Path $RepoRoot ".venv\Scripts"
if (-not (Test-Path (Join-Path $VenvRoot "python.exe"))) {
    if (Test-Path (Join-Path $RepoRoot "venv\Scripts\python.exe")) {
        $VenvRoot = Join-Path $RepoRoot "venv\Scripts"
    }
}
$Python = Join-Path $VenvRoot "python.exe"

if (-not (Test-Path $Python)) {
    Write-Error "Virtual environment Python executable not found at $Python"
    exit 1
}

$env:PYTHONPATH = "src"
Write-Host "Starting APRIL in the foreground..."
& $Python src/main.py
