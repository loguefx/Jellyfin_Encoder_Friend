@echo off
REM Change to the directory where this batch file is located
cd /d "%~dp0"

echo Installing Jellyfin Audio Service...
echo Working directory: %CD%
echo.

REM Check for admin rights
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: This script must be run as Administrator!
    echo Right-click and select "Run as administrator"
    echo.
    pause
    exit /b 1
)

REM Check if service.py exists
if not exist "service.py" (
    echo ERROR: service.py not found in current directory!
    echo Expected: %CD%\service.py
    echo.
    echo Please run this script from the Jellyfin audio tool directory.
    pause
    exit /b 1
)

python service.py install
if errorlevel 1 (
    echo.
    echo ERROR: Service installation failed!
    echo Please check the error messages above.
    pause
    exit /b 1
)
echo.
echo Service installed successfully!
echo.
echo IMPORTANT: To access UNC paths (like standalone mode), the service
echo needs to run under your user account, not the SYSTEM account.
echo.
echo Would you like to configure the service account now? (Y/N)
set /p CONFIGURE_ACCOUNT="> "
if /i "%CONFIGURE_ACCOUNT%"=="Y" (
    echo.
    echo Running configure_service_account.bat...
    echo.
    call configure_service_account.bat
) else (
    echo.
    echo You can configure the service account later by running:
    echo   configure_service_account.bat
    echo.
    echo Or manually via Services (services.msc):
    echo   1. Find "Jellyfin Audio Conversion Service"
    echo   2. Right-click → Properties → Log On tab
    echo   3. Select "This account" and enter your Windows username/password
    echo.
)
echo.
echo You can now start it with:
echo   python service.py start
echo.
echo Or use Windows Services manager to start/stop it.
pause




