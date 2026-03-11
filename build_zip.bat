@echo off
REM Build app and create a zip for installation. No MSI, no Inno required.
REM User extracts the zip and runs "Register Jellyfin Service.bat" as Administrator.
cd /d "%~dp0"

for /f "delims=" %%v in ('python -c "import re; m=re.search(r'version=\"([^\"]+)\"', open('setup.py', encoding='utf-8').read()); print(m.group(1) if m else '1.0.0')"') do set VERSION=%%v
echo Version: %VERSION%

echo Building executable...
python setup.py build_exe
if errorlevel 1 (echo Build failed. & pause & exit /b 1)

set "EXEDIR="
for /d %%d in (build\exe.win-amd64-*) do set "EXEDIR=%%d"
if not defined EXEDIR for /d %%d in (build\exe.win32-*) do set "EXEDIR=%%d"
if not defined EXEDIR (
    echo ERROR: No build\exe.win-amd64-* or exe.win32-* found.
    pause
    exit /b 1
)

if not exist dist mkdir dist
set "ZIPNAME=JellyfinAudioService-%VERSION%-win64.zip"
echo Creating %ZIPNAME%...
powershell -NoProfile -Command "Compress-Archive -Path '%EXEDIR%\*' -DestinationPath 'dist\%ZIPNAME%' -Force"

echo.
echo Done. Install: extract %ZIPNAME% to e.g. C:\Program Files\JellyfinAudioService, then right-click Register Jellyfin Service.bat - Run as administrator.
echo.
pause
