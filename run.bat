@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Antigravity Launcher
python launcher.py
if errorlevel 1 (
    echo.
    echo [错误] 启动程序异常退出。请检查 Python 环境及依赖。
    pause
)
