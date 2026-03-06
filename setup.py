"""
Setup script for creating MSI installer using cx_Freeze.
Run: python setup.py bdist_msi
"""

import sys
import os
from cx_Freeze import setup, Executable
from pathlib import Path

# Determine if we should include config.json (if it exists)
include_files = []
# Include templates directory and all its contents
templates_dir = Path("templates")
if templates_dir.exists():
    for template_file in templates_dir.rglob("*"):
        if template_file.is_file():
            rel_path = template_file.relative_to(Path("."))
            include_files.append((str(template_file), str(rel_path)))
# Include static directory and all its contents
static_dir = Path("static")
if static_dir.exists():
    for static_file in static_dir.rglob("*"):
        if static_file.is_file():
            rel_path = static_file.relative_to(Path("."))
            include_files.append((str(static_file), str(rel_path)))
if Path("config.json").exists():
    include_files.append(("config.json", "config.json"))
# Include cache file if it exists (for tracking processed files)
if Path("file_cache.json").exists():
    include_files.append(("file_cache.json", "file_cache.json"))
if Path("install_service_helper.bat").exists():
    include_files.append(("install_service_helper.bat", "install_service_helper.bat"))
if Path("InstallServiceCA.bat").exists():
    include_files.append(("InstallServiceCA.bat", "InstallServiceCA.bat"))
if Path("UninstallServiceCA.bat").exists():
    include_files.append(("UninstallServiceCA.bat", "UninstallServiceCA.bat"))
if Path("post_install.bat").exists():
    include_files.append(("post_install.bat", "post_install.bat"))
if Path("diagnose_service.bat").exists():
    include_files.append(("diagnose_service.bat", "diagnose_service.bat"))
if Path("test_service_exe.bat").exists():
    include_files.append(("test_service_exe.bat", "test_service_exe.bat"))
if Path("run_service_terminal.bat").exists():
    include_files.append(("run_service_terminal.bat", "run_service_terminal.bat"))
if Path("run_service_python.bat").exists():
    include_files.append(("run_service_python.bat", "run_service_python.bat"))
# Include Python source files for alternative Python mode
if Path("service.py").exists():
    include_files.append(("service.py", "service.py"))
if Path("app.py").exists():
    include_files.append(("app.py", "app.py"))
if Path("config.py").exists():
    include_files.append(("config.py", "config.py"))
if Path("scanner.py").exists():
    include_files.append(("scanner.py", "scanner.py"))
if Path("transcoder.py").exists():
    include_files.append(("transcoder.py", "transcoder.py"))
if Path("cache.py").exists():
    include_files.append(("cache.py", "cache.py"))
if Path("backup.py").exists():
    include_files.append(("backup.py", "backup.py"))
if Path("find_crash.bat").exists():
    include_files.append(("find_crash.bat", "find_crash.bat"))
if Path("find_port_8080.bat").exists():
    include_files.append(("find_port_8080.bat", "find_port_8080.bat"))
if Path("test_with_python.bat").exists():
    include_files.append(("test_with_python.bat", "test_with_python.bat"))

# Build options
build_exe_options = {
    "packages": [
        "os",
        "sys",
        "json",
        "logging",
        "threading",
        "datetime",
        "pathlib",
        "subprocess",
        "time",
        "traceback",
        "tempfile",  # Used by transcoder.py
        "shutil",  # Used by transcoder.py and backup.py
        "typing",  # Used throughout the codebase
        "flask",
        "http",  # Required by Flask/Werkzeug
        "html",  # Required by http.server
        "win32serviceutil",
        "win32service",
        "win32event",
        "servicemanager",
        "win32gui",
        "win32con",
        "win32cred",  # Used for UNC path authentication
        "schedule",  # Used for scheduled scans
        "encodings",
    ],
    "includes": [
        "config",
        "scanner",
        "transcoder",
        "cache",
        "backup",
        "unc_auth",
        "service",  # Explicitly include service module for service_console.py
    ],
    "include_files": include_files,
    "excludes": [
        "tkinter",
        "matplotlib",
        "numpy",
        "pandas",
        "PIL",
        "unittest",
        "email",
        # "html",  # REMOVED: http.server requires html module
        # "http",  # REMOVED: Flask/Werkzeug requires http.server
        # "urllib",  # REMOVED: pathlib depends on urllib in Python 3.12
        "xml",
        "pydoc",
    ],
    "optimize": 2,
}

# Executables
# Note: Using base=None (console) for service executable so install/start/stop commands show output
# The service will still work correctly when installed as a Windows Service
executables = [
    Executable(
        "service_console.py",  # Use console wrapper that ensures visibility
        base=None,  # Console mode - ALWAYS show console window
        target_name="JellyfinAudioService.exe",
        icon=None,
    ),
    Executable(
        "app.py",
        base="Console",  # Show console window for UI
        target_name="JellyfinAudioServiceUI.exe",
        icon=None,
    ),
    Executable(
        "test_minimal.py",
        base=None,
        target_name="TestMinimal.exe",
        icon=None,
    ),
]

# Custom actions: run batch files so install/uninstall never fail the MSI (exit 0 always).
# Type 3106 = 34 (exe in directory) + 3072 (deferred, elevated). Must run between InstallInitialize and InstallFinalize (else error 2762).
# RemoveOldService: during install/upgrade, stop and remove existing service first (TARGETDIR still has old exe at 1520).
_msi_custom_actions = [
    ("RemoveOldService", 3106, "TARGETDIR", 'cmd.exe /c UninstallServiceCA.bat'),
    ("InstallJellyfinService", 3106, "TARGETDIR", 'cmd.exe /c InstallServiceCA.bat'),
    ("UninstallJellyfinService", 3106, "TARGETDIR", 'cmd.exe /c UninstallServiceCA.bat'),
]
_msi_install_sequence = [
    ("RemoveOldService", "NOT REMOVE", 1520),            # Before InstallFiles: remove existing service so upgrade is clean
    ("InstallJellyfinService", "NOT REMOVE", 6500),      # After InstallFiles, before InstallFinalize (6600)
    ("UninstallJellyfinService", 'REMOVE~="ALL"', 1550), # After InstallInitialize (1500), before RemoveFiles
]
msi_data = {
    "CustomAction": _msi_custom_actions,
    "InstallExecuteSequence": _msi_install_sequence,
}

# MSI options - Install to 64-bit Program Files (not x86)
msi_options = {
    "add_to_path": False,
    "initial_target_dir": r"[ProgramFiles64Folder]JellyfinAudioService",  # Use 64-bit folder
    "upgrade_code": "{A1B2C3D4-E5F6-4A5B-8C9D-0E1F2A3B4C5D}",
    "all_users": True,  # Install for all users (requires Program Files)
    "data": msi_data,
}

setup(
    name="JellyfinAudioService",
    version="1.0.0",
    description="Windows Service for Jellyfin Audio Conversion",
    author="Jellyfin Audio Service",
    options={
        "build_exe": build_exe_options,
        "bdist_msi": msi_options,
    },
    executables=executables,
)

