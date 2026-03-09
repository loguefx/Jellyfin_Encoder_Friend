@echo off
REM Manual removal of Jellyfin Audio Conversion Service using sc.exe.
REM Use this when the MSI uninstall fails (e.g. error 2762) or the service won't start (e.g. error 1053).
REM Run this script as Administrator.

set SVC_NAME=JellyfinAudioService

echo Stopping and removing service: %SVC_NAME%
echo You must run this as Administrator.
echo.

sc stop %SVC_NAME%
if errorlevel 1 (
    echo Service was not running or stop failed. Continuing...
) else (
    echo Service stopped. Waiting 3 seconds...
    timeout /t 3 /nobreak >nul
)

sc delete %SVC_NAME%
if errorlevel 1 (
    echo.
    echo DELETE failed. Try running this batch file by right-click - Run as administrator.
    pause
    exit /b 1
)

echo.
echo Service %SVC_NAME% removed successfully.
echo You can now uninstall the app via Settings ^> Apps (or re-run the MSI uninstaller if needed).
pause
