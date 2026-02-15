@echo off
REM Post-installation script - runs after MSI installation
REM This automatically installs and starts the Windows Service using Python

setlocal enabledelayedexpansion

echo ========================================
echo Jellyfin Audio Service - Post Installation
echo ========================================
echo.

REM Get service directory from MSI installation path
REM MSI sets INSTALLDIR property - check common locations
set "SERVICE_DIR="

if exist "C:\Program Files\JellyfinAudioService" (
    set "SERVICE_DIR=C:\Program Files\JellyfinAudioService"
) else if exist "C:\Program Files (x86)\JellyfinAudioService" (
    set "SERVICE_DIR=C:\Program Files (x86)\JellyfinAudioService"
) else (
    REM Try to get from current directory
    set "SERVICE_DIR=%~dp0"
    if "%SERVICE_DIR:~-1%"=="\" set "SERVICE_DIR=%SERVICE_DIR:~0,-1%"
)

if "%SERVICE_DIR%"=="" (
    echo [ERROR] Could not determine service installation directory
    echo Please run install_service_helper.bat manually
    pause
    exit /b 1
)

echo Service Directory: %SERVICE_DIR%
echo.

REM Check for Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH
    echo.
    echo Please install Python 3.8+ and add it to PATH, then run:
    echo   python "%SERVICE_DIR%\service.py" install
    echo   python "%SERVICE_DIR%\service.py" start
    echo.
    pause
    exit /b 1
)

python --version
echo.

REM Check if service.py exists
if not exist "%SERVICE_DIR%\service.py" (
    echo [ERROR] service.py not found in %SERVICE_DIR%
    echo Python source files may not have been included in installer
    pause
    exit /b 1
)

echo [OK] service.py found
echo.

REM Install the service
echo ========================================
echo Installing Windows Service...
echo ========================================
echo.

cd /d "%SERVICE_DIR%"
python service.py install
set INSTALL_RESULT=%errorlevel%

if %INSTALL_RESULT% neq 0 (
    echo.
    echo [ERROR] Service installation failed!
    echo Exit code: %INSTALL_RESULT%
    echo.
    echo Please check error messages above and try running manually:
    echo   python "%SERVICE_DIR%\service.py" install
    echo.
    pause
    exit /b 1
)

echo.
echo [OK] Service installed successfully!
echo.

REM Start the service
echo ========================================
echo Starting Windows Service...
echo ========================================
echo.

python service.py start
set START_RESULT=%errorlevel%

if %START_RESULT% neq 0 (
    echo.
    echo [WARNING] Service start failed (exit code: %START_RESULT%)
    echo The service is installed but not started.
    echo.
    echo You can start it manually using:
    echo   python "%SERVICE_DIR%\service.py" start
    echo   OR
    echo   net start JellyfinAudioService
    echo   OR
    echo   Use Windows Services Manager (services.msc)
    echo.
) else (
    echo.
    echo [OK] Service started successfully!
    echo.
    echo The service is now running.
    echo Web interface: http://localhost:8080
    echo.
)

echo ========================================
echo Installation Complete!
echo ========================================
echo.
echo Service Management Commands:
echo   Start:  python "%SERVICE_DIR%\service.py" start
echo   Stop:   python "%SERVICE_DIR%\service.py" stop
echo   Remove: python "%SERVICE_DIR%\service.py" remove
echo.
echo Web Interface: http://localhost:8080
echo.
pause









