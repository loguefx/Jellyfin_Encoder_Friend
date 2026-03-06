"""
File scanner for Jellyfin Audio Service.
Recursively scans UNC paths and analyzes video files for AAC compliance.
"""

import os
import subprocess
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any

import config
import cache
import unc_auth

logger = logging.getLogger(__name__)
# Debug log path (relative to this file so it works from any install path)
_DEBUG_LOG_PATH = Path(__file__).resolve().parent / ".cursor" / "debug.log"
# Session debug log for this debug run (local vs UNC path scan)
_SESSION_LOG = Path(__file__).resolve().parent / "debug-966f7d.log"

def _session_log(msg: str, data: dict, hypothesis_id: str, location: str):
    try:
        import time as _t
        entry = {"sessionId": "966f7d", "hypothesisId": hypothesis_id, "location": location, "message": msg, "data": data, "timestamp": int(_t.time() * 1000)}
        with open(str(_SESSION_LOG), 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry) + '\n')
    except Exception:
        pass

# Lazy import transcoder to avoid circular dependency
# transcoder imports scanner, so we import it only when needed
_transcoder_module = None

def _get_transcoder():
    """Lazy import of transcoder module to avoid circular dependencies."""
    global _transcoder_module
    if _transcoder_module is None:
        import transcoder
        _transcoder_module = transcoder
    return _transcoder_module

# Video file extensions to scan (matching subtitle program for consistency)
VIDEO_EXTENSIONS = {'.mkv', '.mp4', '.avi', '.m4v', '.mov', '.wmv', '.flv', '.webm', '.mpg', '.mpeg', '.ts', '.m2ts'}


def is_video_file(file_path: Path) -> bool:
    """Check if file is a video file based on extension."""
    return file_path.suffix.lower() in VIDEO_EXTENSIONS


def check_ffprobe_available() -> bool:
    """Check if ffprobe is available."""
    ffprobe_path = config.get_ffprobe_path()
    try:
        result = subprocess.run(
            [ffprobe_path, '-version'],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',  # Replace invalid bytes instead of crashing
            timeout=5,
            check=False
        )
        return result.returncode == 0
    except Exception:
        return False


def probe_video_file(file_path: Path) -> Optional[Dict]:
    """Use ffprobe to analyze video file and return metadata."""
    ffprobe_path = config.get_ffprobe_path()
    
    # Check if file exists first
    if not file_path.exists():
        logger.warning(f"File does not exist: {file_path}")
        return None
    
    try:
        cmd = [
            ffprobe_path,
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            str(file_path)
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',  # Replace invalid bytes instead of crashing
            timeout=30,
            check=True
        )
        
        return json.loads(result.stdout)
    except FileNotFoundError as e:
        # Only log this error once per scan session
        if not hasattr(probe_video_file, '_error_logged'):
            logger.error(f"FFprobe not found at '{ffprobe_path}'. Please ensure FFmpeg is installed and in PATH, or update the path in config.json")
            logger.error(f"Error details: {e}")
            probe_video_file._error_logged = True
        return None
    except subprocess.TimeoutExpired:
        logger.warning(f"FFprobe timeout for {file_path}")
        return None
    except subprocess.CalledProcessError as e:
        logger.warning(f"FFprobe error for {file_path}: {e.stderr}")
        return None
    except UnicodeDecodeError as e:
        logger.error(f"Encoding error reading FFprobe output for {file_path}: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse FFprobe output for {file_path}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error probing {file_path}: {e}", exc_info=True)
        return None


