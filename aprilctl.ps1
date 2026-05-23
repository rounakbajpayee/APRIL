param(
    [ValidateSet("start", "stop", "restart", "status")]
    [string]$Action = "status"
)

$ErrorActionPreference = "Stop"
$RepoRoot = $PSScriptRoot
$VenvRoot = Join-Path $RepoRoot ".venv\Scripts"
$Pythonw = Join-Path $VenvRoot "pythonw.exe"
$Python = Join-Path $VenvRoot "python.exe"
$MainScript = Join-Path $RepoRoot "main.py"

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

    # Always use python.exe, never pythonw.exe.
    # pythonw.exe launches with no foreground rights, which causes DWM to
    # silently suppress Tool windows (e.g. the new surface system orb).
    # The console window is hidden below via Win32 ShowWindow instead.
    if (-not (Test-Path $Python)) {
        throw "Could not find python.exe in .venv\Scripts"
    }

    $startArgs = '"' + $MainScript + '"'
    $proc = Start-Process -FilePath $Python -WorkingDirectory $RepoRoot -ArgumentList $startArgs -WindowStyle Normal -PassThru

    # Hide the console window immediately after launch so it does not flash.
    Start-Sleep -Milliseconds 300
    if (-not $proc.HasExited) {
        $sig = '[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);'
        $type = Add-Type -MemberDefinition $sig -Name WinAPI -Namespace Hide -PassThru
        $hwnd = (Get-Process -Id $proc.Id).MainWindowHandle
        if ($hwnd -ne [IntPtr]::Zero) { $type::ShowWindow($hwnd, 0) | Out-Null }
    }
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
