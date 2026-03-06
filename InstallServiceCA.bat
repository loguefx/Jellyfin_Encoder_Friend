@echo off
REM MSI custom action: install Windows service. Always exit 0 so installer does not roll back.
cd /d "%~dp0"
"%~dp0JellyfinAudioService.exe" install
exit /b 0
