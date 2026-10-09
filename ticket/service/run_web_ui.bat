@echo off
echo [INFO] Starting Work Ticket Analysis Web UI...
echo [INFO] Web UI will be available at: http://localhost:7861

cd /d "%~dp0"
REM Add current directory to PYTHONPATH
set PYTHONPATH=%CD%

python web_ui.py
pause
