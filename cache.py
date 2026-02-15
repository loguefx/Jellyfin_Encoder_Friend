"""
File cache management for Jellyfin Audio Service.
Tracks converted files and their compliance status to avoid rescanning.
"""

import json
import logging
import threading
from pathlib import Path
from typing import Dict, Optional, Tuple, List
from datetime import datetime

logger = logging.getLogger(__name__)
# Debug log path (relative to this file so it works from any install path)
_DEBUG_LOG_PATH = Path(__file__).resolve().parent / ".cursor" / "debug.log"
CACHE_FILE = "file_cache.json"
_cache_lock = threading.Lock()
_cache_data = None
_cache_file_mtime = None  # Track cache file modification time


def get_cache_path() -> Path:
    """Get the full path to the cache file."""
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
    
    return exe_dir / CACHE_FILE


def load_cache() -> Dict:
    """Load cache from JSON file, creating empty cache if it doesn't exist.
    Automatically reloads if cache file has been modified externally."""
    global _cache_data, _cache_file_mtime
    
    cache_path = get_cache_path()
    
    # Check if cache file has been modified externally (e.g., user deleted entries)
    if cache_path.exists():
        try:
            current_mtime = cache_path.stat().st_mtime
            # If cache file was modified externally, reload it
            if _cache_data is not None and _cache_file_mtime is not None:
                if current_mtime != _cache_file_mtime:
                    logger.info(f"Cache file modified externally (mtime changed), reloading cache...")
                    _cache_data = None  # Force reload
                    _cache_file_mtime = None
        except Exception as e:
            logger.debug(f"Error checking cache file mtime: {e}")
    
    if _cache_data is not None:
        return _cache_data
    
    try:
        with _cache_lock:
            if cache_path.exists():
                with open(cache_path, 'r', encoding='utf-8') as f:
                    _cache_data = json.load(f)
                    _cache_file_mtime = cache_path.stat().st_mtime  # Store mtime after loading
                    logger.info(f"Loaded cache with {len(_cache_data.get('files', {}))} entries")
            else:
                _cache_data = {
                    'version': 1,
                    'files': {},
                    'last_updated': None
                }
                save_cache(skip_lock=True)
                if cache_path.exists():
                    _cache_file_mtime = cache_path.stat().st_mtime
                logger.info("Created new cache file")
    except Exception as e:
        logger.error(f"Error loading cache: {e}")
        _cache_data = {
            'version': 1,
            'files': {},
            'last_updated': None
        }
    
    return _cache_data


