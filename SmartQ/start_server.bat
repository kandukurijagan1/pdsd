@echo off
title SmartQ Server - PDSD Prototype
echo =======================================================
echo  SmartQ - Queue Management & Automated Token Calling
echo  Principles of Digital Systems and Design (PDSD)
echo =======================================================
echo.
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo [INFO] Creating Python virtual environment...
    python -m venv venv
    echo [INFO] Installing required dependencies...
    venv\Scripts\pip.exe install -r requirements.txt
)

echo [INFO] Starting Flask Server on port 5000...
echo [INFO] Press Ctrl+C to stop.
echo.
venv\Scripts\python.exe app.py
pause
