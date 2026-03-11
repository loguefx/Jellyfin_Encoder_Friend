@echo off
REM Comprehensive diagnostic for installed service
setlocal enabledelayedexpansion

echo ========================================
echo Jellyfin Audio Service - Installation Diagnostic
echo ========================================
echo.

set "SERVICE_DIR=%~dp0"
if "%SERVICE_DIR:~-1%"=="\" set "SERVICE_DIR=%SERVICE_DIR:~0,-1%"

echo Service Directory: %SERVICE_DIR%
echo.

REM Check if directory exists
if not exist "%SERVICE_DIR%" (
    echo [ERROR] Service directory does not exist: %SERVICE_DIR%
    pause
    exit /b 1
)

echo [OK] Directory exists
echo.

REM List all files
echo Files in directory:
dir /b "%SERVICE_DIR%"
echo.

REM Check for executable
if exist "%SERVICE_DIR%\JellyfinAudioService.exe" (
    echo [OK] JellyfinAudioService.exe found
    for %%A in ("%SERVICE_DIR%\JellyfinAudioService.exe") do (
        echo   Size: %%~zA bytes
        echo   Modified: %%~tA
    )
) else (
    echo [ERROR] JellyfinAudioService.exe NOT FOUND
)
echo.

REM Check for Python files
if exist "%SERVICE_DIR%\service.py" (
    echo [OK] service.py found - Python mode available
) else (
    echo [WARNING] service.py not found
)
echo.

REM Check for DLLs
echo Checking for DLLs:
if exist "%SERVICE_DIR%\python*.dll" (
    echo [OK] Python DLLs found:
    dir /b "%SERVICE_DIR%\python*.dll"
) else (
    echo [WARNING] No Python DLLs found in service directory
    echo This may cause crashes if DLLs are not in PATH
)
echo.

REM Check Visual C++ Runtime
echo Checking Visual C++ Runtime:
reg query "HKLM\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64" >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Visual C++ 2015-2022 Runtime detected
) else (
    echo [WARNING] Visual C++ Runtime may be missing
    echo Download: https://aka.ms/vs/17/release/vc_redist.x64.exe
)
echo.

REM Check Windows Event Viewer for crashes
echo Checking Windows Event Viewer for recent crashes...
wevtutil qe Application /c:5 /f:text /q:"*[System[Provider[@Name='Application Error']] and System[TimeCreated[timediff(@SystemTime) <= 3600000]]]" | findstr /i "jellyfin\|JellyfinAudioService" > "%TEMP%\jellyfin_crashes.txt" 2>nul

if exist "%TEMP%\jellyfin_crashes.txt" (
    for %%A in ("%TEMP%\jellyfin_crashes.txt") do set "CRASH_SIZE=%%~zA"
    if !CRASH_SIZE! GTR 0 (
        echo [FOUND] Recent crash events:
        type "%TEMP%\jellyfin_crashes.txt"
    ) else (
        echo [OK] No recent crash events found
    )
) else (
    echo [OK] No recent crash events found
)
echo.

REM Try to run executable with error capture
echo ========================================
echo Testing Executable...
echo ========================================
echo.

if exist "%SERVICE_DIR%\JellyfinAudioService.exe" (
    echo Attempting to run: "%SERVICE_DIR%\JellyfinAudioService.exe" --help
    echo.
    
    set "OUTPUT_FILE=%SERVICE_DIR%\test_output.txt"
    set "ERROR_FILE=%SERVICE_DIR%\test_error.txt"
    
    REM Try running with timeout (5 seconds)
    timeout /t 1 /nobreak >nul
    "%SERVICE_DIR%\JellyfinAudioService.exe" --help > "%OUTPUT_FILE%" 2> "%ERROR_FILE%"
    set EXIT_CODE=%errorlevel%
    
    echo Exit code: !EXIT_CODE!
    echo.
    
    if exist "%OUTPUT_FILE%" (
        for %%A in ("%OUTPUT_FILE%") do set "OUTPUT_SIZE=%%~zA"
        if !OUTPUT_SIZE! GTR 0 (
            echo Output:
            type "%OUTPUT_FILE%"
            echo.
        )
    )
    
    if exist "%ERROR_FILE%" (
        for %%A in ("%ERROR_FILE%") do set "ERROR_SIZE=%%~zA"
        if !ERROR_SIZE! GTR 0 (
            echo Errors:
            type "%ERROR_FILE%"
            echo.
        )
    )
    
    if !EXIT_CODE! neq 0 (
        echo [ERROR] Executable exited with code !EXIT_CODE!
        echo Check Windows Event Viewer for more details
    )
) else (
    echo [ERROR] Cannot test - executable not found
)
echo.

REM Check log files
echo ========================================
echo Checking Log Files...
echo ========================================
echo.

if exist "%SERVICE_DIR%\service_console.log" (
    echo [FOUND] service_console.log - Last 20 lines:
    powershell -Command "Get-Content '%SERVICE_DIR%\service_console.log' -Tail 20 -ErrorAction SilentlyContinue"
    echo.
)

if exist "%SERVICE_DIR%\service_crash.log" (
    echo [FOUND] service_crash.log - Last 20 lines:
    powershell -Command "Get-Content '%SERVICE_DIR%\service_crash.log' -Tail 20 -ErrorAction SilentlyContinue"
    echo.
)

if exist "%SERVICE_DIR%\service_error.log" (
    echo [FOUND] service_error.log - Last 10 lines:
    powershell -Command "Get-Content '%SERVICE_DIR%\service_error.log' -Tail 10 -ErrorAction SilentlyContinue"
    echo.
)

echo ========================================
echo Diagnostic Complete
echo ========================================
echo.
pause