def save_cache(skip_lock: bool = False) -> bool:
    """Save cache to JSON file.
    
    CRITICAL: Before saving, removes any invalid entries (non-compliant, not converted).
    Only compliant or converted files should be in the cache.
    """
    global _cache_data, _cache_file_mtime
    
    # #region agent log
    import json
    log_entry_entry = {
        "sessionId": "debug-session",
        "runId": "cache-save",
        "hypothesisId": "C1,C2",
        "location": "cache.py:save_cache",
        "message": "save_cache entry",
        "data": {"skip_lock": skip_lock, "_cache_data_is_none": _cache_data is None},
        "timestamp": int(__import__('time').time() * 1000)
    }
    try:
        with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry_entry) + '\n')
    except: pass
    # #endregion
    
    if _cache_data is None:
        load_cache()
    
    cache_path = get_cache_path()
    
    # #region agent log
    log_entry_path = {
        "sessionId": "debug-session",
        "runId": "cache-save",
        "hypothesisId": "C1",
        "location": "cache.py:save_cache",
        "message": "Cache path determined",
        "data": {"cache_path": str(cache_path), "cache_path_exists": cache_path.exists(), "cache_path_parent": str(cache_path.parent), "parent_exists": cache_path.parent.exists()},
        "timestamp": int(__import__('time').time() * 1000)
    }
    try:
        with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry_path) + '\n')
    except: pass
    # #endregion
    
    try:
        lock = _cache_lock if not skip_lock else threading.Lock()
        with lock:
            # CRITICAL SAFETY CHECK: Remove any invalid entries before saving
            # Invalid = compliant=False AND converted=False (non-compliant files should never be cached)
            files = _cache_data.get('files', {})
            invalid_keys = []
            for file_key, file_entry in files.items():
                is_compliant = file_entry.get('compliant', False)
                is_converted = file_entry.get('converted', False)
                # If file is not compliant AND not converted, it's invalid
                if not is_compliant and not is_converted:
                    invalid_keys.append(file_key)
                    logger.warning(f"Removing invalid cache entry before save: {file_key} (compliant={is_compliant}, converted={is_converted})")
            
            # Remove invalid entries
            for key in invalid_keys:
                del files[key]
            
            if invalid_keys:
                logger.info(f"Removed {len(invalid_keys)} invalid cache entries before saving")
                # #region agent log
                import json
                log_entry_cleanup = {
                    "sessionId": "debug-session",
                    "runId": "cache-save",
                    "hypothesisId": "H_CLEANUP_INVALID",
                    "location": "cache.py:save_cache",
                    "message": "Removed invalid cache entries before save",
                    "data": {
                        "invalid_count": len(invalid_keys),
                        "invalid_keys": invalid_keys[:5]  # Sample
                    },
                    "timestamp": int(__import__('time').time() * 1000)
                }
                try:
                    with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                        f.write(json.dumps(log_entry_cleanup) + '\n')
                except: pass
                # #endregion
            
            _cache_data['last_updated'] = datetime.now().isoformat()
            compliant_count = sum(1 for f in files.values() if f.get('compliant', False))
            converted_count = sum(1 for f in files.values() if f.get('converted', False))
            total_count = len(files)
            
            # Final verification: all entries should be compliant or converted
            invalid_after = sum(1 for f in files.values() if not f.get('compliant', False) and not f.get('converted', False))
            if invalid_after > 0:
                logger.error(f"CRITICAL: Found {invalid_after} invalid entries after cleanup - this should never happen!")
            
            # #region agent log
            log_entry_before_save = {
                "sessionId": "debug-session",
                "runId": "cache-save",
                "hypothesisId": "C1",
                "location": "cache.py:save_cache",
                "message": "Before writing cache file",
                "data": {"cache_path": str(cache_path), "cache_path_exists": cache_path.exists(), "total_count": total_count},
                "timestamp": int(__import__('time').time() * 1000)
            }
            try:
                with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                    f.write(json.dumps(log_entry_before_save) + '\n')
            except: pass
            # #endregion
            
            # #region agent log
            log_entry_before_write = {
                "sessionId": "debug-session",
                "runId": "cache-save",
                "hypothesisId": "C1",
                "location": "cache.py:save_cache",
                "message": "Before file write",
                "data": {"cache_path": str(cache_path), "cache_data_files_count": len(_cache_data.get('files', {}))},
                "timestamp": int(__import__('time').time() * 1000)
            }
            try:
                with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                    f.write(json.dumps(log_entry_before_write) + '\n')
            except: pass
            # #endregion
            
            try:
                with open(cache_path, 'w', encoding='utf-8') as f:
                    json.dump(_cache_data, f, indent=2, ensure_ascii=False)
                # #region agent log
                log_entry_write_success = {
                    "sessionId": "debug-session",
                    "runId": "cache-save",
                    "hypothesisId": "C1",
                    "location": "cache.py:save_cache",
                    "message": "File write succeeded",
                    "data": {"cache_path": str(cache_path)},
                    "timestamp": int(__import__('time').time() * 1000)
                }
                try:
                    with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                        f.write(json.dumps(log_entry_write_success) + '\n')
                except: pass
                # #endregion
            except Exception as write_e:
                # #region agent log
                log_entry_write_error = {
                    "sessionId": "debug-session",
                    "runId": "cache-save",
                    "hypothesisId": "C2",
                    "location": "cache.py:save_cache",
                    "message": "File write failed",
                    "data": {"cache_path": str(cache_path), "error": str(write_e), "error_type": type(write_e).__name__},
                    "timestamp": int(__import__('time').time() * 1000)
                }
                try:
                    with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                        f.write(json.dumps(log_entry_write_error) + '\n')
                except: pass
                # #endregion
                raise  # Re-raise to be caught by outer handler
            
            # #region agent log
            log_entry_after_save = {
                "sessionId": "debug-session",
                "runId": "cache-save",
                "hypothesisId": "C1",
                "location": "cache.py:save_cache",
                "message": "After writing cache file",
                "data": {"cache_path": str(cache_path), "cache_path_exists": cache_path.exists()},
                "timestamp": int(__import__('time').time() * 1000)
            }
            try:
                with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                    f.write(json.dumps(log_entry_after_save) + '\n')
            except: pass
            # #endregion
            
            # Update mtime after saving
            if cache_path.exists():
                _cache_file_mtime = cache_path.stat().st_mtime
            
            logger.debug(f"Cache saved: {total_count} total files, {compliant_count} compliant, {converted_count} converted, {invalid_after} invalid (cache file: {cache_path})")
            return True
    except Exception as e:
        # #region agent log
        log_entry_exception = {
            "sessionId": "debug-session",
            "runId": "cache-save",
            "hypothesisId": "C2",
            "location": "cache.py:save_cache",
            "message": "Exception in save_cache",
            "data": {"error": str(e), "error_type": type(e).__name__, "cache_path": str(cache_path) if 'cache_path' in locals() else "unknown"},
            "timestamp": int(__import__('time').time() * 1000)
        }
        try:
            with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry_exception) + '\n')
        except: pass
        # #endregion
        logger.error(f"Error saving cache: {e}")
        return False


