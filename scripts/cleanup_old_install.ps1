<#
.SYNOPSIS
    Removes the old (broken) JellyfinAudioService MSI registration so that
    the new v1.0.11+ MSI installs without Error 2762.

.NOTES
    Run ONCE as Administrator before installing the new MSI.
    Right-click PowerShell -> "Run as administrator", then:
        Set-ExecutionPolicy Bypass -Scope Process -Force
        & "C:\path\to\cleanup_old_install.ps1"
#>

#Requires -RunAsAdministrator

$ErrorActionPreference = "SilentlyContinue"

Write-Host ""
Write-Host "JellyfinAudioService - Old Installation Cleanup"
Write-Host "================================================"
Write-Host ""

# Registry keys for the old product (squished GUID 74A5EF8A...)
$regKeys = @(
    "HKLM\SOFTWARE\Classes\Installer\Products\74A5EF8A3CC97184E868CA0E34D88A35",
    "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Installer\UserData\S-1-5-18\Products\74A5EF8A3CC97184E868CA0E34D88A35",
    "HKLM\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Installer\UserData\S-1-5-18\Products\74A5EF8A3CC97184E868CA0E34D88A35",
    "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{8AEFA574-C93C-8471-E868-CA0E34D88A35}",
    "HKLM\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\{8AEFA574-C93C-8471-E868-CA0E34D88A35}"
)

Write-Host "Removing old product registration from Windows Installer database..."
foreach ($key in $regKeys) {
    $psKey = $key -replace "^HKLM\\", "HKLM:\"
    if (Test-Path $psKey) {
        # reg.exe delete works on TrustedInstaller-owned keys when run as admin
        $result = reg delete $key /f 2>&1
        if (Test-Path $psKey) {
            Write-Warning "  Could not remove (may need reboot): $key"
        } else {
            Write-Host "  Removed: $key"
        }
    } else {
        Write-Host "  (not present): $key"
    }
}

# Stop and remove the Windows service if still registered
Write-Host ""
Write-Host "Checking for leftover Windows service..."
$svc = Get-Service -Name "JellyfinAudioService" -ErrorAction SilentlyContinue
if ($svc) {
    Write-Host "  Stopping service..."
    Stop-Service "JellyfinAudioService" -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    $scResult = sc.exe delete "JellyfinAudioService"
    Write-Host "  Service removed: $scResult"
} else {
    Write-Host "  (not registered, skip)"
}

# Offer to remove leftover install directory
$installDir = "C:\Program Files\JellyfinAudioService"
if (Test-Path $installDir) {
    Write-Host ""
    Write-Host "Found leftover install directory: $installDir"
    $choice = Read-Host "  Delete it? (y/N)"
    if ($choice -ieq 'y') {
        Remove-Item $installDir -Recurse -Force
        Write-Host "  Deleted."
    }
}

Write-Host ""
Write-Host "Done. You can now install JellyfinAudioService-1.0.11-win64.msi."
Write-Host ""
