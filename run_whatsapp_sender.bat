@echo off
title SmartQ Live WhatsApp Sender Daemon
color 0a
echo ===================================================================
echo   SmartQ - Dedicated Realtime WhatsApp Sender Daemon
echo   Principles of Digital Systems and Design (PDSD)
echo ===================================================================
echo.
echo [1/2] Connecting to Supabase Cloud & Local Queue...
echo [2/2] Initializing WhatsApp Automated Web Engine...
echo.
echo ===================================================================
echo  Listening for new patient tokens & emergency calls from:
echo   - Live Hosted Web (https://kandukurijagan1.github.io/pdsd/)
echo   - Localhost Kiosk / ESP32 Physical Device
echo ===================================================================
echo.

cd /d "%~dp0\SmartQ"

if exist "venv\Scripts\python.exe" (
    venv\Scripts\python.exe realtime_bridge.py
) else (
    python realtime_bridge.py
)

pause
