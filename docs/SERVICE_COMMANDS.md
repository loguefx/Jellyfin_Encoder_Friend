# Jellyfin Audio Service - Commands

## ✅ WORKING SOLUTION: Use Python Script

Since the executable crashes, use the Python script directly:

### Install Service
```powershell
cd "C:\Program Files (x86)\JellyfinAudioService"
python .\service.py install
```

### Start Service
```powershell
python .\service.py start
```

### Stop Service
```powershell
python .\service.py stop
```

### Remove Service
```powershell
python .\service.py remove
```

### Check Service Status
```powershell
Get-Service JellyfinAudioService
```

## Alternative: Use Windows Services Manager

1. Press `Win+R`, type `services.msc`
2. Find "JellyfinAudioService"
3. Right-click → Start/Stop

## Web Interface

After starting the service, access the web interface at:
- http://localhost:8080

## Why the Executable Doesn't Work

The executable (`JellyfinAudioService.exe`) is only 17KB, which means it's missing:
- Python runtime dependencies
- Required DLLs
- All bundled modules

The Python script works because Python 3.12.10 is installed on your system.

## Permanent Solution

For future installations, we can:
1. Fix the executable build to include all dependencies (larger file size)
2. Or document Python as the primary installation method

For now, **always use `python .\service.py` instead of the `.exe` file**.









