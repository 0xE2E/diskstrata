@echo off
rem Starts DiskStrata and opens your browser. Close this window (or press Ctrl+C) to stop it.
cd /d "%~dp0"
where py >nul 2>nul && (py -3 -m diskstrata %*) || (python -m diskstrata %*)
if errorlevel 1 pause