def get_file_key(file_path: Path) -> str:
    """Get normalized cache key for a file path."""
    # Normalize path to handle UNC paths and different path separators
    return str(file_path.resolve())


def get_file_mtime(file_path: Path) -> Optional[float]:
    """Get file modification time."""
    try:
        return file_path.stat().st_mtime
    except (OSError, FileNotFoundError):
        return None


def is_file_cached(file_path: Path) -> Tuple[bool, Optional[Dict]]:
    """
    Check if file is in cache and if cache entry is still valid.
    Returns (is_cached, cache_entry).
    Cache entry is valid if:
    - File exists
    - File modification time matches cache
    - File is marked as compliant/converted
    
    Note: This function automatically reloads cache if file was modified externally.
    """
    # Always reload cache to ensure we have latest data (checks mtime internally)
    cache = load_cache()
    file_key = get_file_key(file_path)
    file_entry = cache.get('files', {}).get(file_key)
    
    # #region agent log
    import json
    log_entry = {
        "sessionId": "debug-session",
        "runId": "cache-check",
        "hypothesisId": "H_CACHE_CHECK",
        "location": "cache.py:is_file_cached",
        "message": "is_file_cached check",
        "data": {
            "file": str(file_path.name),
            "file_path": str(file_path),
            "file_key": file_key,
            "cache_size": len(cache.get('files', {})),
            "file_entry_exists": file_entry is not None,
            "cache_keys_sample": list(cache.get('files', {}).keys())[:3] if cache.get('files', {}) else []
        },
        "timestamp": int(__import__('time').time() * 1000)
    }
    try:
        with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry) + '\n')
    except: pass
    # #endregion
    
    if file_entry is None:
        # #region agent log
        log_entry_not_found = {
            "sessionId": "debug-session",
            "runId": "cache-check",
            "hypothesisId": "H_CACHE_NOT_FOUND",
            "location": "cache.py:is_file_cached",
            "message": "File not found in cache",
            "data": {"file": str(file_path.name), "file_key": file_key},
            "timestamp": int(__import__('time').time() * 1000)
        }
        try:
            with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry_not_found) + '\n')
        except: pass
        # #endregion
        return False, None
    
    # Check if file still exists
    if not file_path.exists():
        # File was deleted, remove from cache
        remove_file_from_cache(file_path)
        # #region agent log
        log_entry_deleted = {
            "sessionId": "debug-session",
            "runId": "cache-check",
            "hypothesisId": "H_FILE_DELETED",
            "location": "cache.py:is_file_cached",
            "message": "File deleted, removing from cache",
            "data": {"file": str(file_path.name)},
            "timestamp": int(__import__('time').time() * 1000)
        }
        try:
            with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry_deleted) + '\n')
        except: pass
        # #endregion
        return False, None
    
    # Check if modification time matches
    cached_mtime = file_entry.get('mtime')
    current_mtime = get_file_mtime(file_path)
    
    if current_mtime is None:
        # #region agent log
        log_entry_no_mtime = {
            "sessionId": "debug-session",
            "runId": "cache-check",
            "hypothesisId": "H_NO_MTIME",
            "location": "cache.py:is_file_cached",
            "message": "Cannot get file mtime",
            "data": {"file": str(file_path.name)},
            "timestamp": int(__import__('time').time() * 1000)
        }
        try:
            with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry_no_mtime) + '\n')
        except: pass
        # #endregion
        return False, None
    
    if cached_mtime != current_mtime:
        # File was modified, cache is invalid
        logger.debug(f"File modified: {file_path} (cached: {cached_mtime}, current: {current_mtime})")
        # #region agent log
        log_entry_modified = {
            "sessionId": "debug-session",
            "runId": "cache-check",
            "hypothesisId": "H_FILE_MODIFIED",
            "location": "cache.py:is_file_cached",
            "message": "File modified, cache invalid",
            "data": {"file": str(file_path.name), "cached_mtime": cached_mtime, "current_mtime": current_mtime},
            "timestamp": int(__import__('time').time() * 1000)
        }
        try:
            with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry_modified) + '\n')
        except: pass
        # #endregion
        return False, None
    
    # Check if file is marked as compliant/converted
    is_compliant = file_entry.get('compliant', False)
    is_converted = file_entry.get('converted', False)
    
    if is_compliant or is_converted:
        # File is compliant or converted - valid cache entry
        # #region agent log
        log_entry_cached = {
            "sessionId": "debug-session",
            "runId": "cache-check",
            "hypothesisId": "H_FILE_CACHED",
            "location": "cache.py:is_file_cached",
            "message": "File is cached and valid",
            "data": {"file": str(file_path.name), "is_compliant": is_compliant, "is_converted": is_converted},
            "timestamp": int(__import__('time').time() * 1000)
        }
        try:
            with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry_cached) + '\n')
        except: pass
        # #endregion
        return True, file_entry
    else:
        # File is in cache but marked as non-compliant and not converted
        # This should NOT happen - remove it from cache immediately
        logger.warning(f"File in cache but marked as non-compliant (should not be cached): {file_path}")
        # Remove the invalid entry
        if 'files' in cache and file_key in cache['files']:
            del cache['files'][file_key]
            save_cache()
        # #region agent log
        log_entry_invalid = {
            "sessionId": "debug-session",
            "runId": "cache-check",
            "hypothesisId": "H_INVALID_CACHE_ENTRY",
            "location": "cache.py:is_file_cached",
            "message": "Invalid cache entry (non-compliant, not converted) - removing",
            "data": {
                "file": str(file_path.name),
                "file_path": str(file_path),
                "file_key": file_key,
                "is_compliant": is_compliant,
                "is_converted": is_converted
            },
            "timestamp": int(__import__('time').time() * 1000)
        }
        try:
            with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry_invalid) + '\n')
        except: pass
        # #endregion
        return False, None


