@echo off
rem Run the patcher from source (no exe build).
cd /d "%~dp0"
.venv\Scripts\python.exe app\hok_patcher.py
