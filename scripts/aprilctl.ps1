param(
    [ValidateSet("start", "stop", "restart", "status")]
    [string]$Action = "status"
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path "$PSScriptRoot\..").Path
$VenvRoot = Join-Path $RepoRoot ".venv\Scripts"
if (-not (Test-Path (Join-Path $VenvRoot "python.exe"))) {
    if (Test-Path (Join-Path $RepoRoot "venv\Scripts\python.exe")) {
        $VenvRoot = Join-Path $RepoRoot "venv\Scripts"
    }
}
$Pythonw = Join-Path $VenvRoot "pythonw.exe"
$Python = Join-Path $VenvRoot "python.exe"
$MainScript = Join-Path $RepoRoot "src\main.py"

function Get-AprilProcess {
    $mainPath = [System.IO.Path]::GetFullPath($MainScript)
    Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" |
        Where-Object {
            $_.CommandLine -and (
                $_.CommandLine -like "*$mainPath*" -or
                $_.CommandLine -like "*main.py*"
            )
        } |
        Sort-Object ProcessId -Descending |
        Select-Object -First 1
}

function Start-April {
    $proc = Get-AprilProcess
    if ($proc) {
        Write-Host "APRIL is already running (PID $($proc.ProcessId))."
        return
    }

    $launcher = if (Test-Path $Pythonw) { $Pythonw } else { $Python }
    if (-not (Test-Path $launcher)) {
        throw "Could not find a Python launcher in $VenvRoot"
    }

    $startArgs = '"' + $MainScript + '"'
    $proc = Start-Process -FilePath $launcher -WorkingDirectory $RepoRoot -ArgumentList $startArgs -WindowStyle Hidden -PassThru
    Start-Sleep -Milliseconds 1200
    if ($proc.HasExited) {
        Write-Host "APRIL failed to start (exit code $($proc.ExitCode))."
        return
    }

    $running = Get-AprilProcess
    if ($running) {
        Write-Host "APRIL started (PID $($running.ProcessId))."
    } else {
        Write-Host "APRIL started (PID $($proc.Id))."
    }
}

function Stop-April {
    $proc = Get-AprilProcess
    if (-not $proc) {
        Write-Host "APRIL is not running."
        return
    }

    Stop-Process -Id $proc.ProcessId -Force
    Write-Host "APRIL stopped (PID $($proc.ProcessId))."
}

function Restart-April {
    Stop-April
    Start-Sleep -Milliseconds 400
    Start-April
}

function Show-Status {
    $proc = Get-AprilProcess
    if ($proc) {
        Write-Host "APRIL is running (PID $($proc.ProcessId))."
        return
    }

    Write-Host "APRIL is not running."
}

switch ($Action) {
    "start" { Start-April }
    "stop" { Stop-April }
    "restart" { Restart-April }
    "status" { Show-Status }
}
