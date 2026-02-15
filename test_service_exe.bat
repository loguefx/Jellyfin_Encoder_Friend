@echo off
echo ========================================
echo Testing Service Executable
echo ========================================
echo.

REM Get the directory where this script is located
set "SERVICE_DIR=%~dp0"
if "%SERVICE_DIR:~-1%"=="\" set "SERVICE_DIR=%SERVICE_DIR:~0,-1%"

echo Service directory: %SERVICE_DIR%
echo.

REM Check if executables exist
if not exist "%SERVICE_DIR%\JellyfinAudioService.exe" (
    echo ERROR: JellyfinAudioService.exe not found in %SERVICE_DIR%
    pause
    exit /b 1
)

echo [OK] Found JellyfinAudioService.exe
echo File size:
dir "%SERVICE_DIR%\JellyfinAudioService.exe" | findstr JellyfinAudioService.exe
echo.

echo Testing executable with no arguments (should show message box or error)...
echo.
"%SERVICE_DIR%\JellyfinAudioService.exe"
echo.
echo Exit code: %errorlevel%
echo.

echo Testing executable with 'help' argument...
echo.
"%SERVICE_DIR%\JellyfinAudioService.exe" help
echo.
echo Exit code: %errorlevel%
echo.

echo Checking for log files...
if exist "%SERVICE_DIR%\service_error.log" (
    echo.
    echo Found service_error.log:
    echo ========================================
    type "%SERVICE_DIR%\service_error.log"
    echo ========================================
) else (
    echo No service_error.log found.
)

if exist "%SERVICE_DIR%\service.log" (
    echo.
    echo Found service.log:
    echo ========================================
    type "%SERVICE_DIR%\service.log"
    echo ========================================
) else (
    echo No service.log found.
)

echo.
echo ========================================
echo Test Complete
echo ========================================
pause









