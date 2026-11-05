@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
if errorlevel 1 exit /b 1
title Antigravity Launcher
if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" launcher.py %*
) else (
    python launcher.py %*
)
set "ANTIGRAVITY_EXIT=%ERRORLEVEL%"
if not "%ANTIGRAVITY_EXIT%"=="0" (
    echo.
    echo [ERROR] Launcher exited with an error. Check Python and its dependencies.
    pause
)
exit /b %ANTIGRAVITY_EXIT%
