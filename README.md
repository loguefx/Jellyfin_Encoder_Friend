# Jellyfin Audio Conversion Service

A Windows service that monitors video libraries on UNC paths, scans for audio codec compliance, and automatically converts files to MP4 or MKV with AAC-LC audio while preserving original filenames and embedded subtitles.

## Features

- **UNC Path Support**: Handles Windows UNC paths (\\server\share)
- **Preserve Filenames**: Maintains original show/episode names after conversion
- **Backup Safety**: Creates backups before any conversion
- **Scheduled Scans**: Configurable scan intervals
- **Web Configuration**: Easy-to-use web interface
- **Error Handling**: Graceful handling of network issues, file locks, etc.
- **Logging**: Comprehensive logging for troubleshooting

## Requirements

- Python 3.8 or higher
- FFmpeg installed and available in PATH
- Windows OS (for service functionality)
- Network access to UNC paths

## Installation

### Option 1: MSI Installer (Recommended for Server Deployment)

1. Get the MSI:
   - **From GitHub Releases:** Create a release (e.g. tag `v1.0.0`); the GitHub Action builds the MSI and attaches it to the release. Download the `.msi` from the release page.
   - **Build locally:** Run `build_msi.bat`; the MSI is created in the `dist` directory.

2. Install on target server:
   - Run the MSI installer (requires Administrator rights).
   - After install, open the install folder (e.g. `C:\Program Files\JellyfinAudioService`), right-click **Register Jellyfin Service.bat** → **Run as administrator** to register the Windows service.
   - Start the service from Services (services.msc) or run `JellyfinAudioService.exe start` from the install folder if needed.

3. See [INSTALL_MSI.md](INSTALL_MSI.md) for detailed instructions. Before uninstalling, run **manual_uninstall_service.bat** as Administrator to remove the service, then uninstall via "Add or Remove Programs".

### Option 2: Manual Installation (Development)

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Ensure FFmpeg is installed and accessible:
   - Download from https://ffmpeg.org/download.html
   - Add to system PATH or place in project directory

3. Configure the service:
   - Install the service: `python service.py install`
   - Start the service: `python service.py start`
   - Access web interface at http://localhost:8080
   - Add your UNC paths through the web interface

## Usage

### Running as Service

Install the service:
```bash
python service.py install
```

Start the service:
```bash
python service.py start
```

Stop the service:
```bash
python service.py stop
```

Remove the service:
```bash
python service.py remove
```

### Running Standalone (for testing)

```bash
python app.py
```

Then access http://localhost:8080 in your browser.

### Running as hosted tool (no installer)

You can run the tool as a hosted web app to scan your UNC paths and fix any issues before building the installer:

1. From the project folder, run:
   ```bash
   python app.py
   ```
2. Open http://localhost:8080 (or http://&lt;this-machine-ip&gt;:8080 from another PC).
3. In the web UI, add your UNC path(s) (e.g. `\\server\share\path`) and optional credentials.
4. Use **Test Path** to verify access, then **Start Scan** to scan for non-compliant files.
5. Any scan or conversion errors appear in the UI and in the console, so you can fix them before creating the installer.

The app binds to `0.0.0.0` by default (see `web_host` in config), so it is reachable on your network. Ensure FFmpeg/FFprobe paths in **config.json** (or in the UI) are correct for the machine where the app runs.

## Configuration

Configuration is managed through the web interface at http://localhost:8080. You can:
- Add/remove UNC paths to monitor
- Set scan schedule (daily, hourly, etc.)
- Configure backup location
- View scan logs and history
- Manually trigger scans

## Audio Codec Requirements

The service checks for and converts to:
- **Container**: Smart format selection
  - MKV files with embedded subtitles → Output MKV (preserves all subtitle formats: ASS, VOBSUB, PGS, SRT, etc.)
  - MKV files without subtitles → Output MP4 (better device compatibility)
  - MP4 files → Output MP4 (maintains format)
- **Codec**: AAC-LC
- **Channels**: Stereo (2.0) or 5.1
- **Bitrate**: 160-320 kbps

## Backup Location

By default, backups are stored in a `backups/` subdirectory relative to each source file's location. This can be configured through the web interface.

## Troubleshooting

- **UNC Path Access**: Ensure the service account has network access to UNC paths
- **FFmpeg Errors**: Verify FFmpeg is installed and in PATH
- **Permission Errors**: Service may need elevated permissions for some operations
- **Logs**: Check service logs for detailed error information

### Service won't start after reboot (Error 1053)

If Windows reports *"The service did not respond to the start or control request in a timely fashion"* (Error 1053), the service was taking too long to start. Recent builds report "running" to Windows before loading heavy modules, which should prevent this. If you still see it:

1. Reinstall using the latest MSI (rebuild with `build_msi.bat` if needed).
2. Optionally increase the system service startup timeout: in Registry Editor go to `HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control`, create or set `ServicesPipeTimeout` (DWORD) to a value in milliseconds (e.g. `60000` for 60 seconds). Restart the computer after changing it.

### Uninstall fails (Error 2762 or MSI won't uninstall)

If the MSI uninstaller fails (e.g. error 2762) or the service is stuck:

1. **Remove the service manually:** Right-click **Command Prompt** or **PowerShell** → **Run as administrator**, then run from the project or install folder:
   ```bat
   manual_uninstall_service.bat
   ```
   Or run these commands directly:
   ```bat
   sc stop JellyfinAudioService
   sc delete JellyfinAudioService
   ```
2. Then uninstall the app via **Settings → Apps → JellyfinAudioService** (or run the MSI uninstaller again).




