"""
Configuration management for Jellyfin Audio Service.
Handles JSON-based configuration with thread-safe updates.
"""

import json
import os
import threading
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

CONFIG_FILE = "config.json"
# Debug log path (relative to this file so it works from any install path)
_DEBUG_LOG_PATH = Path(__file__).resolve().parent / ".cursor" / "debug.log"
DEFAULT_CONFIG = {
    "unc_paths": [],  # List of path configs: {"path": "...", "unc_username": "...", "unc_password": "..."} or just strings for backward compatibility
    "unc_username": None,  # Global UNC username (fallback if per-path not set)
    "unc_password": None,  # Global UNC password (fallback if per-path not set)
    "scan_schedule": {
        "enabled": True,
        "interval_hours": 24,
        "time": "02:00"
    },
    "backup_location": "backups",
    "backup_unc_username": None,
    "backup_unc_password": None,
    "web_port": 8080,
    "web_host": "0.0.0.0",
    "ffmpeg_path": "ffmpeg",
    "ffprobe_path": "ffprobe",
    "audio_settings": {
        "codec": "aac",
        "profile": "aac_low",
        "bitrate": "192k",
        "channels": 2,
        "allowed_channels": [2, 6],  # 2.0 and 5.1
        "min_bitrate": 160,
        "max_bitrate": 320
    }
}

_config_lock = threading.Lock()
_config_cache = None


def get_config_path() -> Path:
    """Get the full path to the configuration file."""
    import sys
    # Handle both script and compiled executable cases
    try:
        if getattr(sys, 'frozen', False):
            # Running as compiled executable
            exe_dir = Path(sys.executable).parent
        else:
            # Running as script
            exe_dir = Path(__file__).parent
    except Exception:
        # Fallback to current working directory
        exe_dir = Path.cwd()
    
    return exe_dir / CONFIG_FILE


def load_config() -> Dict[str, Any]:
    """Load configuration from JSON file, creating default if it doesn't exist."""
    global _config_cache
    
    try:
        with _config_lock:
            config_path = get_config_path()
            
            if config_path.exists():
                try:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                        
                        # Convert old format (list of strings) to new format (list of dicts) for backward compatibility
                        if config.get("unc_paths") and isinstance(config["unc_paths"], list) and len(config["unc_paths"]) > 0:
                            if isinstance(config["unc_paths"][0], str):
                                # Old format - convert to new format
                                config["unc_paths"] = [{"path": p, "unc_username": None, "unc_password": None} for p in config["unc_paths"]]
                        
                        # Merge with defaults to ensure all keys exist
                        merged_config = {**DEFAULT_CONFIG, **config}
                        _config_cache = merged_config
                        return merged_config
                except (json.JSONDecodeError, IOError) as e:
                    print(f"Error loading config: {e}. Using defaults.")
                    config = DEFAULT_CONFIG.copy()
            else:
                config = DEFAULT_CONFIG.copy()
            
            # Save default config if it didn't exist
            # Use skip_lock=True since we already have the lock
            save_config(config, skip_lock=True)
            
            _config_cache = config
            return config
    except Exception as e:
        print(f"Error in load_config: {e}")
        import traceback
        traceback.print_exc()
        # Return default config on any error
        return DEFAULT_CONFIG.copy()


def save_config(config: Dict[str, Any], skip_lock: bool = False) -> bool:
    """Save configuration to JSON file."""
    global _config_cache
    
    def _do_save():
        try:
            config_path = get_config_path()
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
            _config_cache = config
            return True
        except IOError as e:
            print(f"Error saving config: {e}")
            return False
    
    if skip_lock:
        # Already have the lock, don't acquire it again
        return _do_save()
    else:
        with _config_lock:
            return _do_save()


def get_config() -> Dict[str, Any]:
    """Get current configuration (cached)."""
    global _config_cache
    
    if _config_cache is None:
        return load_config()
    return _config_cache


def update_config(updates: Dict[str, Any]) -> bool:
    """Update configuration with new values."""
    config = get_config()
    config.update(updates)
    return save_config(config)


