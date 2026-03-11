@echo off
echo ========================================
echo Jellyfin Audio Service - Installation Helper
echo ========================================
echo.

REM Check for admin rights
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: This script must be run as Administrator!
    echo Right-click and select "Run as administrator"
    pause
    exit /b 1
)

echo [OK] Running as Administrator
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
echo File info:
dir "%SERVICE_DIR%\JellyfinAudioService.exe" | findstr JellyfinAudioService.exe
echo.

REM Clear any existing crash logs for fresh start
if exist "%SERVICE_DIR%\service_crash.log" (
    echo Clearing old crash log...
    del "%SERVICE_DIR%\service_crash.log"
)
if exist "%SERVICE_DIR%\service_error.log" (
    echo Clearing old error log...
    del "%SERVICE_DIR%\service_error.log"
)
if exist "%SERVICE_DIR%\service_startup.log" (
    echo Clearing old startup log...
    del "%SERVICE_DIR%\service_startup.log"
)
echo.

REM Install the service
echo Installing Windows Service...
echo.

REM Use Python script (primary method - executable has dependency issues)
if exist "%SERVICE_DIR%\service.py" (
    python --version >nul 2>&1
    if %errorlevel% equ 0 (
        echo [OK] Python detected - using Python script method
        echo Running: python service.py install
        echo.
        cd /d "%SERVICE_DIR%"
        python service.py install
        set INSTALL_RESULT=%errorlevel%
    ) else (
        echo [ERROR] Python is required but not found in PATH
        echo.
        echo Please install Python 3.8+ and add it to PATH, or
        echo manually install the service using:
        echo   python "%SERVICE_DIR%\service.py" install
        echo.
        set INSTALL_RESULT=1
    )
) else (
    echo [ERROR] service.py not found in %SERVICE_DIR%
    echo Python source files may not have been included in installer
    echo.
    set INSTALL_RESULT=1
)

echo.
echo Install command exit code: %INSTALL_RESULT%
echo.

if %INSTALL_RESULT% neq 0 (
    echo.
    echo ERROR: Service installation failed!
    echo Exit code: %INSTALL_RESULT%
    echo.
    echo Checking for error logs...
    echo.
    if exist "%SERVICE_DIR%\service_crash.log" (
        echo ========================================
        echo CRASH LOG (service_crash.log):
        echo ========================================
        type "%SERVICE_DIR%\service_crash.log"
        echo ========================================
        echo.
    )
    if exist "%SERVICE_DIR%\service_error.log" (
        echo ========================================
        echo ERROR LOG (service_error.log):
        echo ========================================
        type "%SERVICE_DIR%\service_error.log"
        echo ========================================
        echo.
    )
    if exist "%SERVICE_DIR%\service_startup.log" (
        echo ========================================
        echo STARTUP LOG (service_startup.log):
        echo ========================================
        type "%SERVICE_DIR%\service_startup.log"
        echo ========================================
        echo.
    )
    if exist "%SERVICE_DIR%\service.log" (
        echo ========================================
        echo SERVICE LOG (service.log):
        echo ========================================
        type "%SERVICE_DIR%\service.log"
        echo ========================================
        echo.
    )
    echo Please check the error messages above.
    echo All logs are saved in: %SERVICE_DIR%
    pause
    exit /b 1
)

echo.
echo [OK] Service installed successfully!
echo.

REM Start the service
echo Starting Windows Service...
echo.

REM Use Python script to start service
if exist "%SERVICE_DIR%\service.py" (
    python --version >nul 2>&1
    if %errorlevel% equ 0 (
        echo [OK] Using Python script to start service
        echo Running: python service.py start
        echo.
        cd /d "%SERVICE_DIR%"
        python service.py start 2>&1
        set START_RESULT=%errorlevel%
    ) else (
        echo [WARNING] Python not available, trying Windows Service Manager...
        net start JellyfinAudioService 2>&1
        set START_RESULT=%errorlevel%
    )
) else (
    echo [WARNING] service.py not found, trying Windows Service Manager...
    net start JellyfinAudioService 2>&1
    set START_RESULT=%errorlevel%
)

echo.
echo Start command exit code: %START_RESULT%
echo.

if %START_RESULT% neq 0 (
    echo.
    echo WARNING: Service start failed!
    echo You may need to start it manually from Services Manager.
    echo.
    echo Try starting manually:
    echo   python "%SERVICE_DIR%\service.py" start
    echo   OR
    echo   net start JellyfinAudioService
    echo   OR
    echo   Use Windows Services Manager (services.msc)
    echo.
    echo Checking for error logs...
    if exist "%SERVICE_DIR%\service_error.log" (
        echo.
        echo Contents of service_error.log:
        echo ========================================
        type "%SERVICE_DIR%\service_error.log"
        echo ========================================
    )
) else (
    echo.
    echo [OK] Service started successfully!
)

echo.
echo ========================================
echo Installation Complete!
echo ========================================
echo.
echo The service is now running.
echo Web interface: http://localhost:8080
echo.
echo To manage the service (use Python script):
echo   - Stop:   python "%SERVICE_DIR%\service.py" stop
echo   - Start:  python "%SERVICE_DIR%\service.py" start
echo   - Remove: python "%SERVICE_DIR%\service.py" remove
echo   - Or use Windows Services Manager (services.msc)
echo.
pause

