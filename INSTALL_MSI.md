# MSI Installer Installation Guide

This guide explains how to create and use the MSI installer for the Jellyfin Audio Service.

## Getting the MSI

- **From GitHub Releases:** Go to your repository’s **Releases** page. Create a new release with a tag (e.g. `v1.0.0`) and publish. The GitHub Action runs, builds the MSI, and attaches it to that release. Download the `.msi` from the release assets. (You can also push a tag from the command line: `git tag v1.0.0 && git push origin v1.0.0`; the Action will create the release and attach the MSI.)
- **Build locally:** Run `build_msi.bat` or `python setup.py bdist_msi`. The MSI is created in the `dist` directory.

## Installing on Target Server

1. **Run the MSI installer** (requires Administrator rights):
   - Right-click the MSI file and select "Install"
   - Or run: `msiexec /i JellyfinAudioService-1.0.0-win64.msi`
   - Follow the installation wizard

2. **Windows service is installed automatically** by the MSI. You do **not** need to run any PowerShell or Command Prompt commands to register the service.

3. **Start the Service** (if it is not set to auto-start):
   - Open Windows Services (services.msc), find "Jellyfin Audio Conversion Service", then Right-click → Start
   - Or from an elevated command prompt: `"C:\Program Files\JellyfinAudioService\JellyfinAudioService.exe" start`

4. **Configure the Service:**
   - Open the web interface at http://localhost:8080
   - Configure UNC paths, scan schedules, and other settings

## Creating the MSI Installer (for developers)

1. **Prerequisites:** Python 3.8+, dependencies (`pip install -r requirements.txt`), and cx_Freeze (`pip install cx_Freeze`).

2. **Build:** Run `build_msi.bat` or:
   ```batch
   pip install cx_Freeze
   python setup.py bdist_msi
   ```
   The MSI is created in the `dist` directory.

## Important Notes

- **FFmpeg Required:** FFmpeg must be installed separately on the target server
  - Download from https://ffmpeg.org/download.html
  - Add to system PATH, or configure the path in the web interface
  
- **Service Account:** The service runs under the Local System account by default
  - For UNC path access, ensure the service account has network permissions
  - You may need to configure the service to run under a specific domain account

- **Firewall:** The web interface uses port 8080 by default
  - Ensure Windows Firewall allows connections on this port
  - Or change the port in the configuration

- **Configuration File:** The `config.json` file is included in the installer
  - It will be created in the installation directory
  - You can edit it directly or use the web interface

## Uninstalling

**Uninstall from Windows:** Use "Add or Remove Programs" (Settings > Apps), find "JellyfinAudioService", and click Uninstall. The MSI automatically stops and removes the Windows service before removing files; you do not need to run any commands manually.

## Troubleshooting

- **Service won't start:** Check the service logs in the installation directory (`service.log`)
- **Web interface not accessible:** Verify the service is running and port 8080 is not blocked
- **UNC path access denied:** Configure the service to run under an account with network access
- **FFmpeg not found:** Ensure FFmpeg is in PATH or configure the path in the web interface




