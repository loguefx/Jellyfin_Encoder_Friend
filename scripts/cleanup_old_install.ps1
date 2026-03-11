<#
.SYNOPSIS
    Removes the old (broken) JellyfinAudioService MSI registration from the Windows
    Installer database so that the new v1.0.11+ MSI can install without Error 2762.

.NOTES
    Run once, as Administrator, BEFORE installing the new MSI.
    Usage:  Right-click PowerShell -> Run as administrator, then:
            Set-ExecutionPolicy Bypass -Scope Process -Force
            & "C:\path\to\cleanup_old_install.ps1"
#>

#Requires -RunAsAdministrator

function Remove-RegistryKeyAsAdmin {
    param([string]$KeyPath)
    if (-not (Test-Path $KeyPath)) {
        Write-Host "  (not found, skip) $KeyPath"
        return
    }

    # Take ownership and grant Administrators full control
    $acl = Get-Acl $KeyPath -ErrorAction SilentlyContinue
    if ($acl) {
        $rule = New-Object System.Security.AccessControl.RegistryAccessRule(
            "Administrators",
            "FullControl",
            "ContainerInherit,ObjectInherit",
            "None",
            "Allow"
        )
        $identity = New-Object System.Security.Principal.NTAccount("Administrators")
        $acl.SetOwner($identity)
        $acl.AddAccessRule($rule)
        try { Set-Acl -Path $KeyPath -AclObject $acl } catch {}
    }

    # Recurse into children first
    Get-ChildItem $KeyPath -ErrorAction SilentlyContinue | ForEach-Object {
        Remove-RegistryKeyAsAdmin -KeyPath $_.PSPath
    }

    Remove-Item $KeyPath -Force -ErrorAction SilentlyContinue
    if (Test-Path $KeyPath) {
        # Fallback: use reg.exe
        $regPath = $KeyPath -replace "^HKLM:\\","HKLM\\" -replace "^Microsoft.PowerShell.Core\\Registry::HKEY_LOCAL_MACHINE\\","HKLM\\"
        reg delete $regPath /f 2>&1 | Out-Null
    }

    if (Test-Path $KeyPath) {
        Write-Warning "  Could not remove: $KeyPath"
    } else {
        Write-Host "  Removed: $KeyPath"
    }
}

Write-Host ""
Write-Host "JellyfinAudioService - Old Installation Cleanup"
Write-Host "================================================"
Write-Host ""

# Old product squished GUIDs (all versions prior to 1.0.11)
$oldSquids = @(
    "74A5EF8A3CC97184E868CA0E34D88A35"   # v1.0.0 - v1.0.10 (upgrade_code A1B2C3D4...)
)
$oldGuids = @(
    "{8AEFA574-C93C-8471-E868-CA0E34D88A35}"
)

foreach ($squid in $oldSquids) {
    Write-Host "Removing old product registration: $squid"
    Remove-RegistryKeyAsAdmin "HKLM:\SOFTWARE\Classes\Installer\Products\$squid"
    Remove-RegistryKeyAsAdmin "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Installer\UserData\S-1-5-18\Products\$squid"
    Remove-RegistryKeyAsAdmin "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Installer\UserData\S-1-5-18\Products\$squid"
}

foreach ($guid in $oldGuids) {
    Remove-RegistryKeyAsAdmin "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\$guid"
    Remove-RegistryKeyAsAdmin "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\$guid"
}

# Stop and remove the service if it is still registered
Write-Host ""
Write-Host "Checking for leftover Windows service..."
$svc = Get-Service -Name "JellyfinAudioService" -ErrorAction SilentlyContinue
if ($svc) {
    Write-Host "  Stopping service..."
    Stop-Service "JellyfinAudioService" -Force -ErrorAction SilentlyContinue
    sc.exe delete "JellyfinAudioService" | Out-Null
    Write-Host "  Service removed."
} else {
    Write-Host "  (service not registered, skip)"
}

# Remove leftover install directory if empty or partially installed
$installDir = "C:\Program Files\JellyfinAudioService"
if (Test-Path $installDir) {
    Write-Host ""
    Write-Host "Found leftover install directory: $installDir"
    $choice = Read-Host "  Delete it? (y/N)"
    if ($choice -eq 'y' -or $choice -eq 'Y') {
        Remove-Item $installDir -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "  Deleted."
    }
}

Write-Host ""
Write-Host "Cleanup complete."
Write-Host "You can now install the new JellyfinAudioService MSI."
Write-Host ""
