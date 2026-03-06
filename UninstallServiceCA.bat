@echo off
REM MSI custom action: stop and remove Windows service. Always exit 0 so uninstall completes.
cd /d "%~dp0"
"%~dp0JellyfinAudioService.exe" stop
"%~dp0JellyfinAudioService.exe" remove
exit /b 0
