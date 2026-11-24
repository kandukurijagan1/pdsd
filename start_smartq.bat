@echo off
title SmartQ Realtime Enterprise Launcher - PDSD Prototype
echo ===================================================================
echo   SmartQ - Smart Queue Management & Automated Token Calling
echo   Subject: Principles of Digital Systems and Design (PDSD)
echo ===================================================================
echo.
echo [1/3] Verifying Local WhatsApp Automated Microservice (:3005)...
curl -s http://127.0.0.1:3005/api/whatsapp/status >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo       [OK] WhatsApp Microservice is running and authenticated on port 3005.
) else (
    echo       [NOTE] Ensure WhatsApp microservice is running on port 3005 for direct message delivery.
)
echo.
echo [2/3] Launching Live Web Portal in default browser...
start https://kandukurijagan1.github.io/pdsd/
echo.
echo [3/3] Starting Local SmartQ Flask Server & Realtime Bridge Daemon (:5000)...
cd /d "%~dp0\SmartQ"
call start_server.bat
