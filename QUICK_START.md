# Quick Start Guide - Jellyfin Audio Service

## PowerShell Commands (Use `.\` prefix!)

PowerShell requires `.\` prefix to run scripts from current directory.

### Install the Service

```powershell
# Option 1: Direct Python (simplest)
python service.py install

# Option 2: Using batch file wrapper
.\run_service_python.bat install
```

### Start the Service

```powershell
# Option 1: Direct Python
python service.py start

# Option 2: Using batch file wrapper
.\run_service_python.bat start
```

### Stop the Service

```powershell
python service.py stop
```

### Remove the Service

```powershell
python service.py remove
```

## Important Notes

- **Always use `.\` prefix** in PowerShell: `.\run_service_python.bat` not `run_service_python.bat`
- **Run PowerShell as Administrator** for install/start/stop commands
- The batch files keep the window open so you can see any errors
- Direct Python (`python service.py`) is usually easier to debug

## After MSI Installation

If you installed via MSI, navigate to the service directory first:

```powershell
cd "C:\Program Files\JellyfinAudioService"
python service.py install
python service.py start
```









