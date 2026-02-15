"""
Backup management for Jellyfin Audio Service.
Creates organized backups before file conversion, preserving directory structure.
"""

import os
import shutil
import logging
from pathlib import Path
from typing import Optional

import config

try:
    import unc_auth
    UNC_AUTH_AVAILABLE = True
except ImportError:
    UNC_AUTH_AVAILABLE = False

logger = logging.getLogger(__name__)


def get_backup_path(source_file: Path, backup_base: Optional[str] = None) -> Path:
    """
    Generate backup path for a source file.
    Preserves directory structure relative to the UNC path root.
    """
    if backup_base is None:
        backup_base = config.get_backup_location()
    
    source_str = str(source_file)
    
    # Find which UNC path this file belongs to
    unc_paths = config.get_unc_paths()
    relative_path = None
    
    for unc_path in unc_paths:
        unc_path_normalized = os.path.normpath(unc_path)
        source_normalized = os.path.normpath(source_str)
        
        if source_normalized.startswith(unc_path_normalized):
            # Get relative path from UNC root
            try:
                relative_path = os.path.relpath(source_normalized, unc_path_normalized)
                break
            except ValueError:
                # Paths on different drives
                continue
    
    if relative_path is None:
        # Fallback: use filename only
        relative_path = source_file.name
    
    # Create backup path: backup_base/relative_path
    backup_file = Path(backup_base) / relative_path
    
    # Validate backup_base exists or can be created
    backup_base_path = Path(backup_base)
    if not backup_base_path.exists():
        try:
            backup_base_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created backup base directory: {backup_base_path}")
        except (PermissionError, OSError) as e:
            logger.warning(f"Cannot create backup base directory {backup_base}: {e}")
    
    return backup_file


