# PowerShell wrapper for the Withings Sync local daemon.
# Designed to be invoked via wscript.exe + run-hidden.vbs to avoid
# the console window flash that .bat files produce in Task Scheduler.
#
# Equivalent to the previous run_withings_sync.bat:
#   cd /d "E:\projects\ws\withings-garmin-webhook-sync"
#   venv\Scripts\python.exe sync_daemon.py

Set-Location "E:\projects\ws\withings-garmin-webhook-sync"
& ".\venv\Scripts\python.exe" sync_daemon.py
