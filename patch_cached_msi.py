"""
Patches the old cached Windows Installer MSI to remove the deferred custom actions
that cause Error 2762 when the new MSI tries to upgrade/remove the old one.

Run as Administrator:  python patch_cached_msi.py
"""

import shutil, sys, os

CACHED_MSI = r"C:\WINDOWS\Installer\41281bcc.msi"
TEMP_MSI   = r"C:\Temp\patch_cached.msi"

ACTIONS_TO_REMOVE = ["InstallJellyfinService", "UninstallJellyfinService", "RemoveOldService"]

def patch(src, dst):
    shutil.copy2(src, dst)
    import win32com.client
    installer = win32com.client.Dispatch("WindowsInstaller.Installer")
    db = installer.OpenDatabase(dst, 1)   # 1 = msiOpenDatabaseModeTransact
    for action in ACTIONS_TO_REMOVE:
        for table in ("CustomAction", "InstallExecuteSequence"):
            sql = "DELETE FROM " + table + " WHERE Action='" + action + "'"
            try:
                v = db.OpenView(sql)
                v.Execute()
                print("  Removed from " + table + ": " + action)
            except Exception:
                pass
    db.Commit()
    print("Patched OK: " + dst)

def replace_cached(patched, original):
    import ctypes
    if ctypes.windll.shell32.IsUserAnAdmin() == 0:
        print("ERROR: must run as Administrator to write to C:\\Windows\\Installer\\")
        sys.exit(1)
    shutil.copy2(patched, original)
    print("Replaced cached MSI: " + original)

if __name__ == "__main__":
    os.makedirs("C:\\Temp", exist_ok=True)
    print("Patching cached MSI...")
    patch(CACHED_MSI, TEMP_MSI)
    replace_cached(TEMP_MSI, CACHED_MSI)
    print("\nDone. You can now run the new MSI installer.")
    print("The old product will be removed cleanly before the new one installs.")