def cache_file_compliant(file_path: Path, probe_data: Optional[Dict] = None) -> bool:
    """Mark file as compliant in cache. Updates existing entry if file is already cached.
    ONLY call this for files that are actually compliant - never for non-compliant files.
    
    CRITICAL: This function should ONLY be called for files that have been verified as compliant.
    Non-compliant files should NEVER be cached - they should be converted first, then cached.
    """
    cache = load_cache()
    file_key = get_file_key(file_path)
    mtime = get_file_mtime(file_path)
    
    if mtime is None:
        logger.warning(f"Cannot cache file (no mtime): {file_path}")
        return False
    
    if 'files' not in cache:
        cache['files'] = {}
    
    # Check if file is already in cache - if so, update it rather than creating duplicate
    existing_entry = cache['files'].get(file_key)
    if existing_entry is not None:
        # File already in cache, just update the compliant flag and mtime
        # Ensure it's marked as compliant (in case it was previously non-compliant)
        # CRITICAL: Always set compliant=True when updating (this function is only for compliant files)
        existing_entry['compliant'] = True
        existing_entry['mtime'] = mtime
        existing_entry['cached_at'] = datetime.now().isoformat()
        # If it was marked as converted, keep that flag
        # (converted files are also compliant)
        logger.info(f"Updated existing cache entry for compliant file: {file_path}")
        # #region agent log
        import json
        log_entry_update = {
            "sessionId": "debug-session",
            "runId": "cache-compliant",
            "hypothesisId": "H_UPDATE_EXISTING",
            "location": "cache.py:cache_file_compliant",
            "message": "Updated existing cache entry (compliant)",
            "data": {
                "file": str(file_path.name),
                "file_path": str(file_path),
                "file_key": file_key,
                "was_compliant": existing_entry.get('compliant', False),
                "was_converted": existing_entry.get('converted', False)
            },
            "timestamp": int(__import__('time').time() * 1000)
        }
        try:
            with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry_update) + '\n')
        except: pass
        # #endregion
    else:
        # New entry - ONLY for compliant files
        cache['files'][file_key] = {
            'path': str(file_path),
            'mtime': mtime,
            'compliant': True,  # MUST be True - this function is only for compliant files
            'converted': False,  # Will be True after conversion
            'cached_at': datetime.now().isoformat()
        }
        logger.info(f"Added new cache entry for compliant file: {file_path}")
        # #region agent log
        import json
        log_entry_new = {
            "sessionId": "debug-session",
            "runId": "cache-compliant",
            "hypothesisId": "H_ADD_NEW",
            "location": "cache.py:cache_file_compliant",
            "message": "Added new cache entry (compliant)",
            "data": {
                "file": str(file_path.name),
                "file_path": str(file_path),
                "file_key": file_key,
                "compliant": True,
                "converted": False
            },
            "timestamp": int(__import__('time').time() * 1000)
        }
        try:
            with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry_new) + '\n')
        except: pass
        # #endregion
    
    return save_cache()


