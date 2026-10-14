@echo off
rem Serve the app on this PC (and your home Wi-Fi). Open http://localhost:8770 in a browser.
cd /d "%~dp0"
start "" http://localhost:8770
"%~dp0.venv\Scripts\python.exe" -m http.server 8770 --directory app
