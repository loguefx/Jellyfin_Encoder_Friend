@echo off
REM Alternative: Run Python script directly (if Python is installed)
REM This bypasses the executable entirely and runs the Python source
setlocal enabledelayedexpansion

set "SERVICE_DIR=%~dp0"
if "%SERVICE_DIR:~-1%"=="\" set "SERVICE_DIR=%SERVICE_DIR:~0,-1%"

REM Keep console window open
title Jellyfin Audio Service (Python)

echo ========================================
echo Jellyfin Audio Service (Python Mode)
echo ========================================
echo.
echo Directory: %SERVICE_DIR%
echo.

REM Check if Python is available
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH
    echo Please install Python 3.8+ or use run_service_terminal.bat instead
    echo.
    pause
    exit /b 1
)

python --version
echo.

REM Check if service.py exists
if not exist "%SERVICE_DIR%\service.py" (
    echo [ERROR] service.py not found!
    echo Expected: %SERVICE_DIR%\service.py
    echo.
    echo Note: This script requires the Python source files.
    echo If you only have the executable, use run_service_terminal.bat instead
    echo.
    pause
    exit /b 1
)

REM Get command line arguments
set "ARGS=%*"

if "%ARGS%"=="" (
    echo Usage: run_service_python.bat [command]
    echo.
    echo Commands:
    echo   install  - Install the Windows Service
    echo   start    - Start the Windows Service
    echo   stop     - Stop the Windows Service
    echo   remove   - Remove the Windows Service
    echo.
    echo Example: run_service_python.bat install
    echo.
    pause
    exit /b 0
)

echo Running: python service.py %ARGS%
echo.
echo ========================================
echo.

REM Change to service directory
cd /d "%SERVICE_DIR%"

REM Run Python script directly - all output visible
python service.py %ARGS%
set EXIT_CODE=%errorlevel%

echo.
echo ========================================
echo Exit code: %EXIT_CODE%
echo ========================================
echo.

REM Keep window open
pause
exit /b %EXIT_CODE%