def check_audio_compliance(probe_data: Dict, file_path: Path) -> Tuple[bool, str]:
    """
    Check if video file meets Jellyfin compatibility requirements for all devices.
    Checks both audio and video codecs, bitrates, and container formats.
    Returns (is_compliant, reason).
    """
    audio_settings = config.get_audio_settings()
    
    # Check container format first (MP4 or MKV required)
    format_name = probe_data.get('format', {}).get('format_name', '').lower()
    container_ok = 'mp4' in format_name or 'matroska' in format_name or 'mkv' in format_name
    
    if not container_ok:
        return False, f"Container format '{format_name}' not MP4 or MKV"
    
    # Check video codec (H.264/AVC is most compatible, H.265/HEVC is also widely supported)
    video_streams = [s for s in probe_data.get('streams', []) if s.get('codec_type') == 'video']
    if video_streams:
        video_codec = video_streams[0].get('codec_name', '').lower()
        # H.264 (avc, h264) and H.265 (hevc, h265) are widely supported
        # Other codecs may require transcoding on some devices
        if video_codec not in ['h264', 'avc', 'hevc', 'h265']:
            return False, f"Video codec '{video_codec}' not H.264/AVC or H.265/HEVC (may require transcoding)"
    
    # Find audio streams
    audio_streams = [s for s in probe_data.get('streams', []) if s.get('codec_type') == 'audio']
    
    if not audio_streams:
        return False, "No audio stream found"
    
    # Check each audio stream
    for stream in audio_streams:
        codec_name = stream.get('codec_name', '').lower()
        
        # Check codec (AAC is preferred, MP3 is also widely supported)
        # AAC is recommended for maximum device compatibility
        if codec_name not in ['aac', 'mp3']:
            return False, f"Audio codec is '{codec_name}', not AAC or MP3 (AAC preferred for maximum compatibility)"
        
        # Check profile (only for AAC, MP3 doesn't have profiles)
        if codec_name == 'aac':
            profile = stream.get('profile', '').lower()
            if 'lc' not in profile and 'low' not in profile:
                return False, f"AAC profile is '{profile}', not AAC-LC (required for maximum device compatibility)"
        
        # Check channels
        channels = stream.get('channels', 0)
        allowed_channels = audio_settings.get('allowed_channels', [2, 6])
        if channels not in allowed_channels:
            return False, f"Audio has {channels} channels, not {allowed_channels}"
        
        # Check bitrate based on channel count
        # Jellyfin guideline: 64 Kbps per channel minimum
        # Stereo (2 channels): 128 Kbps minimum
        # 5.1 (6 channels): 384 Kbps minimum
        # We use configurable min/max but adjust based on channels
        bitrate_str = stream.get('bit_rate', '0')
        if bitrate_str and bitrate_str != 'N/A':
            try:
                bitrate = int(bitrate_str) / 1000  # Convert to kbps
                channels = stream.get('channels', 2)
                
                # Calculate minimum bitrate based on channels (64 kbps per channel)
                min_bitrate_per_channel = 64
                calculated_min_bitrate = channels * min_bitrate_per_channel
                
                # Use configured min_bitrate if higher, otherwise use calculated minimum
                config_min_bitrate = audio_settings.get('min_bitrate', 160)
                min_bitrate = max(calculated_min_bitrate, config_min_bitrate)
                max_bitrate = audio_settings.get('max_bitrate', 320)
                
                # #region agent log
                log_entry_bitrate = {
                    "sessionId": "debug-session",
                    "runId": "scan-debug",
                    "hypothesisId": "G",
                    "location": "scanner.py:check_audio_compliance",
                    "message": "Bitrate check",
                    "data": {
                        "file": str(file_path.name),
                        "bitrate_str": str(bitrate_str),
                        "bitrate_kbps": bitrate,
                        "channels": channels,
                        "calculated_min_bitrate": calculated_min_bitrate,
                        "config_min_bitrate": config_min_bitrate,
                        "min_bitrate": min_bitrate,
                        "max_bitrate": max_bitrate,
                        "in_range": min_bitrate <= bitrate <= max_bitrate,
                        "check_result": not (min_bitrate <= bitrate <= max_bitrate)
                    },
                    "timestamp": int(__import__('time').time() * 1000)
                }
                try:
                    with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                        f.write(json.dumps(log_entry_bitrate) + '\n')
                except: pass
                # #endregion
                
                if not (min_bitrate <= bitrate <= max_bitrate):
                    return False, f"Audio bitrate is {bitrate:.0f}kbps ({channels} channels), minimum required: {min_bitrate:.0f}kbps (64 kbps per channel)"
            except (ValueError, TypeError):
                # If bitrate parsing fails, check format bitrate
                format_bitrate = probe_data.get('format', {}).get('bit_rate', '0')
                if format_bitrate and format_bitrate != 'N/A':
                    try:
                        # Estimate audio bitrate (rough approximation)
                        total_bitrate = int(format_bitrate) / 1000
                        # Assume audio is ~20% of total (conservative estimate)
                        estimated_audio_bitrate = total_bitrate * 0.2
                        min_bitrate = audio_settings.get('min_bitrate', 160)
                        max_bitrate = audio_settings.get('max_bitrate', 320)
                        
                        if not (min_bitrate <= estimated_audio_bitrate <= max_bitrate):
                            return False, f"Estimated audio bitrate is {estimated_audio_bitrate:.0f}kbps, not in range {min_bitrate}-{max_bitrate}kbps"
                    except (ValueError, TypeError):
                        pass  # Skip bitrate check if we can't parse it
    
    return True, "Compliant"


