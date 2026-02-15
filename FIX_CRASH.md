# Fix Crash - PowerShell Commands

## Step 1: Navigate to Service Directory

```powershell
cd "C:\Program Files (x86)\JellyfinAudioService"
```

## Step 2: Run Diagnostic (Use `.\` prefix!)

```powershell
.\find_crash.bat
```

**OR** if the batch file doesn't exist, run these PowerShell commands directly:

```powershell
# Check for Application Error events
Get-WinEvent -FilterHashtable @{LogName='Application'; ID=1000} -MaxEvents 20 | Where-Object {$_.Message -like '*JellyfinAudioService*'} | Format-List

# Check if executable exists
Test-Path ".\JellyfinAudioService.exe"

# Check for DLLs
Get-ChildItem ".\*.dll" | Select-Object Name

# Check Visual C++ Runtime
Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64" -ErrorAction SilentlyContinue

# Try Python fallback
python --version
if ($?) {
    python .\service.py install
}
```

## Step 3: Try Python Fallback

If Python is installed, use this instead of the executable:

```powershell
cd "C:\Program Files (x86)\JellyfinAudioService"
python .\service.py install
python .\service.py start
```

## Step 4: Check Event Viewer Manually

1. Press `Win+R`, type `eventvwr.msc`
2. Go to **Windows Logs** → **Application**
3. Filter for **Event ID 1000** (Application Error)
4. Look for entries with "JellyfinAudioService.exe"
5. Check the "Faulting module" - this shows which DLL is missing

## Most Common Fix

Install Visual C++ Runtime:
- Download: https://aka.ms/vs/17/release/vc_redist.x64.exe
- Install it
- Try running the executable again









