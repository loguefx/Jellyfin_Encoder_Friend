@echo off
REM Show which process is using port 8080 (default Jellyfin web port).
cd /d "%~dp0"
echo.
echo Processes using port 8080:
echo.
netstat -ano | findstr ":8080"
echo.
echo The last column is the PID. To stop a process, run as Administrator:
echo   taskkill /PID <pid> /F
echo.
echo Or stop the Windows service: services.msc -> "Jellyfin Audio Conversion Service" -> Stop
echo Or close JellyfinAudioServiceUI.exe / python app.py if you ran the app manually.
echo.
pause
