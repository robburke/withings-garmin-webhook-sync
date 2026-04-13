@echo off
REM Wrapper for Windows Task Scheduler.
REM Activates the venv and runs the Withings -> Garmin sync daemon.

cd /d "E:\projects\ws\withings-garmin-webhook-sync"
venv\Scripts\python.exe sync_daemon.py
