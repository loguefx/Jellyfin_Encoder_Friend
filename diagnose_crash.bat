@echo off
REM Comprehensive crash diagnostic script
setlocal enabledelayedexpansion

echo ========================================
echo Jellyfin Audio Service Crash Diagnostic
echo ========================================
echo.

set "SERVICE_DIR=%~dp0"
if "%SERVICE_DIR:~-1%"=="\" set "SERVICE_DIR=%SERVICE_DIR:~0,-1%"

echo Service Directory: %SERVICE_DIR%
echo.

REM Check if executable exists
if not exist "%SERVICE_DIR%\JellyfinAudioService.exe" (
    echo [ERROR] JellyfinAudioService.exe not found!
    echo Expected location: %SERVICE_DIR%\JellyfinAudioService.exe
    pause
    exit /b 1
)

echo [OK] Executable found: %SERVICE_DIR%\JellyfinAudioService.exe
echo.

REM Check file size
for %%A in ("%SERVICE_DIR%\JellyfinAudioService.exe") do set "EXE_SIZE=%%~zA"
echo Executable size: %EXE_SIZE% bytes
if %EXE_SIZE% LSS 1000000 (
    echo [WARNING] Executable seems too small - may be corrupted
)
echo.

REM Check for DLL dependencies
echo Checking for required DLLs...
if exist "%SERVICE_DIR%\python*.dll" (
    echo [OK] Python DLL found
    dir "%SERVICE_DIR%\python*.dll" /b
) else (
    echo [WARNING] Python DLL not found in service directory
    echo This may cause crashes if DLLs are not in PATH
)
echo.

REM Check for Visual C++ runtime
echo Checking Visual C++ Runtime...
reg query "HKLM\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64" >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Visual C++ 2015-2022 Runtime detected
) else (
    echo [WARNING] Visual C++ Runtime may be missing
    echo Download from: https://aka.ms/vs/17/release/vc_redist.x64.exe
)
echo.

REM Check Windows Event Viewer for crashes
echo.
echo Checking Windows Event Viewer for recent crashes...
wevtutil qe Application /c:5 /f:text /q:"*[System[Provider[@Name='Application Error'] or Provider[@Name='Windows Error Reporting']] and System[TimeCreated[timediff(@SystemTime) <= 86400000]]]" | findstr /i "jellyfin\|python\|JellyfinAudioService" > "%TEMP%\jellyfin_crashes.txt" 2>nul

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

REM Check for crash dumps
echo Checking for crash dumps...
if exist "%LOCALAPPDATA%\CrashDumps\JellyfinAudioService*.dmp" (
    echo [FOUND] Crash dumps:
    dir "%LOCALAPPDATA%\CrashDumps\JellyfinAudioService*.dmp" /b
) else (
    echo [OK] No crash dumps found
)
echo.

REM Check for log files
echo Checking for log files...
if exist "%SERVICE_DIR%\service_crash.log" (
    echo [FOUND] service_crash.log exists
    echo Last 20 lines:
    powershell -Command "Get-Content '%SERVICE_DIR%\service_crash.log' -Tail 20"
    echo.
) else (
    echo [INFO] service_crash.log not found (executable may not have run yet)
)
echo.

if exist "%SERVICE_DIR%\service_error.log" (
    echo [FOUND] service_error.log exists
    echo Last 10 lines:
    powershell -Command "Get-Content '%SERVICE_DIR%\service_error.log' -Tail 10"
    echo.
)

if exist "%SERVICE_DIR%\service_startup.log" (
    echo [FOUND] service_startup.log exists
    echo Last 10 lines:
    powershell -Command "Get-Content '%SERVICE_DIR%\service_startup.log' -Tail 10"
    echo.
)

if exist "%SERVICE_DIR%\service_fatal_error.txt" (
    echo [FOUND] service_fatal_error.txt exists
    echo Contents:
    type "%SERVICE_DIR%\service_fatal_error.txt"
    echo.
)

REM Try to run executable with error capture
echo ========================================
echo Attempting to run executable...
echo ========================================
echo.

set "OUTPUT_FILE=%SERVICE_DIR%\test_run_output.txt"
set "ERROR_FILE=%SERVICE_DIR%\test_run_error.txt"

echo Running: "%SERVICE_DIR%\JellyfinAudioService.exe" --help
echo Output will be captured to: %OUTPUT_FILE%
echo Errors will be captured to: %ERROR_FILE%
echo.

"%SERVICE_DIR%\JellyfinAudioService.exe" --help > "%OUTPUT_FILE%" 2> "%ERROR_FILE%"
set EXIT_CODE=%errorlevel%

echo Exit code: %EXIT_CODE%
echo.

if exist "%OUTPUT_FILE%" (
    set "OUTPUT_SIZE=0"
    for %%A in ("%OUTPUT_FILE%") do set "OUTPUT_SIZE=%%~zA"
    if !OUTPUT_SIZE! GTR 0 (
        echo Output:
        type "%OUTPUT_FILE%"
        echo.
    )
)

if exist "%ERROR_FILE%" (
    set "ERROR_SIZE=0"
    for %%A in ("%ERROR_FILE%") do set "ERROR_SIZE=%%~zA"
    if !ERROR_SIZE! GTR 0 (
        echo Errors:
        type "%ERROR_FILE%"
        echo.
    )
)

echo ========================================
echo Diagnostic complete
echo ========================================
echo.
echo Log files checked:
echo   - service_crash.log
echo   - service_error.log
echo   - service_startup.log
echo   - service_fatal_error.txt
echo   - test_run_output.txt
echo   - test_run_error.txt
echo.
pause