def create_backup(source_file: Path, backup_base: Optional[str] = None) -> Optional[Path]:
    """
    Create a backup of the source file.
    Returns the backup file path if successful, None otherwise.
    """
    # #region agent log
    import json
    import time as time_module
    DEBUG_LOG_PATH = Path(__file__).parent / ".cursor" / "debug.log"
    log_entry = {
        "sessionId": "debug-session",
        "runId": "backup-debug",
        "hypothesisId": "H1",
        "location": "backup.py:create_backup",
        "message": "create_backup entry",
        "data": {
            "source_file": str(source_file),
            "source_exists": source_file.exists() if source_file else False,
            "backup_base": backup_base
        },
        "timestamp": int(time_module.time() * 1000)
    }
    try:
        DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
    except: pass
    # #endregion
    
    try:
        # Ensure UNC access for backup location if it's a UNC path
        backup_base = backup_base or config.get_backup_location()
        if UNC_AUTH_AVAILABLE and unc_auth.is_unc_path(backup_base):
            username, password = config.get_backup_unc_credentials()
            if not unc_auth.ensure_unc_access(backup_base, username, password):
                logger.error(f"Cannot access UNC backup location {backup_base}. Check backup UNC credentials in Settings.")
                return None

        # Verify source file exists
        if not source_file.exists():
            error_msg = f"Source file does not exist: {source_file}"
            logger.error(error_msg)
            # #region agent log
            log_entry2 = {
                "sessionId": "debug-session",
                "runId": "backup-debug",
                "hypothesisId": "H2",
                "location": "backup.py:create_backup",
                "message": "source file does not exist",
                "data": {"source_file": str(source_file)},
                "timestamp": int(time_module.time() * 1000)
            }
            try:
                with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                    f.write(json.dumps(log_entry2) + "\n")
            except: pass
            # #endregion
            return None
        
        backup_file = get_backup_path(source_file, backup_base)
        
        # #region agent log
        log_entry3 = {
            "sessionId": "debug-session",
            "runId": "backup-debug",
            "hypothesisId": "H3",
            "location": "backup.py:create_backup",
            "message": "backup path generated",
            "data": {
                "backup_file": str(backup_file),
                "backup_base": backup_base or config.get_backup_location(),
                "backup_parent": str(backup_file.parent),
                "backup_parent_exists": backup_file.parent.exists()
            },
            "timestamp": int(time_module.time() * 1000)
        }
        try:
            with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry3) + "\n")
        except: pass
        # #endregion
        
        # Create parent directories with error handling
        try:
            backup_file.parent.mkdir(parents=True, exist_ok=True)
            # #region agent log
            log_entry4 = {
                "sessionId": "debug-session",
                "runId": "backup-debug",
                "hypothesisId": "H4",
                "location": "backup.py:create_backup",
                "message": "backup parent directory created",
                "data": {
                    "backup_parent": str(backup_file.parent),
                    "backup_parent_exists": backup_file.parent.exists(),
                    "backup_parent_writable": os.access(backup_file.parent, os.W_OK) if backup_file.parent.exists() else False
                },
                "timestamp": int(time_module.time() * 1000)
            }
            try:
                with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                    f.write(json.dumps(log_entry4) + "\n")
            except: pass
            # #endregion
        except (PermissionError, OSError) as e:
            error_msg = f"Cannot create backup directory {backup_file.parent}: {e}"
            logger.error(error_msg)
            # #region agent log
            log_entry5 = {
                "sessionId": "debug-session",
                "runId": "backup-debug",
                "hypothesisId": "H5",
                "location": "backup.py:create_backup",
                "message": "failed to create backup directory",
                "data": {
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "backup_parent": str(backup_file.parent)
                },
                "timestamp": int(time_module.time() * 1000)
            }
            try:
                with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                    f.write(json.dumps(log_entry5) + "\n")
            except: pass
            # #endregion
            return None
        
        # Check if backup already exists
        if backup_file.exists():
            logger.warning(f"Backup already exists: {backup_file}")
            # Optionally, add timestamp to avoid overwriting
            import time
            timestamp = int(time.time())
            backup_file = backup_file.with_stem(f"{backup_file.stem}_{timestamp}")
        
        # Check available disk space
        try:
            import shutil as shutil_module
            backup_drive = backup_file.parent.drive or backup_file.parent.root
            if backup_drive:
                stat = shutil_module.disk_usage(backup_file.parent)
                free_space = stat.free
                source_size = source_file.stat().st_size
                # #region agent log
                log_entry6 = {
                    "sessionId": "debug-session",
                    "runId": "backup-debug",
                    "hypothesisId": "H6",
                    "location": "backup.py:create_backup",
                    "message": "disk space check",
                    "data": {
                        "free_space": free_space,
                        "source_size": source_size,
                        "has_enough_space": free_space > source_size * 1.1  # 10% buffer
                    },
                    "timestamp": int(time_module.time() * 1000)
                }
                try:
                    with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                        f.write(json.dumps(log_entry6) + "\n")
                except: pass
                # #endregion
                if free_space < source_size * 1.1:  # Need at least 10% more than file size
                    error_msg = f"Insufficient disk space for backup. Free: {free_space / (1024**3):.2f} GB, Required: {source_size * 1.1 / (1024**3):.2f} GB"
                    logger.error(error_msg)
                    return None
        except Exception as e:
            logger.warning(f"Could not check disk space: {e}")
        
        # Check if source file is accessible (not locked)
        try:
            # Try to open file in read mode to check if it's locked
            with open(source_file, 'rb') as test_handle:
                test_handle.read(1)
        except (IOError, PermissionError, OSError) as lock_error:
            error_msg = f"Source file is locked or inaccessible: {lock_error}"
            logger.error(error_msg)
            # #region agent log
            log_entry_lock = {
                "sessionId": "debug-session",
                "runId": "backup-debug",
                "hypothesisId": "H13",
                "location": "backup.py:create_backup",
                "message": "source file locked",
                "data": {
                    "error": str(lock_error),
                    "error_type": type(lock_error).__name__,
                    "source_file": str(source_file)
                },
                "timestamp": int(time_module.time() * 1000)
            }
            try:
                with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                    f.write(json.dumps(log_entry_lock) + "\n")
            except: pass
            # #endregion
            return None
        
        # Copy file with retry logic
        logger.info(f"Creating backup: {source_file} -> {backup_file}")
        # #region agent log
        log_entry7 = {
            "sessionId": "debug-session",
            "runId": "backup-debug",
            "hypothesisId": "H7",
            "location": "backup.py:create_backup",
            "message": "before copy2",
            "data": {
                "source_file": str(source_file),
                "source_exists": source_file.exists(),
                "source_size": source_file.stat().st_size if source_file.exists() else 0,
                "backup_file": str(backup_file),
                "backup_exists": backup_file.exists()
            },
            "timestamp": int(time_module.time() * 1000)
        }
        try:
            with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry7) + "\n")
        except: pass
        # #endregion
        
        # Retry copy operation up to 3 times
        import time
        max_copy_retries = 3
        copy_retry_delay = 1.0
        copy_success = False
        
        for copy_attempt in range(max_copy_retries):
            try:
                shutil.copy2(source_file, backup_file)
                copy_success = True
                break
            except (PermissionError, OSError, IOError) as copy_error:
                if copy_attempt < max_copy_retries - 1:
                    logger.warning(f"Backup copy failed (attempt {copy_attempt + 1}/{max_copy_retries}): {copy_error}. Retrying in {copy_retry_delay}s...")
                    time.sleep(copy_retry_delay)
                    # Re-check file accessibility
                    try:
                        with open(source_file, 'rb') as test_handle:
                            test_handle.read(1)
                    except (IOError, PermissionError, OSError):
                        error_msg = f"Source file became inaccessible during retry: {source_file}"
                        logger.error(error_msg)
                        return None
                else:
                    # Last attempt failed - re-raise to be caught by outer exception handler
                    raise
        
        # #region agent log
        log_entry8 = {
            "sessionId": "debug-session",
            "runId": "backup-debug",
            "hypothesisId": "H8",
            "location": "backup.py:create_backup",
            "message": "after copy2",
            "data": {
                "backup_file": str(backup_file),
                "backup_exists": backup_file.exists(),
                "backup_size": backup_file.stat().st_size if backup_file.exists() else 0,
                "source_size": source_file.stat().st_size
            },
            "timestamp": int(time_module.time() * 1000)
        }
        try:
            with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry8) + "\n")
        except: pass
        # #endregion
        
        # Verify backup was created
        if backup_file.exists() and backup_file.stat().st_size == source_file.stat().st_size:
            logger.info(f"Backup created successfully: {backup_file}")
            return backup_file
        else:
            error_msg = f"Backup verification failed: {backup_file}"
            logger.error(error_msg)
            if backup_file.exists():
                backup_file.unlink()  # Remove incomplete backup
            # #region agent log
            log_entry9 = {
                "sessionId": "debug-session",
                "runId": "backup-debug",
                "hypothesisId": "H9",
                "location": "backup.py:create_backup",
                "message": "backup verification failed",
                "data": {
                    "backup_file": str(backup_file),
                    "backup_exists": backup_file.exists(),
                    "backup_size": backup_file.stat().st_size if backup_file.exists() else 0,
                    "source_size": source_file.stat().st_size
                },
                "timestamp": int(time_module.time() * 1000)
            }
            try:
                with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                    f.write(json.dumps(log_entry9) + "\n")
            except: pass
            # #endregion
            return None
    
    except PermissionError as e:
        error_msg = f"Permission denied creating backup for {source_file}: {e}"
        logger.error(error_msg)
        # #region agent log
        log_entry10 = {
            "sessionId": "debug-session",
            "runId": "backup-debug",
            "hypothesisId": "H10",
            "location": "backup.py:create_backup",
            "message": "PermissionError",
            "data": {
                "error": str(e),
                "source_file": str(source_file),
                "backup_file": str(backup_file) if 'backup_file' in locals() else None
            },
            "timestamp": int(time_module.time() * 1000)
        }
        try:
            with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry10) + "\n")
        except: pass
        # #endregion
        return None
    except OSError as e:
        error_msg = f"OS error creating backup for {source_file}: {e}"
        logger.error(error_msg)
        # #region agent log
        log_entry11 = {
            "sessionId": "debug-session",
            "runId": "backup-debug",
            "hypothesisId": "H11",
            "location": "backup.py:create_backup",
            "message": "OSError",
            "data": {
                "error": str(e),
                "error_type": type(e).__name__,
                "error_code": getattr(e, 'winerror', None) or getattr(e, 'errno', None),
                "source_file": str(source_file),
                "backup_file": str(backup_file) if 'backup_file' in locals() else None
            },
            "timestamp": int(time_module.time() * 1000)
        }
        try:
            with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry11) + "\n")
        except: pass
        # #endregion
        return None
    except Exception as e:
        error_msg = f"Unexpected error creating backup for {source_file}: {e}"
        logger.error(error_msg, exc_info=True)
        # #region agent log
        log_entry12 = {
            "sessionId": "debug-session",
            "runId": "backup-debug",
            "hypothesisId": "H12",
            "location": "backup.py:create_backup",
            "message": "Unexpected exception",
            "data": {
                "error": str(e),
                "error_type": type(e).__name__,
                "source_file": str(source_file),
                "backup_file": str(backup_file) if 'backup_file' in locals() else None
            },
            "timestamp": int(time_module.time() * 1000)
        }
        try:
            with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry12) + "\n")
        except: pass
        # #endregion
        return None


def restore_backup(backup_file: Path, original_path: Path) -> bool:
    """
    Restore a file from backup.
    Returns True if successful, False otherwise.
    """
    try:
        if not backup_file.exists():
            logger.error(f"Backup file does not exist: {backup_file}")
            return False
        
        # Ensure original path's parent directory exists
        original_path.parent.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Restoring from backup: {backup_file} -> {original_path}")
        shutil.copy2(backup_file, original_path)
        
        # Verify restore
        if original_path.exists() and original_path.stat().st_size == backup_file.stat().st_size:
            logger.info(f"Restore successful: {original_path}")
            return True
        else:
            logger.error(f"Restore verification failed: {original_path}")
            return False
    
    except Exception as e:
        logger.error(f"Error restoring backup {backup_file}: {e}")
        return False


def backup_exists(source_file: Path, backup_base: Optional[str] = None) -> bool:
    """Check if a backup exists for the source file."""
    backup_file = get_backup_path(source_file, backup_base)
    return backup_file.exists()





