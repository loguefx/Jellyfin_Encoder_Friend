@echo off
REM Simple terminal wrapper to run the service executable with visible output
setlocal enabledelayedexpansion

set "SERVICE_DIR=%~dp0"
if "%SERVICE_DIR:~-1%"=="\" set "SERVICE_DIR=%SERVICE_DIR:~0,-1%"

REM Keep console window open
title Jellyfin Audio Service

echo ========================================
echo Jellyfin Audio Service
echo ========================================
echo.
echo Directory: %SERVICE_DIR%
echo.

REM Check if executable exists
if not exist "%SERVICE_DIR%\JellyfinAudioService.exe" (
    echo [ERROR] JellyfinAudioService.exe not found!
    echo Expected: %SERVICE_DIR%\JellyfinAudioService.exe
    echo.
    pause
    exit /b 1
)

REM Get command line arguments (everything after batch file name)
set "ARGS=%*"

if "%ARGS%"=="" (
    echo Usage: run_service_terminal.bat [command]
    echo.
    echo Commands:
    echo   install  - Install the Windows Service
    echo   start    - Start the Windows Service
    echo   stop     - Stop the Windows Service
    echo   remove   - Remove the Windows Service
    echo   debug    - Run in debug mode (not as service)
    echo.
    echo Example: run_service_terminal.bat install
    echo.
    pause
    exit /b 0
)

echo Running: JellyfinAudioService.exe %ARGS%
echo.
echo ========================================
echo.

REM Run the executable - output will be visible in this console
"%SERVICE_DIR%\JellyfinAudioService.exe" %ARGS%
set EXIT_CODE=%errorlevel%

echo.
echo ========================================
echo Exit code: %EXIT_CODE%
echo ========================================
echo.

REM Keep window open so user can see results
pause
exit /b %EXIT_CODE%