def cache_file_converted(file_path: Path, original_path: Optional[Path] = None, subtitle_file: Optional[Path] = None) -> bool:
    """Mark file as converted in cache.
    This function is ONLY called after successful conversion - converted files are always compliant.
    
    CRITICAL: This caches files that were previously non-compliant but are now compliant after conversion.
    
    Args:
        file_path: Path to converted file (usually .mp4) - this file is now compliant
        original_path: Path to original file before conversion (optional, for tracking)
        subtitle_file: Path to extracted subtitle file (optional, for tracking extracted subtitles)
    """
    cache = load_cache()
    
    # Cache the converted file (usually .mp4)
    # This file was previously non-compliant but is now compliant after conversion
    file_key = get_file_key(file_path)
    mtime = get_file_mtime(file_path)
    
    if mtime is None:
        logger.warning(f"Cannot cache converted file (no mtime): {file_path}")
        return False
    
    if 'files' not in cache:
        cache['files'] = {}
    
    # Converted files are ALWAYS compliant (they were converted to be compliant)
    # CRITICAL: Set both compliant=True and converted=True
    cache_entry = {
        'path': str(file_path),
        'mtime': mtime,
        'compliant': True,  # Converted files are always compliant (they were converted to meet compliance)
        'converted': True,  # Mark as converted so we know it was previously non-compliant
        'cached_at': datetime.now().isoformat()
    }
    
    # Add subtitle file info if provided (for tracking extracted subtitles)
    if subtitle_file and subtitle_file.exists():
        cache_entry['subtitle_file'] = str(subtitle_file)
        logger.debug(f"Caching subtitle file info: {subtitle_file} for video: {file_path}")
    
    # Check if entry already exists (update instead of duplicate)
    existing_entry = cache['files'].get(file_key)
    if existing_entry is not None:
        # Update existing entry
        existing_entry.update(cache_entry)
        logger.info(f"Updated existing cache entry for converted file: {file_path}")
        # #region agent log
        import json
        log_entry_update = {
            "sessionId": "debug-session",
            "runId": "cache-converted",
            "hypothesisId": "H_UPDATE_CONVERTED",
            "location": "cache.py:cache_file_converted",
            "message": "Updated existing cache entry (converted)",
            "data": {
                "file": str(file_path.name),
                "file_path": str(file_path),
                "file_key": file_key
            },
            "timestamp": int(__import__('time').time() * 1000)
        }
        try:
            with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry_update) + '\n')
        except: pass
        # #endregion
    else:
        # New entry
        cache['files'][file_key] = cache_entry
        logger.info(f"Added new cache entry for converted file: {file_path}")
        # #region agent log
        import json
        log_entry_new = {
            "sessionId": "debug-session",
            "runId": "cache-converted",
            "hypothesisId": "H_ADD_CONVERTED",
            "location": "cache.py:cache_file_converted",
            "message": "Added new cache entry (converted)",
            "data": {
                "file": str(file_path.name),
                "file_path": str(file_path),
                "file_key": file_key,
                "compliant": True,
                "converted": True
            },
            "timestamp": int(__import__('time').time() * 1000)
        }
        try:
            with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry_new) + '\n')
        except: pass
        # #endregion
    
    # IMPORTANT: Do NOT cache the original file if it's different
    # Non-compliant files should NEVER be in the cache
    # Only cache the converted file (which is compliant)
    # If original file still exists, remove it from cache (it's been replaced)
    if original_path and original_path != file_path:
        original_key = get_file_key(original_path)
        if original_key in cache.get('files', {}):
            # Remove original file from cache (it's been converted/replaced)
            del cache['files'][original_key]
            logger.info(f"Removed original file from cache (replaced by converted file): {original_path}")
            # #region agent log
            import json
            log_entry_remove_original = {
                "sessionId": "debug-session",
                "runId": "cache-converted",
                "hypothesisId": "H_REMOVE_ORIGINAL",
                "location": "cache.py:cache_file_converted",
                "message": "Removed original file from cache",
                "data": {
                    "original_path": str(original_path),
                    "converted_path": str(file_path)
                },
                "timestamp": int(__import__('time').time() * 1000)
            }
            try:
                with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                    f.write(json.dumps(log_entry_remove_original) + '\n')
            except: pass
            # #endregion
    
    return save_cache()


