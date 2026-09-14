@echo off
REM =====================================================================
REM  INFORAXIS - Windows one-click start
REM  Double-click this file every time you want to use the application.
REM =====================================================================
title INFORAXIS - Server
cd /d "%~dp0"


echo.
echo  ============================================================
echo   Starting INFORAXIS...
echo   Open your browser at:  http://127.0.0.1:5000
echo   Press CTRL+C to stop the server.
echo  ============================================================
echo.

python run_web.py

echo.
echo  The server has stopped. If you saw an error above, check
echo  the "Troubleshooting" section in INSTALL.md.
echo.
pause
