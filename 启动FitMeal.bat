@echo off
setlocal
cd /d "%~dp0"
title FitMeal Local Demo

where uv >nul 2>&1
if errorlevel 1 (
    echo.
    echo [FitMeal] uv was not found. Install uv first.
    pause
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0server\start.ps1"
if errorlevel 1 (
    echo.
    echo [FitMeal] Startup failed. Review the messages above.
    pause
)

endlocal