def add_unc_path(path: str, unc_username: Optional[str] = None, unc_password: Optional[str] = None) -> bool:
    """Add or update a UNC path to monitor with optional credentials."""
    config = get_config()
    # Normalize the path before adding
    normalized_path = normalize_path(path)
    
    # Convert existing paths to dict format if needed (backward compatibility)
    unc_paths = config.get("unc_paths", [])
    path_configs = []
    for p in unc_paths:
        if isinstance(p, dict):
            path_configs.append(p)
        else:
            # Old format (string) - convert to dict
            path_configs.append({"path": p, "unc_username": None, "unc_password": None})
    
    # Check if normalized path already exists
    existing_normalized = [normalize_path(p.get("path") if isinstance(p, dict) else p) for p in path_configs]
    path_found = False
    for i, pc in enumerate(path_configs):
        pc_path = pc.get("path") if isinstance(pc, dict) else pc
        if normalize_path(pc_path) == normalized_path:
            # Path exists - update it with new credentials
            path_configs[i] = {
                "path": normalized_path,
                "unc_username": unc_username.strip() if unc_username else None,
                "unc_password": unc_password.strip() if unc_password else None
            }
            path_found = True
            break
    
    if not path_found:
        # Add new path config
        path_configs.append({
            "path": normalized_path,
            "unc_username": unc_username.strip() if unc_username else None,
            "unc_password": unc_password.strip() if unc_password else None
        })
    
    config["unc_paths"] = path_configs
    return save_config(config)


def normalize_path(path: str) -> str:
    """
    Normalize a path for comparison:
    - Remove trailing slashes/backslashes (except for root UNC paths)
    - Normalize path separators to backslashes on Windows
    - Handle both local and UNC paths
    """
    if not path:
        return path
    
    # Normalize separators to backslashes
    normalized = path.replace('/', '\\')
    
    # Remove trailing backslashes (but preserve UNC root)
    if normalized.startswith('\\\\'):
        # UNC path - remove trailing backslashes
        # \\server\share\ -> \\server\share
        # \\server\share -> \\server\share (no change)
        # Split by backslash and filter empty strings
        parts = [p for p in normalized.split('\\') if p]
        if len(parts) >= 2:
            # Reconstruct as \\server\share or \\server\share\subpath
            normalized = '\\\\' + '\\'.join(parts)
        else:
            # Invalid UNC path, just remove trailing backslashes
            normalized = normalized.rstrip('\\')
    else:
        # Local path - remove trailing backslashes (except drive root like C:\)
        if len(normalized) > 3 and normalized[1:3] == ':\\':
            # Drive letter path (C:\path\) - remove trailing backslash after drive root
            normalized = normalized.rstrip('\\')
        else:
            # Other local path
            normalized = normalized.rstrip('\\')
    
    return normalized


