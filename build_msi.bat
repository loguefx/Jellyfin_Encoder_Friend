@echo off
REM Change to the directory where this batch file is located
cd /d "%~dp0"
echo Building MSI Installer for Jellyfin Audio Service...
echo Current directory: %CD%
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not found in PATH!
    echo Please ensure Python is installed and accessible.
    pause
    exit /b 1
)

REM Check if cx_Freeze is installed
python -c "import cx_Freeze" >nul 2>&1
if errorlevel 1 (
    echo cx_Freeze not found. Installing...
    pip install cx_Freeze
    if errorlevel 1 (
        echo ERROR: Failed to install cx_Freeze!
        pause
        exit /b 1
    )
)

echo.
echo Cleaning previous builds...
REM Try to delete build directory
if exist build (
    rmdir /s /q build 2>nul
    if exist build (
        echo WARNING: Could not delete 'build' directory. It may be in use.
        echo Continuing anyway...
    )
)

REM Try to delete dist directory and handle locked files gracefully
if exist dist (
    REM Try to delete individual MSI files first (handles locked files better)
    REM The for loop will simply not execute if no MSI files exist - that's OK
    for %%f in (dist\*.msi) do (
        del /f /q "%%f" >nul 2>&1
        if exist "%%f" (
            echo WARNING: Could not delete %%f - file may be locked by another process.
            echo Please close any programs that might be using this file.
            echo Continuing anyway - the new build will overwrite it if possible...
        )
    )
    REM Try to delete other files in dist directory (errors are ignored)
    del /f /q dist\*.* >nul 2>&1
    REM Now try to remove the directory (will fail if files are locked, but that's OK)
    rmdir /s /q dist >nul 2>&1
    if exist dist (
        echo WARNING: Could not fully delete 'dist' directory. Some files may be locked.
        echo Continuing anyway - the build will attempt to overwrite existing files...
    )
)

echo.
echo Building MSI installer...
python setup.py bdist_msi

if errorlevel 1 (
    echo.
    echo ERROR: MSI build failed!
    echo.
    echo If you see file locking errors above, try:
    echo 1. Close Windows Explorer if it's viewing the dist folder
    echo 2. Close any MSI installer windows that might be open
    echo 3. Wait a few seconds and try again
    echo 4. If the file is still locked, restart your computer
    pause
    exit /b 1
)

echo.
echo ========================================
echo MSI installer created successfully!
echo ========================================
echo.
echo The installer is in the 'dist' directory.
echo.
echo When you run the MSI (as Administrator):
echo - The installer copies all files to Program Files\JellyfinAudioService.
echo - After the MSI completes, run "Register Jellyfin Service.bat" as Administrator
echo   to register and start the Windows service.
echo - On upgrade: uninstall the old version first (manual_uninstall_service.bat,
echo   then Apps and Features), then install the new MSI and re-register.
echo.
echo To register the service after install:
echo   Right-click "Register Jellyfin Service.bat" in the install folder, Run as administrator
echo.
echo Note: FFmpeg must be installed separately on the target server.
echo.
pause



