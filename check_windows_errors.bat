@echo off
echo ========================================
echo Checking Windows Event Viewer for Errors
echo ========================================
echo.

REM Check Application Event Log for Jellyfin errors
echo Checking Application Event Log...
echo.

wevtutil qe Application /c:10 /f:text /q:"*[System[Provider[@Name='Application Error'] or Provider[@Name='Windows Error Reporting']]]" | findstr /i "jellyfin\|python\|JellyfinAudioService" > "%TEMP%\jellyfin_events.txt" 2>nul

if exist "%TEMP%\jellyfin_events.txt" (
    echo Found events:
    type "%TEMP%\jellyfin_events.txt"
) else (
    echo No recent Jellyfin-related errors found in Event Viewer.
)

echo.
echo ========================================
echo Checking for crash dumps
echo ========================================
echo.

if exist "%LOCALAPPDATA%\CrashDumps\JellyfinAudioService*.dmp" (
    echo Found crash dumps:
    dir "%LOCALAPPDATA%\CrashDumps\JellyfinAudioService*.dmp" /b
) else (
    echo No crash dumps found.
)

echo.
pause