def scan_directory(directory: Path, recursive: bool = True) -> List[Path]:
    """Scan directory for video files."""
    video_files = []
    skipped_backups = 0
    total_dirs_scanned = 0

    # #region agent log
    _session_log("scan_directory entry", {"directory": str(directory), "exists": os.path.exists(str(directory)), "recursive": recursive}, "H2", "scanner.py:scan_directory")
    # #endregion

    try:
        if recursive:
            # #region agent log
            log_entry_before_walk = {
                "sessionId": "debug-session",
                "runId": "scan-debug",
                "hypothesisId": "H6",
                "location": "scanner.py:scan_directory",
                "message": "Before os.walk call",
                "data": {"directory": str(directory), "directory_type": type(directory).__name__},
                "timestamp": int(__import__('time').time() * 1000)
            }
            try:
                with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                    f.write(json.dumps(log_entry_before_walk) + '\n')
            except: pass
            # #endregion
            
            # Test if path is accessible before os.walk
            try:
                test_list = list(os.listdir(str(directory)))
                # #region agent log
                log_entry_listdir_test = {
                    "sessionId": "debug-session",
                    "runId": "scan-debug",
                    "hypothesisId": "H6",
                    "location": "scanner.py:scan_directory",
                    "message": "os.listdir test succeeded",
                    "data": {"directory": str(directory), "item_count": len(test_list)},
                    "timestamp": int(__import__('time').time() * 1000)
                }
                try:
                    with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                        f.write(json.dumps(log_entry_listdir_test) + '\n')
                except: pass
                # #endregion
            except Exception as listdir_e:
                # #region agent log
                log_entry_listdir_failed = {
                    "sessionId": "debug-session",
                    "runId": "scan-debug",
                    "hypothesisId": "H6",
                    "location": "scanner.py:scan_directory",
                    "message": "os.listdir test failed - path not accessible",
                    "data": {"directory": str(directory), "error": str(listdir_e), "error_type": type(listdir_e).__name__},
                    "timestamp": int(__import__('time').time() * 1000)
                }
                try:
                    with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                        f.write(json.dumps(log_entry_listdir_failed) + '\n')
                except: pass
                # #endregion
                raise  # Re-raise to be caught by outer exception handler
            
            for root, dirs, files in os.walk(str(directory)):
                total_dirs_scanned += 1
                
                # #region agent log
                log_entry_walk_iteration = {
                    "sessionId": "debug-session",
                    "runId": "scan-debug",
                    "hypothesisId": "H6",
                    "location": "scanner.py:scan_directory",
                    "message": "os.walk iteration",
                    "data": {"root": root, "dirs_count": len(dirs), "files_count": len(files), "iteration": total_dirs_scanned},
                    "timestamp": int(__import__('time').time() * 1000)
                }
                try:
                    with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                        f.write(json.dumps(log_entry_walk_iteration) + '\n')
                except: pass
                # #endregion
                # Skip backup directories
                if 'backups' in root.lower():
                    skipped_backups += 1
                    continue
                
                # Log directory being scanned (every 10th directory to avoid spam)
                if total_dirs_scanned % 10 == 0 or len(files) > 0:
                    # #region agent log
                    log_entry_dir = {
                        "sessionId": "debug-session",
                        "runId": "scan-debug",
                        "hypothesisId": "H4",
                        "location": "scanner.py:scan_directory",
                        "message": "Scanning directory",
                        "data": {"directory": root, "file_count": len(files), "dirs_in_level": len(dirs)},
                        "timestamp": int(__import__('time').time() * 1000)
                    }
                    try:
                        with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                            f.write(json.dumps(log_entry_dir) + '\n')
                    except: pass
                    # #endregion
                
                for file in files:
                    file_path = Path(root) / file
                    if is_video_file(file_path):
                        video_files.append(file_path)
                        # Log each video file found (for first 20 files to avoid spam)
                        if len(video_files) <= 20:
                            # #region agent log
                            log_entry_file = {
                                "sessionId": "debug-session",
                                "runId": "scan-debug",
                                "hypothesisId": "H4",
                                "location": "scanner.py:scan_directory",
                                "message": "Video file found",
                                "data": {"file": str(file_path.name), "full_path": str(file_path), "directory": root},
                                "timestamp": int(__import__('time').time() * 1000)
                            }
                            try:
                                with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                                    f.write(json.dumps(log_entry_file) + '\n')
                            except: pass
                            # #endregion
        else:
            for item in directory.iterdir():
                if item.is_file() and is_video_file(item):
                    video_files.append(item)
    
    except PermissionError as e:
        logger.error(f"Permission denied accessing {directory}: {e}")
        # #region agent log
        log_entry_error = {
            "sessionId": "debug-session",
            "runId": "scan-debug",
            "hypothesisId": "H4",
            "location": "scanner.py:scan_directory",
            "message": "Permission error during scan",
            "data": {"directory": str(directory), "error": str(e)},
            "timestamp": int(__import__('time').time() * 1000)
        }
        try:
            with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry_error) + '\n')
        except: pass
        # #endregion
    except Exception as e:
        logger.error(f"Error scanning {directory}: {e}")
        # #region agent log
        log_entry_error = {
            "sessionId": "debug-session",
            "runId": "scan-debug",
            "hypothesisId": "H4",
            "location": "scanner.py:scan_directory",
            "message": "Exception during scan",
            "data": {"directory": str(directory), "error": str(e), "error_type": type(e).__name__},
            "timestamp": int(__import__('time').time() * 1000)
        }
        try:
            with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry_error) + '\n')
        except: pass
        # #endregion
    
    # #region agent log
    log_entry_end = {
        "sessionId": "debug-session",
        "runId": "scan-debug",
        "hypothesisId": "H4",
        "location": "scanner.py:scan_directory",
        "message": "Directory scan complete",
        "data": {"directory": str(directory), "video_files_found": len(video_files), "total_dirs_scanned": total_dirs_scanned, "skipped_backups": skipped_backups},
        "timestamp": int(__import__('time').time() * 1000)
    }
    try:
        with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry_end) + '\n')
    except: pass
    # #endregion
    
    return video_files


