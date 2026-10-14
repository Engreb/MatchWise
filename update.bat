@echo off
rem Refresh results, fixtures and predictions. Run before each round of matches.
cd /d "%~dp0engine"
"%~dp0.venv\Scripts\python.exe" -m matchwise update
pause
