@echo off
REM Simple test - just try to run the executable and see what happens
setlocal

set "SERVICE_DIR=C:\Program Files (x86)\JellyfinAudioService"

echo Testing executable in: %SERVICE_DIR%
echo.

if not exist "%SERVICE_DIR%\JellyfinAudioService.exe" (
    echo ERROR: Executable not found!
    pause
    exit /b 1
)

echo Running executable...
echo.

REM Run with explicit path quoting for spaces
"%SERVICE_DIR%\JellyfinAudioService.exe" --help

echo.
echo Exit code: %errorlevel%
echo.
pause









