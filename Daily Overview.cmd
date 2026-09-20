@echo off
rem Double-click to launch the Daily Overview app (visuals + voice).
start "" powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "%~dp0run-app.ps1"
