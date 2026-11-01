@echo off
setlocal DisableDelayedExpansion
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0environment\start.ps1" %*
exit /b %ERRORLEVEL%
