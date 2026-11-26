@echo off
echo Starting Road Intelligence Platform...
start "RoadSense Backend (8000)" cmd /k "cd /d %~dp0 && python -m uvicorn backend.main:app --reload --port 8000"
start "RoadSense User App (5173)" cmd /k "cd /d %~dp0apps\user-app && npm.cmd run dev"
start "RoadSense Admin App (5174)" cmd /k "cd /d %~dp0apps\admin-app && npm.cmd run dev"
echo.
echo Services launching:
echo   Backend API : http://127.0.0.1:8000/docs
echo   User App    : http://localhost:5173
echo   Admin App   : http://localhost:5174