def remove_file_from_cache(file_path: Path) -> bool:
    """Remove file from cache. This is called for non-compliant files to ensure they are NOT in cache."""
    cache = load_cache()
    file_key = get_file_key(file_path)
    
    # #region agent log
    import json
    log_entry_before = {
        "sessionId": "debug-session",
        "runId": "cache-remove",
        "hypothesisId": "H_REMOVE_BEFORE",
        "location": "cache.py:remove_file_from_cache",
        "message": "Attempting to remove file from cache",
        "data": {
            "file": str(file_path.name),
            "file_path": str(file_path),
            "file_key": file_key,
            "file_in_cache": file_key in cache.get('files', {}),
            "cache_size_before": len(cache.get('files', {}))
        },
        "timestamp": int(__import__('time').time() * 1000)
    }
    try:
        with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry_before) + '\n')
    except: pass
    # #endregion
    
    if 'files' in cache and file_key in cache['files']:
        entry_before = cache['files'][file_key].copy()
        del cache['files'][file_key]
        result = save_cache()
        
        # #region agent log
        log_entry_removed = {
            "sessionId": "debug-session",
            "runId": "cache-remove",
            "hypothesisId": "H_REMOVE_SUCCESS",
            "location": "cache.py:remove_file_from_cache",
            "message": "File removed from cache",
            "data": {
                "file": str(file_path.name),
                "file_path": str(file_path),
                "file_key": file_key,
                "was_compliant": entry_before.get('compliant', False),
                "was_converted": entry_before.get('converted', False),
                "save_result": result,
                "cache_size_after": len(cache.get('files', {}))
            },
            "timestamp": int(__import__('time').time() * 1000)
        }
        try:
            with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry_removed) + '\n')
        except: pass
        # #endregion
        
        logger.info(f"Removed file from cache: {file_path} (was compliant: {entry_before.get('compliant', False)})")
        return result
    
    # #region agent log
    log_entry_not_found = {
        "sessionId": "debug-session",
        "runId": "cache-remove",
        "hypothesisId": "H_REMOVE_NOT_FOUND",
        "location": "cache.py:remove_file_from_cache",
        "message": "File not found in cache (nothing to remove)",
        "data": {
            "file": str(file_path.name),
            "file_path": str(file_path),
            "file_key": file_key
        },
        "timestamp": int(__import__('time').time() * 1000)
    }
    try:
        with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry_not_found) + '\n')
    except: pass
    # #endregion
    
    return True


