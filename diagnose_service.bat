@echo off
echo ========================================
echo Service Diagnostic Tool
echo ========================================
echo.

REM Get the directory where this script is located
set "SERVICE_DIR=%~dp0"
if "%SERVICE_DIR:~-1%"=="\" set "SERVICE_DIR=%SERVICE_DIR:~0,-1%"

echo Service directory: %SERVICE_DIR%
echo.

REM Check if executables exist
if not exist "%SERVICE_DIR%\JellyfinAudioService.exe" (
    echo ERROR: JellyfinAudioService.exe not found!
    echo Expected location: %SERVICE_DIR%\JellyfinAudioService.exe
    pause
    exit /b 1
)

echo [OK] Found JellyfinAudioService.exe
echo.

REM Check file size
echo File information:
dir "%SERVICE_DIR%\JellyfinAudioService.exe" | findstr JellyfinAudioService.exe
echo.

REM Check for required files
echo Checking for required files...
if exist "%SERVICE_DIR%\config.json" (
    echo [OK] config.json found
) else (
    echo [WARN] config.json not found - will be created on first run
)
if exist "%SERVICE_DIR%\templates" (
    echo [OK] templates directory found
) else (
    echo [FAIL] templates directory not found!
)
if exist "%SERVICE_DIR%\static" (
    echo [OK] static directory found
) else (
    echo [FAIL] static directory not found!
)
echo.

REM Check for log files
echo Checking for log files...
if exist "%SERVICE_DIR%\service_crash.log" (
    echo.
    echo ========================================
    echo CRASH LOG FOUND:
    echo ========================================
    type "%SERVICE_DIR%\service_crash.log"
    echo ========================================
    echo.
) else (
    echo [INFO] No crash log found (this is OK if service hasn't run yet)
)

if exist "%SERVICE_DIR%\service_error.log" (
    echo.
    echo ========================================
    echo ERROR LOG FOUND:
    echo ========================================
    type "%SERVICE_DIR%\service_error.log"
    echo ========================================
    echo.
)

if exist "%SERVICE_DIR%\service_startup.log" (
    echo.
    echo ========================================
    echo STARTUP LOG FOUND:
    echo ========================================
    type "%SERVICE_DIR%\service_startup.log"
    echo ========================================
    echo.
)

echo.
echo Testing executable with 'help' command...
echo.
"%SERVICE_DIR%\JellyfinAudioService.exe" help 2>&1
set TEST_RESULT=%errorlevel%
echo.
echo Help command exit code: %TEST_RESULT%
echo.

if %TEST_RESULT% neq 0 (
    echo WARNING: Executable may have issues!
    echo Check logs above for details.
) else (
    echo [OK] Executable responds to help command
)

echo.
echo ========================================
echo Diagnostic Complete
echo ========================================
pause









