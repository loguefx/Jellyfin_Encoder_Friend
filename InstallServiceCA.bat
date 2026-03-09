@echo off
REM MSI custom action: stop/remove any existing service, then install. Always exit 0 so installer does not roll back.
cd /d "%~dp0"
"%~dp0JellyfinAudioService.exe" stop
"%~dp0JellyfinAudioService.exe" remove
"%~dp0JellyfinAudioService.exe" install
exit /b 0
