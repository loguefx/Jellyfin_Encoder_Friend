@echo off
REM Test using Python script directly (bypasses executable issues)
setlocal

set "SERVICE_DIR=C:\Program Files (x86)\JellyfinAudioService"

echo ========================================
echo Testing with Python Script (Fallback)
echo ========================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH
    echo Cannot use Python fallback method
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

REM Change to service directory
cd /d "%SERVICE_DIR%"

echo Running: python service.py install
echo.

python service.py install

echo.
echo Exit code: %errorlevel%
echo.

if %errorlevel% equ 0 (
    echo [SUCCESS] Service installed using Python script!
    echo.
    echo You can use Python script for all service commands:
    echo   python service.py start
    echo   python service.py stop
    echo   python service.py remove
) else (
    echo [ERROR] Python script also failed
    echo Check error messages above
)

echo.
pause









