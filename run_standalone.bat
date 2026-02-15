@echo off
REM Run the Jellyfin Audio Service standalone (not as Windows service)
REM This uses your logged-in user's credentials automatically for UNC paths
REM Useful for testing and when service account configuration is problematic

echo Starting Jellyfin Audio Service (standalone mode)...
echo.
echo Access the web UI at http://localhost:8080
echo Press Ctrl+C to stop
echo.

cd /d %~dp0

REM Check if Python is available
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH
    echo Please install Python 3.8+ and add it to PATH
    echo.
    pause
    exit /b 1
)

python --version
echo.

REM Check if app.py exists
if not exist "app.py" (
    echo [ERROR] app.py not found!
    echo Expected: %CD%\app.py
    echo.
    pause
    exit /b 1
)

echo Running: python app.py
echo.
echo ========================================
echo.

REM Run Python script directly - uses logged-in user's credentials
python app.py
set EXIT_CODE=%errorlevel%

echo.
echo ========================================
echo Exit code: %EXIT_CODE%
echo ========================================
echo.

REM Keep window open
pause
exit /b %EXIT_CODE%
