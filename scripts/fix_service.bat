@echo off
REM Fix service configuration to use the correct executable
setlocal

set "SERVICE_DIR=C:\Program Files\JellyfinAudioService"

echo ========================================
echo Fixing Service Configuration
echo ========================================
echo.

REM Stop and remove existing service
echo Stopping service (if running)...
net stop JellyfinAudioService >nul 2>&1

echo Removing old service...
sc delete JellyfinAudioService >nul 2>&1
timeout /t 2 /nobreak >nul

echo.
echo Reinstalling service with correct configuration...
cd /d "%SERVICE_DIR%"

REM Reinstall using the executable
"%SERVICE_DIR%\JellyfinAudioService.exe" install

if %errorlevel% equ 0 (
    echo.
    echo [OK] Service reinstalled successfully!
    echo.
    echo Starting service...
    "%SERVICE_DIR%\JellyfinAudioService.exe" start
    
    if %errorlevel% equ 0 (
        echo.
        echo [OK] Service started successfully!
    ) else (
        echo.
        echo [WARNING] Service start had issues, but service is installed.
        echo Try starting manually: net start JellyfinAudioService
    )
) else (
    echo.
    echo [ERROR] Service reinstallation failed!
)

echo.
pause









