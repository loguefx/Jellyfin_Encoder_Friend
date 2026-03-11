@echo off
REM Wrapper to run service executable and capture ALL output including Windows errors
setlocal enabledelayedexpansion

set "SERVICE_DIR=%~dp0"
if "%SERVICE_DIR:~-1%"=="\" set "SERVICE_DIR=%SERVICE_DIR:~0,-1%"

set "LOG_FILE=%SERVICE_DIR%\executable_run.log"
set "ERROR_FILE=%SERVICE_DIR%\executable_error.log"

echo ======================================== > "%LOG_FILE%"
echo Service Executable Test >> "%LOG_FILE%"
echo ======================================== >> "%LOG_FILE%"
echo Date: %DATE% %TIME% >> "%LOG_FILE%"
echo Directory: %SERVICE_DIR% >> "%LOG_FILE%"
echo Command: %* >> "%LOG_FILE%"
echo. >> "%LOG_FILE%"

if not exist "%SERVICE_DIR%\JellyfinAudioService.exe" (
    echo ERROR: JellyfinAudioService.exe not found! >> "%ERROR_FILE%"
    echo ERROR: JellyfinAudioService.exe not found!
    pause
    exit /b 1
)

echo Running: "%SERVICE_DIR%\JellyfinAudioService.exe" %* >> "%LOG_FILE%"
echo Running: "%SERVICE_DIR%\JellyfinAudioService.exe" %*
echo.

REM Try to run the executable and capture output
"%SERVICE_DIR%\JellyfinAudioService.exe" %* >> "%LOG_FILE%" 2>> "%ERROR_FILE%"
set EXIT_CODE=%errorlevel%

echo. >> "%LOG_FILE%"
echo Exit code: !EXIT_CODE! >> "%LOG_FILE%"
echo Exit code: !EXIT_CODE!

if !EXIT_CODE! neq 0 (
    echo.
    echo ERROR: Executable exited with code !EXIT_CODE!
    echo Check logs: %LOG_FILE% and %ERROR_FILE%
    echo.
    if exist "%ERROR_FILE%" (
        echo Error output:
        type "%ERROR_FILE%"
    )
    pause
)

endlocal
exit /b %EXIT_CODE%









