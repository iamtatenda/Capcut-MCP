@echo off
REM Google Flow Persistent Chrome CDP Daemon Launcher
REM Keeps a background Chrome instance running on port 9222 for instant attachment.
cd /d "%~dp0"
python flow_daemon.py
if %ERRORLEVEL% EQU 0 (
    echo [SUCCESS] Chrome CDP daemon is active on port 9222.
) else (
    echo [ERROR] Failed to start Chrome CDP daemon.
)
timeout /t 2 /nobreak >nul
