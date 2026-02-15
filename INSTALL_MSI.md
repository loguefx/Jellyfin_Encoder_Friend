# MSI Installer Installation Guide

This guide explains how to create and use the MSI installer for the Jellyfin Audio Service.

## Creating the MSI Installer

1. **Prerequisites:**
   - Python 3.8 or higher installed
   - All project dependencies installed (`pip install -r requirements.txt`)
   - cx_Freeze installed (`pip install cx_Freeze`)

2. **Build the MSI:**
   - Run `build_msi.bat` (double-click it or run from command prompt)
   - The script will automatically install cx_Freeze if needed
   - The MSI file will be created in the `dist` directory

3. **Alternative method (manual):**
   ```batch
   pip install cx_Freeze
   python setup.py bdist_msi
   ```

## Installing on Target Server

1. **Copy the MSI file** to your target server

2. **Run the MSI installer** (requires Administrator rights):
   - Right-click the MSI file and select "Install"
   - Or run from command prompt: `msiexec /i JellyfinAudioService-1.0.0-win64.msi`
   - Follow the installation wizard

3. **Install the Windows Service:**
   - After MSI installation, **you MUST run PowerShell or Command Prompt as Administrator**
   - **Right-click** on PowerShell or Command Prompt and select **"Run as Administrator"**
   - Navigate to the installation directory (typically `C:\Program Files\JellyfinAudioService\`)
   - Run: `.\JellyfinAudioService.exe install`
   - **Note:** If you see "Access is denied" error, you did not run as Administrator

4. **Start the Service:**
   - Run: `JellyfinAudioService.exe start`
   - Or use Windows Services Manager (services.msc):
     - Find "Jellyfin Audio Conversion Service"
     - Right-click and select "Start"

5. **Configure the Service:**
   - Access the web interface at http://localhost:8080
   - Configure UNC paths, scan schedules, and other settings

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

1. **Stop and Remove the Service:**
   - Open Command Prompt as Administrator
   - Run: `JellyfinAudioService.exe stop`
   - Run: `JellyfinAudioService.exe remove`

2. **Uninstall the Application:**
   - Use Windows "Add or Remove Programs" (Settings > Apps)
   - Find "JellyfinAudioService" and click Uninstall
   - Or run: `msiexec /x JellyfinAudioService-1.0.0-win64.msi`

## Troubleshooting

- **Service won't start:** Check the service logs in the installation directory (`service.log`)
- **Web interface not accessible:** Verify the service is running and port 8080 is not blocked
- **UNC path access denied:** Configure the service to run under an account with network access
- **FFmpeg not found:** Ensure FFmpeg is in PATH or configure the path in the web interface




