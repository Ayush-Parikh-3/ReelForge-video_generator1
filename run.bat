@echo off
title ReelForge Studio
echo ===================================================
echo             Launching ReelForge Studio
echo ===================================================
echo.
cd /d "%~dp0"
echo Starting FastAPI Web Server at http://localhost:8000 ...
python -m uvicorn server:app --host 0.0.0.0 --port 8000 --reload
pause
