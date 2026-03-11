# Installation

## Recommended: Zip install (no MSI, no extra tools)

1. **Get the zip**
   - From [Releases](https://github.com/loguefx/Jellyfin_Encoder_Friend/releases): download **JellyfinAudioService-*.*.*-win64.zip**.
   - Or build it: run **`build_zip.bat`** in the project folder; the zip is created in `dist\`.

2. **Install**
   - Extract the zip to the folder where you want the app (e.g. `C:\Program Files\JellyfinAudioService`).
   - Right-click **Register Jellyfin Service.bat** → **Run as administrator** to register the Windows service.
   - Start the service from **Services** (services.msc) or run `JellyfinAudioService.exe start` from the install folder.

3. **Configure**
   - Open http://localhost:8080 and add your UNC paths and settings.

4. **Uninstall**
   - Run **manual_uninstall_service.bat** as Administrator from the install folder (removes the service).
   - Delete the install folder (and optionally remove from **Settings → Apps** if it appears there).

---

FFmpeg must be installed separately and available in PATH (or set in the web UI).
