@echo off
echo Starting Construction Hazard Detection Services...

:: 1. Detection API (Port 8000)
start "Detection API" cmd /k "uvicorn examples.YOLO_server_api.backend.app:app --host 127.0.0.1 --port 8000 --workers 1"

:: 2. Violation Record API (Port 8002)
start "Violation Record API" cmd /k "uvicorn examples.violation_records.app:app --host 127.0.0.1 --port 8002 --workers 1"

:: 3. Notification API (Port 8003)
start "Notification API" cmd /k "uvicorn examples.local_notification_server.app:app --host 127.0.0.1 --port 8003 --workers 1"

:: 4. DB Management API (Port 8005)
start "DB Management API" cmd /k "uvicorn examples.db_management.app:app --host 127.0.0.1 --port 8005 --workers 1"

:: 5. Streaming Web Backend (Port 8800)
start "Streaming Web Backend" cmd /k "uvicorn examples.streaming_web.backend.app:app --host 127.0.0.1 --port 8800 --workers 1"

:: 6. Ticket Agent API (Port 8011)
cd ..
start "Ticket Agent API" cmd /k "uvicorn ticket.service.api_server:app --host 127.0.0.1 --port 8011 --workers 1"
cd Construction-Hazard-Detection

echo All services have been launched in separate windows.
echo Please ensure your database and Redis are running.
echo To start the main program, run: python main.py
pause