def remove_unc_path(path: str) -> bool:
    """Remove a UNC path from monitoring."""
    # #region agent log
    import json
    import time
    log_entry = {
        "sessionId": "debug-session",
        "runId": "run1",
        "hypothesisId": "H1,H2,H3",
        "location": "config.py:remove_unc_path",
        "message": "remove_unc_path entry",
        "data": {"path": path, "path_repr": repr(path), "path_type": type(path).__name__},
        "timestamp": int(time.time() * 1000)
    }
    try:
        with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry) + '\n')
    except: pass
    # #endregion
    
    # Normalize the input path
    normalized_path = normalize_path(path)
    # #region agent log
    log_entry_norm = {
        "sessionId": "debug-session",
        "runId": "run1",
        "hypothesisId": "H1",
        "location": "config.py:remove_unc_path",
        "message": "path normalized",
        "data": {"original_path": path, "normalized_path": normalized_path},
        "timestamp": int(time.time() * 1000)
    }
    try:
        with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry_norm) + '\n')
    except: pass
    # #endregion
    
    config = get_config()
    unc_paths = config.get("unc_paths", [])
    
    # Convert to list of path configs if needed (backward compatibility)
    path_configs = []
    for p in unc_paths:
        if isinstance(p, dict):
            path_configs.append(p)
        else:
            # Old format (string) - convert to dict
            path_configs.append({"path": p, "unc_username": None, "unc_password": None})
    
    # Normalize all paths in the list for comparison
    normalized_paths = [(pc.get("path") if isinstance(pc, dict) else pc, normalize_path(pc.get("path") if isinstance(pc, dict) else pc)) for pc in path_configs]
    
    # #region agent log
    path_comparisons = []
    for idx, (original, normalized) in enumerate(normalized_paths):
        path_comparisons.append({
            "index": idx,
            "original_path": original,
            "normalized_path": normalized,
            "normalized_match": normalized_path == normalized,
            "original_exact_match": path == original,
            "normalized_exact_match": normalized_path == normalized
        })
    log_entry2 = {
        "sessionId": "debug-session",
        "runId": "run1",
        "hypothesisId": "H1,H2,H3",
        "location": "config.py:remove_unc_path",
        "message": "path comparison check",
        "data": {
            "input_path": path,
            "normalized_input": normalized_path,
            "path_configs": [pc.get("path") if isinstance(pc, dict) else pc for pc in path_configs],
            "path_comparisons": path_comparisons
        },
        "timestamp": int(time.time() * 1000)
    }
    try:
        with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry2) + '\n')
    except: pass
    # #endregion
    
    # Try to find and remove the path (try both exact and normalized match)
    removed = False
    path_to_remove = None
    
    # Try normalized match (works for both old string format and new dict format)
    for i, (original_path, normed_path) in enumerate(normalized_paths):
        if normalized_path == normed_path:
            path_to_remove = original_path
            path_configs.pop(i)
            config["unc_paths"] = path_configs
            removed = True
            # #region agent log
            log_entry_match = {
                "sessionId": "debug-session",
                "runId": "run1",
                "hypothesisId": "H2",
                "location": "config.py:remove_unc_path",
                "message": "matched via normalization",
                "data": {"input_path": path, "normalized_input": normalized_path, "matched_original": original_path, "matched_normalized": normed_path},
                "timestamp": int(time.time() * 1000)
            }
            try:
                with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                    f.write(json.dumps(log_entry_match) + '\n')
            except: pass
            # #endregion
            break
    
    if removed:
        # #region agent log
        log_entry3 = {
            "sessionId": "debug-session",
            "runId": "run1",
            "hypothesisId": "H5",
            "location": "config.py:remove_unc_path",
            "message": "before save_config",
            "data": {"path_removed": path_to_remove, "config_after_remove": config.get("unc_paths", [])},
            "timestamp": int(time.time() * 1000)
        }
        try:
            with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry3) + '\n')
        except: pass
        # #endregion
        save_result = save_config(config)
        # #region agent log
        log_entry4 = {
            "sessionId": "debug-session",
            "runId": "run1",
            "hypothesisId": "H5",
            "location": "config.py:remove_unc_path",
            "message": "after save_config",
            "data": {"save_result": save_result, "path_removed": path_to_remove},
            "timestamp": int(time.time() * 1000)
        }
        try:
            with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry4) + '\n')
        except: pass
        # #endregion
        return save_result
    
    # #region agent log
    log_entry5 = {
        "sessionId": "debug-session",
        "runId": "run1",
        "hypothesisId": "H1,H2,H3",
        "location": "config.py:remove_unc_path",
        "message": "path not found in list",
        "data": {"input_path": path, "normalized_input": normalized_path, "path_configs": [pc.get("path") if isinstance(pc, dict) else pc for pc in path_configs]},
        "timestamp": int(time.time() * 1000)
    }
    try:
        with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry5) + '\n')
    except: pass
    # #endregion
    return False  # Path not found, return False instead of True


def get_unc_paths() -> List[str]:
    """Get list of configured UNC paths (strings only, for backward compatibility)."""
    config = get_config()
    unc_paths = config.get("unc_paths", [])
    # Convert to list of strings if they're dicts
    result = []
    for p in unc_paths:
        if isinstance(p, dict):
            result.append(p.get("path", ""))
        else:
            result.append(p)
    return result


def get_unc_path_configs() -> List[Dict[str, Any]]:
    """Get list of UNC path configurations with credentials."""
    config = get_config()
    unc_paths = config.get("unc_paths", [])
    # Convert to list of dicts if they're strings (backward compatibility)
    result = []
    for p in unc_paths:
        if isinstance(p, dict):
            result.append(p)
        else:
            # Old format (string) - convert to dict
            result.append({"path": p, "unc_username": None, "unc_password": None})
    return result


def get_scan_schedule() -> Dict[str, Any]:
    """Get scan schedule configuration."""
    return get_config()["scan_schedule"]


def get_backup_location() -> str:
    """Get backup location path."""
    return get_config()["backup_location"]


def get_backup_unc_credentials() -> Tuple[Optional[str], Optional[str]]:
    """Get UNC credentials for backup location (if backup path is UNC)."""
    cfg = get_config()
    return (cfg.get("backup_unc_username"), cfg.get("backup_unc_password"))


def get_web_port() -> int:
    """Get web server port."""
    return get_config()["web_port"]


def get_web_host() -> str:
    """Get web server host."""
    return get_config()["web_host"]


def get_ffmpeg_path() -> str:
    """Get FFmpeg executable path."""
    return get_config()["ffmpeg_path"]


def get_ffprobe_path() -> str:
    """Get FFprobe executable path."""
    return get_config()["ffprobe_path"]


def get_audio_settings() -> Dict[str, Any]:
    """Get audio conversion settings."""
    return get_config()["audio_settings"]

