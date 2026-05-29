# deploy.ps1 — Deploy local changes and restart background daemon
$RepoRoot = (Resolve-Path "$PSScriptRoot\..").Path
$Aprilctl = Join-Path $PSScriptRoot "aprilctl.ps1"

Write-Host "Triggering local background daemon deployment/restart..."
powershell -File $Aprilctl restart
