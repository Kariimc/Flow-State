@echo off
cd /d "%~dp0"
rem launch windowless via pythonw (no console, no pause) — the bat closes at once
if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" flow.py
) else (
  start "" ".venv\Scripts\python.exe" flow.py
)
