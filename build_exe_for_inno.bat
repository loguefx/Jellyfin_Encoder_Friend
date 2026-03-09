@echo off
REM Build the application and prepare folder for Inno Setup. Use this if MSI fails with Error 2762.
cd /d "%~dp0"

echo Building Jellyfin Audio Service (exe only)...
python setup.py build_exe
if errorlevel 1 (
    echo Build failed.
    pause
    exit /b 1
)

REM Find the exe output folder (e.g. build\exe.win-amd64-3.11)
set "EXEDIR="
for /d %%d in (build\exe.win-amd64-*) do set "EXEDIR=%%d"
if not defined EXEDIR (
    for /d %%d in (build\exe.win32-*) do set "EXEDIR=%%d"
)
if not defined EXEDIR (
    echo ERROR: Could not find build\exe.win-amd64-* or build\exe.win32-*
    pause
    exit /b 1
)

echo Copying to dist\installer_files...
if exist dist\installer_files rmdir /s /q dist\installer_files
xcopy /E /I /Y "%EXEDIR%" dist\installer_files

echo.
echo Done. Next steps:
echo 1. Install Inno Setup 6 from https://jrsoftware.org/isdl.php
echo 2. Open JellyfinAudioService.iss in Inno Setup Compiler
echo 3. Build ^> Compile (or press Ctrl+F9)
echo 4. Run dist\JellyfinAudioService-setup.exe to install (no MSI, no Error 2762)
echo 5. After install, right-click "Register Jellyfin Service.bat" ^> Run as administrator
echo.
pause