def clear_cache() -> bool:
    """Clear entire cache."""
    global _cache_data
    
    # #region agent log
    import json
    log_entry = {
        "sessionId": "debug-session",
        "runId": "run1",
        "hypothesisId": "A",
        "location": "cache.py:clear_cache",
        "message": "clear_cache called",
        "data": {"cache_data_before": len(_cache_data.get('files', {})) if _cache_data else 0},
        "timestamp": int(__import__('time').time() * 1000)
    }
    try:
        with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry) + '\n')
    except: pass
    # #endregion
    
    with _cache_lock:
        _cache_data = {
            'version': 1,
            'files': {},
            'last_updated': None
        }
        _cache_file_mtime = None  # Reset mtime tracking
        result = save_cache(skip_lock=True)
        
        # #region agent log
        log_entry2 = {
            "sessionId": "debug-session",
            "runId": "run1",
            "hypothesisId": "A",
            "location": "cache.py:clear_cache",
            "message": "clear_cache completed",
            "data": {"save_result": result, "cache_data_after": len(_cache_data.get('files', {}))},
            "timestamp": int(__import__('time').time() * 1000)
        }
        try:
            with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry2) + '\n')
        except: pass
        # #endregion
        
        return result


def get_cache_stats() -> Dict:
    """Get cache statistics."""
    cache = load_cache()
    files = cache.get('files', {})
    
    compliant_count = sum(1 for f in files.values() if f.get('compliant', False))
    converted_count = sum(1 for f in files.values() if f.get('converted', False))
    
    return {
        'total_files': len(files),
        'compliant_files': compliant_count,
        'converted_files': converted_count,
        'last_updated': cache.get('last_updated')
    }


def get_converted_files_history() -> List[Dict]:
    """
    Get all converted files sorted by conversion date (newest first).
    
    Returns:
        List of dictionaries containing file information, sorted by cached_at date (descending)
    """
    cache_data = load_cache()
    files = cache_data.get('files', {})
    
    converted_files = []
    for file_key, file_entry in files.items():
        # Only include files that were converted
        if file_entry.get('converted', False):
            file_info = {
                'path': file_entry.get('path', file_key),
                'cached_at': file_entry.get('cached_at'),
                'mtime': file_entry.get('mtime'),
                'subtitle_file': file_entry.get('subtitle_file'),
                'converted_to': file_entry.get('converted_to'),  # If original was converted to different file
                'original_path': file_entry.get('path', file_key)  # Original path before conversion
            }
            converted_files.append(file_info)
    
    # Sort by cached_at date (newest first)
    # Handle None values by putting them at the end
    def sort_key(f):
        cached_at = f.get('cached_at')
        if cached_at is None:
            return datetime.min.isoformat()
        try:
            return datetime.fromisoformat(cached_at).isoformat()
        except (ValueError, TypeError):
            return datetime.min.isoformat()
    
    converted_files.sort(key=sort_key, reverse=True)
    
    return converted_files



