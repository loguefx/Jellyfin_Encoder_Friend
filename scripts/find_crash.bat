@echo off
REM Find the actual crash for JellyfinAudioService.exe
setlocal enabledelayedexpansion

echo ========================================
echo Finding JellyfinAudioService Crash
echo ========================================
echo.

set "SERVICE_DIR=C:\Program Files (x86)\JellyfinAudioService"

echo Checking: %SERVICE_DIR%
echo.

REM Check Application Error events specifically for our executable
echo Checking Application Error events for JellyfinAudioService...
echo.

wevtutil qe Application /c:20 /f:text /q:"*[System[EventID=1000] and EventData[Data[@Name='ApplicationName']='JellyfinAudioService.exe']]" > "%TEMP%\jellyfin_app_errors.txt" 2>nul

if exist "%TEMP%\jellyfin_app_errors.txt" (
    for %%A in ("%TEMP%\jellyfin_app_errors.txt") do set "ERROR_SIZE=%%~zA"
    if !ERROR_SIZE! GTR 0 (
        echo [FOUND] Application Error events:
        echo ========================================
        type "%TEMP%\jellyfin_app_errors.txt"
        echo ========================================
        echo.
    ) else (
        echo [INFO] No Application Error events found for JellyfinAudioService.exe
        echo.
    )
) else (
    echo [INFO] No Application Error events found
    echo.
)

REM Check Windows Error Reporting events
echo Checking Windows Error Reporting events...
echo.

wevtutil qe Application /c:20 /f:text /q:"*[System[Provider[@Name='Windows Error Reporting']] and EventData[Data[contains(., 'JellyfinAudioService')]]]" > "%TEMP%\jellyfin_wer.txt" 2>nul

if exist "%TEMP%\jellyfin_wer.txt" (
    for %%A in ("%TEMP%\jellyfin_wer.txt") do set "WER_SIZE=%%~zA"
    if !WER_SIZE! GTR 0 (
        echo [FOUND] Windows Error Reporting events:
        echo ========================================
        type "%TEMP%\jellyfin_wer.txt"
        echo ========================================
        echo.
    )
)

REM Check for crash dumps
echo Checking for crash dumps...
if exist "%LOCALAPPDATA%\CrashDumps\JellyfinAudioService*.dmp" (
    echo [FOUND] Crash dumps:
    dir "%LOCALAPPDATA%\CrashDumps\JellyfinAudioService*.dmp" /b
    echo.
) else (
    echo [INFO] No crash dumps found
    echo.
)

REM Check if executable exists and try to get more info
if exist "%SERVICE_DIR%\JellyfinAudioService.exe" (
    echo Executable found: %SERVICE_DIR%\JellyfinAudioService.exe
    echo.
    
    REM Check file properties
    echo File properties:
    for %%A in ("%SERVICE_DIR%\JellyfinAudioService.exe") do (
        echo   Size: %%~zA bytes
        echo   Modified: %%~tA
    )
    echo.
    
    REM Check for DLLs in same directory
    echo Checking for DLLs in service directory:
    if exist "%SERVICE_DIR%\*.dll" (
        echo [FOUND] DLLs:
        dir /b "%SERVICE_DIR%\*.dll"
    ) else (
        echo [WARNING] No DLLs found in service directory
        echo This may cause crashes if DLLs are not in PATH
    )
    echo.
    
    REM Try Dependency Walker info (if available)
    echo Checking dependencies...
    echo Run this command to see DLL dependencies:
    echo   dumpbin /dependents "%SERVICE_DIR%\JellyfinAudioService.exe"
    echo.
    
) else (
    echo [ERROR] Executable not found: %SERVICE_DIR%\JellyfinAudioService.exe
    echo.
)

REM Check if Python is available (for fallback)
echo Checking Python availability...
python --version >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Python is available
    python --version
    echo.
    echo You can try running the Python script directly:
    echo   python "%SERVICE_DIR%\service.py" install
    echo.
) else (
    echo [WARNING] Python is not in PATH
    echo The executable must work standalone
    echo.
)

REM Check Visual C++ Runtime
echo Checking Visual C++ Runtime...
reg query "HKLM\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64" >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Visual C++ 2015-2022 Runtime detected
) else (
    echo [ERROR] Visual C++ Runtime NOT FOUND
    echo Download and install: https://aka.ms/vs/17/release/vc_redist.x64.exe
    echo This is likely the cause of the crash!
)
echo.

echo ========================================
echo Diagnostic Complete
echo ========================================
echo.
echo If no Application Error events were found, the crash may be happening
echo before Windows can log it (missing DLLs or runtime).
echo.
echo Most likely causes:
echo 1. Missing Visual C++ Runtime (check above)
echo 2. Missing Python DLLs (check DLL list above)
echo 3. Missing other dependencies
echo.
pause









