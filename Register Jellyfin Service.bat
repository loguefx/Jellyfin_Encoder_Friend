@echo off
REM Run as Administrator to register the Jellyfin Audio Conversion Service.
REM Use this after installing the MSI (the MSI no longer registers the service automatically).
cd /d "%~dp0"
echo Registering Jellyfin Audio Conversion Service...
"%~dp0JellyfinAudioService.exe" install
if errorlevel 1 (
    echo.
    echo Failed. Make sure you right-click this file and choose "Run as administrator".
    pause
    exit /b 1
)
echo.
echo Service registered. Start it from Services (services.msc) or run: JellyfinAudioService.exe start
pause
