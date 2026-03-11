@echo off
REM Configure Jellyfin Audio Service to run under current logged-in user account
REM This gives the service the same network access as standalone mode

echo ========================================
echo Configure Service Account
echo ========================================
echo.
echo This script will configure the Jellyfin Audio Service
echo to run under your logged-in user account.
echo.
echo This allows the service to access UNC paths using your
echo Windows credentials, just like standalone mode.
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

echo [OK] Running as Administrator
echo.

REM Get current logged-in username
for /f "tokens=2" %%a in ('whoami') do set CURRENT_USER=%%a
echo Current user: %CURRENT_USER%
echo.

REM Service name
set SERVICE_NAME=JellyfinAudioService

echo Checking if service exists...
sc query %SERVICE_NAME% >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: Service '%SERVICE_NAME%' is not installed!
    echo Please install the service first using: python service.py install
    echo.
    pause
    exit /b 1
)

echo [OK] Service found
echo.

REM Stop the service if running
echo Stopping service (if running)...
sc stop %SERVICE_NAME% >nul 2>&1
timeout /t 2 /nobreak >nul
echo.

REM Configure service to run under current user account
echo Configuring service to run under: %CURRENT_USER%
echo.
echo NOTE: Windows requires a password to be set for user account services.
echo You will need to set the password manually via Services manager.
echo.
echo Attempting to configure service account (password must be set manually)...
echo.

REM Try to configure with empty password first (Windows may prompt)
sc config %SERVICE_NAME% obj= "%CURRENT_USER%"
if %errorLevel% neq 0 (
    echo.
    echo [INFO] Automatic configuration requires password.
    echo.
    echo Please configure manually via Services (services.msc):
    echo   1. Find "Jellyfin Audio Conversion Service"
    echo   2. Right-click → Properties → Log On tab
    echo   3. Select "This account"
    echo   4. Enter: %CURRENT_USER%
    echo   5. Enter your Windows password
    echo   6. Click OK
    echo.
    echo This gives the service the same network access as standalone mode.
    echo.
    pause
    exit /b 0
)

echo [OK] Service account configured to: %CURRENT_USER%
echo.
echo IMPORTANT: You must set the password manually:
echo   1. Open Services (services.msc)
echo   2. Find "Jellyfin Audio Conversion Service"
echo   3. Right-click → Properties → Log On tab
echo   4. Click "This account" (should show %CURRENT_USER%)
echo   5. Enter your Windows password
echo   6. Click OK
echo.
echo Without the password, the service cannot start under your account.
echo.

echo.
echo [OK] Service configured successfully!
echo.
echo The service will now run under your user account (%CURRENT_USER%)
echo and will have the same network access as standalone mode.
echo.
echo Starting service...
sc start %SERVICE_NAME%
if %errorLevel% equ 0 (
    echo [OK] Service started successfully!
) else (
    echo [WARNING] Service may already be running or failed to start
    echo Check Windows Services (services.msc) for status
)
echo.
pause
