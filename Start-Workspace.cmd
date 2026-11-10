@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-Workspace.ps1" -Engine auto
if errorlevel 1 pause
