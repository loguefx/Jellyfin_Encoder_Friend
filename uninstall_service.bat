@echo off
REM Change to the directory where this batch file is located
cd /d "%~dp0"

echo Uninstalling Jellyfin Audio Service...
echo Working directory: %CD%
echo.

REM Check if service.py exists
if not exist "service.py" (
    echo ERROR: service.py not found in current directory!
    echo Expected: %CD%\service.py
    echo.
    echo Please run this script from the Jellyfin audio tool directory.
    pause
    exit /b 1
)

echo Stopping service (if running)...
python service.py stop
if errorlevel 1 (
    echo Service was not running or stop failed (this is usually OK)
)
echo.
echo Removing service...
python service.py remove
if errorlevel 1 (
    echo.
    echo ERROR: Service removal failed!
    echo Please check the error messages above.
    pause
    exit /b 1
)
echo.
echo Service uninstalled successfully.
pause