def scan_unc_paths() -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    Scan all configured UNC paths and return list of non-compliant files and statistics.
    Returns tuple of (non_compliant_files, stats_dict).
    non_compliant_files: list of dicts with 'path', 'reason', and 'probe_data' keys.
    stats_dict: dictionary with scan statistics (total_files_found, files_skipped_cache, etc.)
    """
    # Check if ffprobe is available
    ffprobe_path = config.get_ffprobe_path()
    if not check_ffprobe_available():
        logger.error(f"FFprobe is not available at '{ffprobe_path}'. Please ensure FFmpeg is installed and accessible.")
        logger.error("Download FFmpeg from https://ffmpeg.org/download.html and add it to PATH, or update 'ffprobe_path' in config.json")
        empty_stats = {
            'total_files_found': 0,
            'files_skipped_cache': 0,
            'files_probe_failed': 0,
            'files_processed': 0,
            'files_compliant': 0,
            'files_non_compliant': 0,
            'files_error': 0
        }
        return [], empty_stats
    
    # Get path configs with credentials
    path_configs = config.get_unc_path_configs()
    unc_paths = [pc.get("path") for pc in path_configs]  # For backward compatibility
    non_compliant = []
    ffprobe_error_logged = False

    # #region agent log
    _session_log("Paths to scan (from config)", {"paths": [str(p) for p in unc_paths], "is_unc": [unc_auth.is_unc_path(str(p)) for p in unc_paths]}, "H3", "scanner.py:scan_unc_paths")
    # #endregion

    # Statistics tracking
    stats = {
        'total_files_found': 0,
        'files_skipped_cache': 0,
        'files_probe_failed': 0,
        'files_processed': 0,
        'files_compliant': 0,
        'files_non_compliant': 0,
        'files_error': 0
    }
    
    logger.info(f"Starting scan of {len(unc_paths)} UNC path(s)")
    for i, path in enumerate(unc_paths, 1):
        logger.info(f"  [{i}/{len(unc_paths)}] {path}")
    
    # #region agent log
    import json
    log_entry_scan_start = {
        "sessionId": "debug-session",
        "runId": "scan-debug",
        "hypothesisId": "H5",
        "location": "scanner.py:scan_unc_paths",
        "message": "Scan starting",
        "data": {"unc_path_count": len(unc_paths), "unc_paths": [str(p) for p in unc_paths]},
        "timestamp": int(__import__('time').time() * 1000)
    }
    try:
        with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry_scan_start) + '\n')
    except: pass
    # #endregion
    
    for unc_path_idx, unc_path in enumerate(unc_paths, 1):
        # Get path config for this path to retrieve credentials
        path_config = None
        for pc in path_configs:
            if pc.get("path") == unc_path:
                path_config = pc
                break
        
        # Authenticate to UNC paths if credentials are configured
        # Use per-path credentials if available, otherwise fall back to global credentials
        if unc_auth.is_unc_path(str(unc_path)):
            username = None
            password = None
            
            # Try per-path credentials first
            if path_config:
                username = path_config.get("unc_username")
                password = path_config.get("unc_password")
            
            # Fall back to global credentials if per-path not set
            if not username or not password:
                cfg = config.get_config()
                username = cfg.get("unc_username")
                password = cfg.get("unc_password")
            
            # Authenticate if credentials are available
            if username and password:
                logger.info(f"Authenticating to UNC path {unc_path} with username: {username}")
                if not unc_auth.ensure_unc_access(str(unc_path), username, password):
                    logger.error(f"Failed to authenticate/access UNC path: {unc_path}")
                    logger.error("Check UNC credentials in path configuration if path requires authentication")
                    continue
            elif unc_auth.is_unc_path(str(unc_path)):
                # Try without credentials (may work if already authenticated)
                logger.debug(f"No credentials provided for {unc_path}, attempting direct access...")
                if not unc_auth.ensure_unc_access(str(unc_path), None, None):
                    logger.warning(f"Could not access UNC path {unc_path} without credentials")
                    continue
        
        # Like subtitle program - just try to scan, don't validate first
        # Validation checks (os.path.exists, os.access) may fail for UNC paths
        # even when they're accessible, so we just try to scan and catch exceptions
        # #region agent log
        import time as time_module
        _session_log("Starting scan attempt", {"unc_path": str(unc_path), "is_unc_path": unc_auth.is_unc_path(str(unc_path))}, "H1", "scanner.py:scan_unc_paths")
        # #endregion

        # Like subtitle program - pass string path directly, not Path object
        # UNC paths work better with string paths in os.walk()
        try:
            # #region agent log
            path_str = str(unc_path)
            path_obj_for_log = Path(unc_path)
            try:
                resolved = str(path_obj_for_log.resolve())
                exists_resolved = os.path.exists(resolved)
            except Exception as res_e:
                resolved = str(res_e)
                exists_resolved = False
            _session_log("Before scan_directory", {"path": path_str, "resolved": resolved, "exists": exists_resolved}, "H4", "scanner.py:scan_unc_paths")
            # #endregion

            # Like subtitle program - pass string path directly to scan_directory
            # scan_directory will convert to Path internally for os.walk(str(path))
            path_obj = Path(unc_path)
            video_files = scan_directory(path_obj)
            # #region agent log
            log_entry_scan_success = {
                "sessionId": "debug-session",
                "runId": "scan-debug",
                "hypothesisId": "H3",
                "location": "scanner.py:scan_unc_paths",
                "message": "scan_directory succeeded",
                "data": {"unc_path": str(unc_path), "video_file_count": len(video_files)},
                "timestamp": int(__import__('time').time() * 1000)
            }
            try:
                with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                    f.write(json.dumps(log_entry_scan_success) + '\n')
            except: pass
            # #endregion
            logger.info(f"Found {len(video_files)} video file(s) in {unc_path} (path {unc_path_idx}/{len(unc_paths)})")
            stats['total_files_found'] += len(video_files)
            if len(video_files) == 0:
                # #region agent log
                _session_log("Scan returned 0 video files", {"unc_path": str(unc_path), "is_unc": unc_auth.is_unc_path(str(unc_path))}, "H2,H4", "scanner.py:scan_unc_paths")
                # #endregion
                logger.warning(f"WARNING: No video files found in {unc_path} - check if path is correct and accessible")
        except PermissionError as e:
            # #region agent log
            _session_log("PermissionError during scan", {"unc_path": str(unc_path), "error": str(e), "is_unc": unc_auth.is_unc_path(str(unc_path))}, "H2,H5", "scanner.py:scan_unc_paths")
            # #endregion
            logger.error(f"Permission denied accessing path: {unc_path}: {e}")
            continue
        except Exception as e:
            # #region agent log
            _session_log("Exception during scan", {"unc_path": str(unc_path), "error": str(e), "error_type": type(e).__name__, "is_unc": unc_auth.is_unc_path(str(unc_path))}, "H2,H5", "scanner.py:scan_unc_paths")
            # #endregion
            logger.error(f"Error accessing path {unc_path}: {e}", exc_info=True)
            continue
        
        # #region agent log
        log_entry2 = {
            "sessionId": "debug-session",
            "runId": "scan-debug",
            "hypothesisId": "H5",
            "location": "scanner.py:scan_unc_paths",
            "message": "Video files found in UNC path",
            "data": {"unc_path": str(unc_path), "video_file_count": len(video_files)},
            "timestamp": int(__import__('time').time() * 1000)
        }
        try:
            with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry2) + '\n')
        except: pass
        # #endregion
        
        for video_file in video_files:
            try:
                # Check cache first - skip if file is already compliant/converted
                # Note: load_cache() now auto-reloads if cache file was modified externally
                is_cached, cache_entry = cache.is_file_cached(video_file)
                
                # #region agent log
                import json
                log_entry_cache = {
                    "sessionId": "debug-session",
                    "runId": "scan-debug",
                    "hypothesisId": "B",
                    "location": "scanner.py:scan_unc_paths",
                    "message": "File cache check result",
                    "data": {
                        "file": str(video_file.name),
                        "full_path": str(video_file),
                        "is_cached": is_cached,
                        "cache_entry_exists": cache_entry is not None,
                        "file_key": cache.get_file_key(video_file) if hasattr(cache, 'get_file_key') else "unknown"
                    },
                    "timestamp": int(__import__('time').time() * 1000)
                }
                try:
                    with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                        f.write(json.dumps(log_entry_cache) + '\n')
                except: pass
                # #endregion
                
                if is_cached:
                    # File is already cached (compliant or converted) - skip rescanning
                    # This prevents rescanning files that have already been processed
                    stats['files_skipped_cache'] += 1
                    is_compliant_cached = cache_entry.get('compliant', False) if cache_entry else False
                    is_converted_cached = cache_entry.get('converted', False) if cache_entry else False
                    if is_converted_cached:
                        logger.debug(f"Skipping cached converted file (already fixed): {video_file}")
                    else:
                        logger.debug(f"Skipping cached compliant file: {video_file}")
                    # #region agent log
                    log_entry_skipped = {
                        "sessionId": "debug-session",
                        "runId": "scan-debug",
                        "hypothesisId": "H1",
                        "location": "scanner.py:scan_unc_paths",
                        "message": "File skipped due to cache (already processed)",
                        "data": {
                            "file": str(video_file.name),
                            "full_path": str(video_file),
                            "is_compliant": is_compliant_cached,
                            "is_converted": is_converted_cached
                        },
                        "timestamp": int(__import__('time').time() * 1000)
                    }
                    try:
                        with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                            f.write(json.dumps(log_entry_skipped) + '\n')
                    except: pass
                    # #endregion
                    continue
                
                # File not in cache or cache invalid, probe it
                probe_data = probe_video_file(video_file)
                if probe_data is None:
                    stats['files_probe_failed'] += 1
                    # Only log ffprobe error once
                    if not ffprobe_error_logged:
                        logger.warning(f"Could not probe {video_file} - check if ffprobe is available")
                        ffprobe_error_logged = True
                    # #region agent log
                    log_entry_probe_failed = {
                        "sessionId": "debug-session",
                        "runId": "scan-debug",
                        "hypothesisId": "H2",
                        "location": "scanner.py:scan_unc_paths",
                        "message": "File probe failed",
                        "data": {"file": str(video_file.name), "full_path": str(video_file)},
                        "timestamp": int(__import__('time').time() * 1000)
                    }
                    try:
                        with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                            f.write(json.dumps(log_entry_probe_failed) + '\n')
                    except: pass
                    # #endregion
                    continue
                
                stats['files_processed'] += 1
                is_compliant, reason = check_audio_compliance(probe_data, video_file)
                logger.debug(f"File {video_file.name}: compliant={is_compliant}, reason={reason}")
                
                # #region agent log
                log_entry_compliance = {
                    "sessionId": "debug-session",
                    "runId": "scan-debug",
                    "hypothesisId": "D",
                    "location": "scanner.py:scan_unc_paths",
                    "message": "File compliance check",
                    "data": {"file": str(video_file.name), "full_path": str(video_file), "is_compliant": is_compliant, "reason": reason},
                    "timestamp": int(__import__('time').time() * 1000)
                }
                try:
                    with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                        f.write(json.dumps(log_entry_compliance) + '\n')
                except: pass
                # #endregion
                
                if not is_compliant:
                    stats['files_non_compliant'] += 1
                    # Remove from cache if it was previously cached as compliant (file may have changed)
                    # Non-compliant files should NOT be in cache - only cache after conversion
                    was_removed = cache.remove_file_from_cache(video_file)
                    # #region agent log
                    import json
                    log_entry_non_compliant = {
                        "sessionId": "debug-session",
                        "runId": "scan-debug",
                        "hypothesisId": "H_NON_COMPLIANT",
                        "location": "scanner.py:scan_unc_paths",
                        "message": "Non-compliant file found - removing from cache",
                        "data": {
                            "file": str(video_file.name),
                            "file_path": str(video_file),
                            "reason": reason,
                            "was_removed_from_cache": was_removed
                        },
                        "timestamp": int(__import__('time').time() * 1000)
                    }
                    try:
                        with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                            f.write(json.dumps(log_entry_non_compliant) + '\n')
                    except: pass
                    # #endregion
                    
                    # Determine output format that will be used
                    try:
                        transcoder = _get_transcoder()
                        output_format = transcoder.get_output_format(probe_data)
                    except Exception as e:
                        logger.error(f"Error getting output format for {video_file}: {e}", exc_info=True)
                        output_format = 'MP4'  # Default fallback
                    
                    non_compliant.append({
                        'path': str(video_file),
                        'reason': reason,
                        'probe_data': probe_data,
                        'output_format': output_format
                    })
                    logger.debug(f"Non-compliant: {video_file} - {reason} (will convert to {output_format}) - NOT cached (will cache after conversion)")
                else:
                    stats['files_compliant'] += 1
                    # Check if file is already in cache before caching (prevent duplicates)
                    is_already_cached, existing_entry = cache.is_file_cached(video_file)
                    if is_already_cached:
                        logger.debug(f"Compliant file already in cache, skipping: {video_file}")
                        # #region agent log
                        log_entry_already_cached = {
                            "sessionId": "debug-session",
                            "runId": "scan-debug",
                            "hypothesisId": "H_ALREADY_CACHED",
                            "location": "scanner.py:scan_unc_paths",
                            "message": "Compliant file already cached, skipping",
                            "data": {"file": str(video_file.name), "full_path": str(video_file)},
                            "timestamp": int(__import__('time').time() * 1000)
                        }
                        try:
                            with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                                f.write(json.dumps(log_entry_already_cached) + '\n')
                        except: pass
                        # #endregion
                    else:
                        # Cache compliant files
                        cache_success = cache.cache_file_compliant(video_file, probe_data)
                        if cache_success:
                            logger.debug(f"Compliant file cached: {video_file}")
                            # #region agent log
                            log_entry_cached = {
                                "sessionId": "debug-session",
                                "runId": "scan-debug",
                                "hypothesisId": "H_CACHE_ADDED",
                                "location": "scanner.py:scan_unc_paths",
                                "message": "Compliant file cached",
                                "data": {"file": str(video_file.name), "full_path": str(video_file), "cache_success": cache_success},
                                "timestamp": int(__import__('time').time() * 1000)
                            }
                            try:
                                with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                                    f.write(json.dumps(log_entry_cached) + '\n')
                            except: pass
                            # #endregion
                        else:
                            logger.warning(f"Failed to cache compliant file: {video_file}")
                        # #region agent log
                        log_entry_cache_failed = {
                            "sessionId": "debug-session",
                            "runId": "scan-debug",
                            "hypothesisId": "H",
                            "location": "scanner.py:scan_unc_paths",
                            "message": "Failed to cache compliant file",
                            "data": {"file": str(video_file.name), "full_path": str(video_file)},
                            "timestamp": int(__import__('time').time() * 1000)
                        }
                        try:
                            with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                                f.write(json.dumps(log_entry_cache_failed) + '\n')
                        except: pass
                        # #endregion
            
            except Exception as e:
                stats['files_error'] += 1
                # #region agent log
                import json
                log_entry_error = {
                    "sessionId": "debug-session",
                    "runId": "scan-debug",
                    "hypothesisId": "H3",
                    "location": "scanner.py:scan_unc_paths",
                    "message": "Error processing file",
                    "data": {"file": str(video_file.name) if 'video_file' in locals() else "unknown", "full_path": str(video_file) if 'video_file' in locals() else "unknown", "error": str(e), "error_type": type(e).__name__},
                    "timestamp": int(__import__('time').time() * 1000)
                }
                try:
                    with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                        f.write(json.dumps(log_entry_error) + '\n')
                except: pass
                # #endregion
                logger.error(f"Error processing {video_file}: {e}", exc_info=True)
                if not ffprobe_error_logged:
                    ffprobe_error_logged = True
                continue
    
    logger.info(f"Scan complete. Found {len(non_compliant)} non-compliant file(s)")
    logger.info(f"Scan statistics: {stats['total_files_found']} total files, {stats['files_skipped_cache']} skipped (cached), {stats['files_probe_failed']} probe failed, {stats['files_processed']} processed, {stats['files_compliant']} compliant, {stats['files_non_compliant']} non-compliant, {stats['files_error']} errors")
    
    # #region agent log
    import json
    log_entry_final = {
        "sessionId": "debug-session",
        "runId": "scan-debug",
        "hypothesisId": "F",
        "location": "scanner.py:scan_unc_paths",
        "message": "Scan complete",
        "data": {
            "non_compliant_count": len(non_compliant),
            "stats": stats
        },
        "timestamp": int(__import__('time').time() * 1000)
    }
    try:
        with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry_final) + '\n')
    except: pass
    # #endregion
    
    return non_compliant, stats

