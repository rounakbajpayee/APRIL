@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0aprilctl.ps1" %*
exit /b %errorlevel%
