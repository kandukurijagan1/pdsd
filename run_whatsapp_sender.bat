@echo off
title SmartQ Dedicated Offline WhatsApp Sender & Live Cloud Gateway
color 0a
echo ===================================================================
echo   SmartQ - Dedicated WhatsApp Microservice & Cloud Sync Daemon
echo   Principles of Digital Systems and Design (PDSD)
echo ===================================================================
echo.
echo [1/2] Starting Authenticated WhatsApp Microservice on port 3005...
start "SmartQ-WhatsApp-Port3005" /min cmd /c "cd /d "%~dp0whatsapp_service" && node service.js"

echo [2/2] Launching Realtime Cloud-to-Local WhatsApp Bridge...
echo       - Connecting to Live Hosted Web: https://kandukurijagan1.github.io/pdsd/
echo       - Syncing with Supabase Cloud: mnsfeojsbzomvhcuiaur.supabase.co
echo       - Forwarding new tokens and emergencies to WhatsApp (+91 8367047947)...
echo.
echo ===================================================================
echo   System is active! Keep this window open in background.
echo ===================================================================
echo.

cd /d "%~dp0SmartQ"
if exist "venv\Scripts\python.exe" (
    venv\Scripts\python.exe realtime_bridge.py
) else (
    python realtime_bridge.py
)

pause
