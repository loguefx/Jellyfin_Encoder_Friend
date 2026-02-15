"""
Flask web application for Jellyfin Audio Service.
Provides web interface for configuration and monitoring.
"""

import json
import logging
import threading
import traceback
import time
import schedule
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, make_response
from pathlib import Path

import config
import scanner
import transcoder
import cache
import unc_auth

# Determine template and static folders for frozen executables
import sys
import os
if getattr(sys, 'frozen', False):
    # Running as compiled executable
    exe_dir = Path(sys.executable).parent
    template_folder = str(exe_dir / "templates")
    static_folder = str(exe_dir / "static")
else:
    # Running as script - explicitly set paths relative to app.py location
    script_dir = Path(__file__).parent
    template_folder = str(script_dir / "templates")
    static_folder = str(script_dir / "static")

# Debug log path (works when run as script or frozen exe)
_DEBUG_LOG_DIR = (Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent) / ".cursor"
DEBUG_LOG_PATH = _DEBUG_LOG_DIR / "debug.log"
try:
    _DEBUG_LOG_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass

app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)
app.config['SECRET_KEY'] = 'jellyfin-audio-service-secret-key'

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Log template/static folder paths for debugging
if getattr(sys, 'frozen', False):
    logger.info(f"Running as frozen executable - exe_dir: {exe_dir}")
    logger.info(f"Template folder: {template_folder}, exists: {Path(template_folder).exists()}")
    logger.info(f"Static folder: {static_folder}, exists: {Path(static_folder).exists()}")
    if Path(template_folder).exists():
        logger.info(f"Template files: {list(Path(template_folder).glob('*.html'))}")
    if Path(static_folder).exists():
        logger.info(f"Static files: {list(Path(static_folder).glob('*'))}")
else:
    logger.info("Running as script - using default template/static folders")
logger.info(f"Flask app initialized - template_folder: {app.template_folder}, static_folder: {app.static_folder}")

# Global state for scan status
scan_status = {
    'running': False,
    'progress': 0,
    'total_files': 0,
    'processed_files': 0,
    'non_compliant_files': [],
    'compliant_files_count': 0,
    'conversion_results': None,
    'last_scan_time': None,
    'error': None,
    'converting': False,
    'conversion_progress': 0,
    'conversion_total': 0,
    'conversion_current_file': None,
    'conversion_file_progress': 0,
    'conversion_success_count': 0,
    'conversion_failed_count': 0,
    'converted_files': []
}

scan_lock = threading.Lock()
schedule_thread = None
schedule_running = False


def setup_schedule():
    """Setup scheduled scans based on configuration."""
    global schedule_running
    # #region agent log
    import json
    import time as time_module
    from datetime import datetime
    log_entry = {
        "sessionId": "debug-session",
        "runId": "schedule-debug",
        "hypothesisId": "H1",
        "location": "app.py:setup_schedule",
        "message": "setup_schedule called",
        "data": {"current_time": datetime.now().isoformat(), "schedule_running": schedule_running},
        "timestamp": int(time_module.time() * 1000)
    }
    try:
        with open(str(DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry) + '\n')
    except: pass
    # #endregion
    
    schedule_config = config.get_scan_schedule()
    
    # #region agent log
    log_entry2 = {
        "sessionId": "debug-session",
        "runId": "schedule-debug",
        "hypothesisId": "H2",
        "location": "app.py:setup_schedule",
        "message": "schedule config loaded",
        "data": {"schedule_config": schedule_config, "enabled": schedule_config.get('enabled', True)},
        "timestamp": int(time_module.time() * 1000)
    }
    try:
        with open(str(DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry2) + '\n')
    except: pass
    # #endregion
    
    if not schedule_config.get('enabled', True):
        logger.info("Scheduled scans are disabled")
        schedule.clear()
        return
    
    interval_hours = schedule_config.get('interval_hours', 24)
    scan_time = schedule_config.get('time', '02:00')
    
    # #region agent log
    log_entry3 = {
        "sessionId": "debug-session",
        "runId": "schedule-debug",
        "hypothesisId": "H3",
        "location": "app.py:setup_schedule",
        "message": "schedule parameters",
        "data": {"interval_hours": interval_hours, "scan_time": scan_time, "current_time": datetime.now().strftime("%H:%M")},
        "timestamp": int(time_module.time() * 1000)
    }
    try:
        with open(str(DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry3) + '\n')
    except: pass
    # #endregion
    
    # Clear any existing scheduled tasks
    schedule.clear()
    
    # Schedule based on interval_hours
    if interval_hours < 24:
        # Schedule scans every N hours
        schedule.every(interval_hours).hours.do(run_scheduled_scan)
        logger.info(f"Scheduled scans: Every {interval_hours} hour(s)")
    else:
        # Schedule daily scan at specified time
        # Parse the time to check if it's already passed today
        from datetime import datetime
        try:
            hour, minute = map(int, scan_time.split(':'))
            now = datetime.now()
            scheduled_time_today = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            # If the scheduled time has already passed today (within last 2 hours), trigger immediately
            # Otherwise, schedule normally
            if scheduled_time_today < now:
                time_diff = (now - scheduled_time_today).total_seconds()
                if time_diff < 7200:  # Within 2 hours
                    # Time has passed recently - trigger immediately
                    logger.info(f"Scheduled time {scan_time} has passed today (by {int(time_diff/60)} minutes). Triggering scan immediately.")
                    # Run in a separate thread to avoid blocking
                    thread = threading.Thread(target=run_scheduled_scan, daemon=True)
                    thread.start()
                # Still schedule for tomorrow to maintain daily schedule
                schedule.every().day.at(scan_time).do(run_scheduled_scan)
                logger.info(f"Scheduled scans: Daily at {scan_time} (next run: tomorrow)")
            else:
                # Time hasn't passed yet today - schedule normally
                schedule.every().day.at(scan_time).do(run_scheduled_scan)
                logger.info(f"Scheduled scans: Daily at {scan_time}")
        except Exception as e:
            # Fallback to default behavior if time parsing fails
            logger.warning(f"Error parsing schedule time '{scan_time}': {e}. Using default scheduling.")
            schedule.every().day.at(scan_time).do(run_scheduled_scan)
            logger.info(f"Scheduled scans: Daily at {scan_time}")
    
    # #region agent log
    jobs = list(schedule.jobs)
    log_entry4 = {
        "sessionId": "debug-session",
        "runId": "schedule-debug",
        "hypothesisId": "H4",
        "location": "app.py:setup_schedule",
        "message": "schedule jobs created",
        "data": {"job_count": len(jobs), "jobs": [str(job) for job in jobs]},
        "timestamp": int(time_module.time() * 1000)
    }
    try:
        with open(str(DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry4) + '\n')
    except: pass
    # #endregion
    
    # Start schedule checking thread if not already running
    if not schedule_running:
        start_schedule_thread()


def run_scheduled_scan():
    """Run a scheduled scan and automatically convert non-compliant files."""
    # #region agent log
    import json
    import time as time_module
    from datetime import datetime
    log_entry = {
        "sessionId": "debug-session",
        "runId": "schedule-debug",
        "hypothesisId": "H9",
        "location": "app.py:run_scheduled_scan",
        "message": "run_scheduled_scan called",
        "data": {"current_time": datetime.now().isoformat()},
        "timestamp": int(time_module.time() * 1000)
    }
    try:
        with open(str(DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry) + '\n')
    except: pass
    # #endregion
    
    logger.info("Starting scheduled scan...")
    
    # Check if scan is already running
    with scan_lock:
        if scan_status['running']:
            logger.warning("Scan already in progress, skipping scheduled scan")
            # #region agent log
            log_entry2 = {
                "sessionId": "debug-session",
                "runId": "schedule-debug",
                "hypothesisId": "H10",
                "location": "app.py:run_scheduled_scan",
                "message": "scan already running, skipping",
                "data": {},
                "timestamp": int(time_module.time() * 1000)
            }
            try:
                with open(str(DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                    f.write(json.dumps(log_entry2) + '\n')
            except: pass
            # #endregion
            return
    
    # Run scan with auto-convert enabled
    run_scan(auto_convert=True)


def schedule_loop():
    """Background thread that checks and runs scheduled tasks."""
    global schedule_running
    schedule_running = True
    logger.info("Schedule checking thread started")
    
    # #region agent log
    import json
    import time as time_module
    from datetime import datetime
    log_entry = {
        "sessionId": "debug-session",
        "runId": "schedule-debug",
        "hypothesisId": "H5",
        "location": "app.py:schedule_loop",
        "message": "schedule_loop started",
        "data": {"current_time": datetime.now().isoformat()},
        "timestamp": int(time_module.time() * 1000)
    }
    try:
        with open(str(DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry) + '\n')
    except: pass
    # #endregion
    
    while schedule_running:
        try:
            # #region agent log
            current_time = datetime.now()
            jobs = list(schedule.jobs)
            pending_jobs = [j for j in jobs if j.should_run]
            log_entry2 = {
                "sessionId": "debug-session",
                "runId": "schedule-debug",
                "hypothesisId": "H6",
                "location": "app.py:schedule_loop",
                "message": "checking schedule",
                "data": {
                    "current_time": current_time.isoformat(),
                    "current_time_str": current_time.strftime("%H:%M:%S"),
                    "job_count": len(jobs),
                    "pending_job_count": len(pending_jobs),
                    "jobs": [{"next_run": str(j.next_run) if hasattr(j, 'next_run') else None, "should_run": j.should_run} for j in jobs]
                },
                "timestamp": int(time_module.time() * 1000)
            }
            try:
                with open(str(DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                    f.write(json.dumps(log_entry2) + '\n')
            except: pass
            # #endregion
            
            ran_jobs = schedule.run_pending()
            
            # #region agent log
            log_entry3 = {
                "sessionId": "debug-session",
                "runId": "schedule-debug",
                "hypothesisId": "H7",
                "location": "app.py:schedule_loop",
                "message": "after run_pending",
                "data": {"ran_pending": True, "jobs_ran": len(ran_jobs) if ran_jobs else 0},
                "timestamp": int(time_module.time() * 1000)
            }
            try:
                with open(str(DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                    f.write(json.dumps(log_entry3) + '\n')
            except: pass
            # #endregion
            
            time.sleep(10)  # Check every 10 seconds for more precise timing
        except Exception as e:
            logger.error(f"Error in schedule loop: {e}", exc_info=True)
            # #region agent log
            log_entry4 = {
                "sessionId": "debug-session",
                "runId": "schedule-debug",
                "hypothesisId": "H8",
                "location": "app.py:schedule_loop",
                "message": "error in schedule loop",
                "data": {"error": str(e), "error_type": type(e).__name__},
                "timestamp": int(time_module.time() * 1000)
            }
            try:
                with open(str(DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                    f.write(json.dumps(log_entry4) + '\n')
            except: pass
            # #endregion
            time.sleep(60)


def start_schedule_thread():
    """Start the background thread for checking schedules."""
    global schedule_thread, schedule_running
    
    if schedule_thread and schedule_thread.is_alive():
        return  # Already running
    
    schedule_running = True
    schedule_thread = threading.Thread(target=schedule_loop, daemon=True)
    schedule_thread.start()
    logger.info("Schedule thread started")


@app.route('/favicon.ico')
def favicon():
    """Return empty favicon to prevent 404 errors."""
    return '', 204

@app.route('/')
def index():
    """Main configuration page."""
    try:
        cfg = config.get_config()
        # #region agent log
        import json
        import os
        try:
            _DEBUG_LOG_DIR.mkdir(parents=True, exist_ok=True)
            template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates', 'index.html')
            with open(str(DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    'sessionId': 'debug-session',
                    'runId': 'template-debug',
                    'hypothesisId': 'A',
                    'location': 'app.py:index',
                    'message': 'Rendering index template',
                    'data': {
                        'template_folder': str(app.template_folder),
                        'template_path': template_path,
                        'template_exists': os.path.exists(template_path),
                        'frozen': getattr(sys, 'frozen', False),
                        'exe_dir': str(exe_dir) if getattr(sys, 'frozen', False) else 'N/A'
                    },
                    'timestamp': int(time.time() * 1000)
                }) + '\n')
        except Exception as e:
            try:
                with open(str(DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                    f.write(json.dumps({
                        'sessionId': 'debug-session',
                        'runId': 'template-debug',
                        'hypothesisId': 'A',
                        'location': 'app.py:index',
                        'message': 'Error logging template info',
                        'data': {'error': str(e)},
                        'timestamp': int(time.time() * 1000)
                    }) + '\n')
            except: pass
        # #endregion
        # Disable template caching to ensure fresh templates
        app.config['TEMPLATES_AUTO_RELOAD'] = True
        app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
        # Render template and convert to Response object to set headers
        html_content = render_template('index.html', config=cfg, scan_status=scan_status)
        response = make_response(html_content)
        # Add cache-busting headers
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    except Exception as e:
        logger.error(f"Error rendering index: {e}", exc_info=True)
        return f"Error loading page: {e}", 500


@app.route('/health')
def health():
    """Health check endpoint."""
    return jsonify({'status': 'ok', 'service': 'Jellyfin Audio Service'})


@app.route('/api/config', methods=['GET'])
def get_config_api():
    """Get current configuration."""
    return jsonify(config.get_config())


@app.route('/api/config', methods=['POST'])
def update_config_api():
    """Update configuration."""
    try:
        data = request.json
        
        # Validate and update configuration
        if 'unc_paths' in data:
            # Handle UNC paths separately
            current_paths = config.get_unc_paths()
            new_paths = data.get('unc_paths', [])
            
            # Remove paths not in new list
            for path in current_paths:
                if path not in new_paths:
                    config.remove_unc_path(path)
            
            # Add new paths
            for path in new_paths:
                if path not in current_paths:
                    config.add_unc_path(path)
        
        # Update other settings
        updates = {}
        if 'scan_schedule' in data:
            updates['scan_schedule'] = data['scan_schedule']
            # Re-setup schedule when it changes
            setup_schedule()
        if 'backup_location' in data:
            updates['backup_location'] = data['backup_location']
        if 'backup_unc_username' in data:
            updates['backup_unc_username'] = data['backup_unc_username'] or None
        if 'backup_unc_password' in data:
            updates['backup_unc_password'] = data['backup_unc_password'] or None
        if 'web_port' in data:
            updates['web_port'] = data['web_port']
        if 'ffmpeg_path' in data:
            updates['ffmpeg_path'] = data['ffmpeg_path']
        if 'ffprobe_path' in data:
            updates['ffprobe_path'] = data['ffprobe_path']
        
        if updates:
            config.update_config(updates)
        
        return jsonify({'success': True, 'config': config.get_config()})
    
    except Exception as e:
        logger.error(f"Error updating config: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/unc_paths', methods=['POST'])
def add_unc_path_api():
    """Add a path (UNC or local) with optional credentials. Works like the subtitle program."""
    try:
        data = request.json
        path = data.get('path', '').strip()
        unc_username = data.get('unc_username', '').strip() if data.get('unc_username') else None
        unc_password = data.get('unc_password', '').strip() if data.get('unc_password') else None
        
        if not path:
            return jsonify({'success': False, 'error': 'Path is required'}), 400
        
        # Like the subtitle program - just save the path without validation
        # Validation happens later during scanning, and failures just log warnings
        success = config.add_unc_path(path, unc_username, unc_password)
        return jsonify({'success': success, 'paths': config.get_unc_paths()})
    
    except Exception as e:
        logger.error(f"Error adding path: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/unc_paths', methods=['DELETE'])
def remove_unc_path_api():
    """Remove a UNC path."""
    from urllib.parse import unquote
    try:
        # Get path from query parameter to avoid Flask path converter stripping backslashes
        path = request.args.get('path')
        if not path:
            return jsonify({'success': False, 'error': 'Path parameter is required'}), 400
        
        # URL decode the path to handle encoded backslashes
        path = unquote(path)
        
        # #region agent log
        import json as json_module
        import time
        log_entry = {
            "sessionId": "debug-session",
            "runId": "run2",
            "hypothesisId": "ALL",
            "location": "app.py:remove_unc_path_api",
            "message": "remove_unc_path_api entry",
            "data": {"path": path, "path_type": type(path).__name__, "path_repr": repr(path), "raw_query": request.query_string.decode('utf-8')},
            "timestamp": int(time.time() * 1000)
        }
        try:
            with open(str(DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                f.write(json_module.dumps(log_entry) + '\n')
        except: pass
        # #endregion
        
        # #region agent log
        current_paths_before = config.get_unc_paths()
        log_entry2 = {
            "sessionId": "debug-session",
            "runId": "run2",
            "hypothesisId": "H1,H2",
            "location": "app.py:remove_unc_path_api",
            "message": "before remove_unc_path call",
            "data": {"path": path, "current_paths": current_paths_before, "path_in_list": path in current_paths_before},
            "timestamp": int(time.time() * 1000)
        }
        try:
            with open(str(DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                f.write(json_module.dumps(log_entry2) + '\n')
        except: pass
        # #endregion
        success = config.remove_unc_path(path)
        
        # Also remove stored credentials if it's a UNC path
        # Try with both original and normalized path to ensure we delete credentials
        if unc_auth.is_unc_path(path):
            # Try to delete with original path
            unc_auth.delete_unc_credentials(path)
            # Also try with normalized path
            normalized = config.normalize_path(path)
            if normalized != path:
                unc_auth.delete_unc_credentials(normalized)
        
        # #region agent log
        current_paths_after = config.get_unc_paths()
        log_entry3 = {
            "sessionId": "debug-session",
            "runId": "run2",
            "hypothesisId": "ALL",
            "location": "app.py:remove_unc_path_api",
            "message": "after remove_unc_path call",
            "data": {"success": success, "current_paths_before": current_paths_before, "current_paths_after": current_paths_after, "path_removed": path not in current_paths_after},
            "timestamp": int(time.time() * 1000)
        }
        try:
            with open(str(DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                f.write(json_module.dumps(log_entry3) + '\n')
        except: pass
        # #endregion
        
        if success:
            return jsonify({'success': True, 'paths': config.get_unc_paths()})
        else:
            return jsonify({'success': False, 'error': 'Path not found in configured paths'}), 404
    
    except Exception as e:
        # #region agent log
        import json as json_module
        import time
        import traceback
        log_entry4 = {
            "sessionId": "debug-session",
            "runId": "run2",
            "hypothesisId": "H4",
            "location": "app.py:remove_unc_path_api",
            "message": "exception in remove_unc_path_api",
            "data": {"error": str(e), "error_type": type(e).__name__, "traceback": traceback.format_exc()[:500]},
            "timestamp": int(time.time() * 1000)
        }
        try:
            with open(str(DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                f.write(json_module.dumps(log_entry4) + '\n')
        except: pass
        # #endregion
        logger.error(f"Error removing UNC path: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/unc_paths/test', methods=['POST'])
def test_unc_path_api():
    """Test if a path is accessible. Like subtitle program - attempts test but doesn't block if it fails."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No JSON data provided'}), 400
        
        path = data.get('path')
        if not path:
            return jsonify({'success': False, 'error': 'Path parameter is required'}), 400
        
        # Try to test the path, but don't fail hard if it's not accessible
        # The path might be accessible from service context even if not from web server context
        try:
            access_success, error_msg = unc_auth.test_unc_access(path)
            if access_success:
                return jsonify({
                    'success': True,
                    'message': f'Path is accessible: {path}'
                })
            else:
                # Path test failed, but still return success with a warning message
                # Like subtitle program - paths are accepted even if temporarily inaccessible
                return jsonify({
                    'success': True,
                    'message': f'Path accepted (may not be accessible from web server context): {path}',
                    'warning': error_msg
                })
        except Exception as test_error:
            # Even if test throws exception, accept the path
            logger.warning(f"Path test failed for {path}: {test_error}")
            return jsonify({
                'success': True,
                'message': f'Path accepted: {path}',
                'warning': f'Could not verify accessibility: {str(test_error)}'
            })
    
    except Exception as e:
        logger.error(f"Error testing path: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/unc_paths/credentials', methods=['POST'])
def store_unc_credentials_api():
    """Store UNC path credentials (legacy endpoint for per-path credentials)."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No JSON data provided'}), 400
        
        path = data.get('path')
        username = data.get('username')
        password = data.get('password')
        
        if not path or not username or not password:
            return jsonify({'success': False, 'error': 'Path, username, and password are required'}), 400
        
        # Store credentials
        success = unc_auth.store_unc_credentials(path, username, password)
        if not success:
            return jsonify({'success': False, 'error': 'Failed to store credentials'}), 500
        
        # Test access with stored credentials
        test_success, test_error = unc_auth.test_unc_access(path, username, password)
        if not test_success:
            return jsonify({
                'success': False,
                'error': f'Credentials stored but access test failed: {test_error}'
            }), 401
        
        return jsonify({
            'success': True,
            'message': 'Credentials stored and verified'
        })
    
    except Exception as e:
        logger.error(f"Error storing UNC credentials: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/scan', methods=['POST'])
def start_scan_api():
    """Start a scan for non-compliant files."""
    global scan_status
    
    with scan_lock:
        if scan_status['running']:
            return jsonify({'success': False, 'error': 'Scan already in progress'}), 400
        
        scan_status['running'] = True
        scan_status['progress'] = 0
        scan_status['total_files'] = 0
        scan_status['processed_files'] = 0
        scan_status['non_compliant_files'] = []
        scan_status['compliant_files_count'] = 0
        scan_status['conversion_results'] = None
        scan_status['error'] = None
    
    # Run scan in background thread
    thread = threading.Thread(target=run_scan, daemon=True)
    thread.start()
    
    return jsonify({'success': True, 'message': 'Scan started'})


@app.route('/api/scan/status', methods=['GET'])
def get_scan_status_api():
    """Get current scan status."""
    # Update compliant files count from cache if not running
    if not scan_status.get('running', False):
        try:
            cache_stats = cache.get_cache_stats()
            scan_status['compliant_files_count'] = cache_stats.get('compliant_files', 0)
        except Exception as e:
            logger.debug(f"Error getting cache stats: {e}")
    return jsonify(scan_status)


@app.route('/api/conversion/errors', methods=['GET'])
def get_conversion_errors_api():
    """Get detailed conversion error information."""
    global scan_status
    with scan_lock:
        if scan_status.get('conversion_results'):
            errors = scan_status['conversion_results'].get('errors', {})
            failed = scan_status['conversion_results'].get('failed', [])
            return jsonify({
                'success': True,
                'failed_count': len(failed),
                'errors': {path: error for path, error in errors.items()}
            })
        return jsonify({'success': False, 'error': 'No conversion results available'})


@app.route('/api/convert', methods=['POST'])
def convert_files_api():
    """Convert non-compliant files."""
    try:
        data = request.json
        file_paths = data.get('files', [])
        
        if not file_paths:
            return jsonify({'success': False, 'error': 'No files specified'}), 400
        
        # Run conversion in background
        thread = threading.Thread(target=run_conversion, args=(file_paths,), daemon=True)
        thread.start()
        
        return jsonify({'success': True, 'message': 'Conversion started'})
    
    except Exception as e:
        logger.error(f"Error starting conversion: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/cache/stats', methods=['GET'])
def get_cache_stats_api():
    """Get cache statistics."""
    try:
        stats = cache.get_cache_stats()
        return jsonify({'success': True, 'stats': stats})
    except Exception as e:
        logger.error(f"Error getting cache stats: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/cache/clear', methods=['POST'])
def clear_cache_api():
    """Clear the file cache."""
    # #region agent log
    import json
    import time as time_module
    log_entry = {
        "sessionId": "debug-session",
        "runId": "cache-clear",
        "hypothesisId": "C1,C2,C3",
        "location": "app.py:clear_cache_api",
        "message": "clear_cache_api entry",
        "data": {},
        "timestamp": int(time_module.time() * 1000)
    }
    try:
        with open(str(DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry) + '\n')
    except: pass
    # #endregion
    
    try:
        # #region agent log
        log_entry_before = {
            "sessionId": "debug-session",
            "runId": "cache-clear",
            "hypothesisId": "C1",
            "location": "app.py:clear_cache_api",
            "message": "Before cache.clear_cache call",
            "data": {},
            "timestamp": int(time_module.time() * 1000)
        }
        try:
            with open(str(DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry_before) + '\n')
        except: pass
        # #endregion
        
        success = cache.clear_cache()
        
        # #region agent log
        log_entry_after = {
            "sessionId": "debug-session",
            "runId": "cache-clear",
            "hypothesisId": "C1",
            "location": "app.py:clear_cache_api",
            "message": "After cache.clear_cache call",
            "data": {"success": success},
            "timestamp": int(time_module.time() * 1000)
        }
        try:
            with open(str(DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry_after) + '\n')
        except: pass
        # #endregion
        
        if success:
            logger.info("Cache cleared by user")
            return jsonify({'success': True, 'message': 'Cache cleared successfully'})
        else:
            # #region agent log
            log_entry_failed = {
                "sessionId": "debug-session",
                "runId": "cache-clear",
                "hypothesisId": "C2",
                "location": "app.py:clear_cache_api",
                "message": "clear_cache returned False",
                "data": {},
                "timestamp": int(time_module.time() * 1000)
            }
            try:
                with open(str(DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                    f.write(json.dumps(log_entry_failed) + '\n')
            except: pass
            # #endregion
            return jsonify({'success': False, 'error': 'Failed to clear cache'}), 500
    except Exception as e:
        # #region agent log
        log_entry_exception = {
            "sessionId": "debug-session",
            "runId": "cache-clear",
            "hypothesisId": "C3",
            "location": "app.py:clear_cache_api",
            "message": "Exception in clear_cache_api",
            "data": {"error": str(e), "error_type": type(e).__name__},
            "timestamp": int(time_module.time() * 1000)
        }
        try:
            with open(str(DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry_exception) + '\n')
        except: pass
        # #endregion
        logger.error(f"Error clearing cache: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.template_filter('basename')
def basename_filter(path):
    """Get basename from path."""
    return Path(path).name


@app.template_filter('dirname')
def dirname_filter(path):
    """Get directory name from path."""
    return str(Path(path).parent)


@app.template_filter('datetime_format')
def datetime_format_filter(iso_string):
    """Format ISO datetime string to readable format."""
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(iso_string.replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, AttributeError):
        return iso_string or 'Unknown'


@app.template_filter('file_size')
def file_size_filter(mtime):
    """Format file modification time (placeholder for future file size display)."""
    # For now, just return a placeholder
    # In the future, we could calculate file size from the path
    return '-'


@app.route('/history')
def history():
    """Process history page showing all converted files."""
    try:
        converted_files = cache.get_converted_files_history()
        return render_template('history.html', converted_files=converted_files)
    except Exception as e:
        logger.error(f"Error rendering history: {e}", exc_info=True)
        return f"Error loading history page: {e}", 500


@app.route('/api/history', methods=['GET'])
def get_history_api():
    """Get conversion history as JSON."""
    try:
        converted_files = cache.get_converted_files_history()
        return jsonify({'success': True, 'files': converted_files})
    except Exception as e:
        logger.error(f"Error getting history: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


def run_scan(auto_convert=False):
    """Run scan in background thread.
    
    Args:
        auto_convert: If True, automatically convert all non-compliant files after scan completes.
    """
    global scan_status
    
    try:
        logger.info("Starting scan...")
        logger.info(f"Scan status before scan: running={scan_status['running']}")
        non_compliant, scan_stats = scanner.scan_unc_paths()
        logger.info(f"Scanner returned {len(non_compliant)} non-compliant files")
        logger.info(f"Scan statistics: {scan_stats}")
        
        # Get compliant files count from cache stats
        cache_stats = cache.get_cache_stats()
        compliant_count = cache_stats.get('compliant_files', 0)
        
        # Use actual scan statistics instead of just non-compliant count
        total_files_found = scan_stats.get('total_files_found', 0)
        files_processed = scan_stats.get('files_processed', 0)
        files_compliant = scan_stats.get('files_compliant', 0)
        files_skipped_cache = scan_stats.get('files_skipped_cache', 0)
        
        with scan_lock:
            scan_status['non_compliant_files'] = non_compliant
            scan_status['compliant_files_count'] = compliant_count
            scan_status['total_files'] = total_files_found  # Use actual total files found, not just non-compliant
            scan_status['processed_files'] = files_processed
            scan_status['progress'] = 100
            scan_status['last_scan_time'] = datetime.now().isoformat()
            scan_status['running'] = False
            # Store detailed stats for debugging
            scan_status['scan_stats'] = scan_stats
        
        logger.info(f"Scan complete. Found {len(non_compliant)} non-compliant files.")
        if non_compliant:
            logger.info(f"First few non-compliant files: {[f['path'] for f in non_compliant[:3]]}")
        
        # Auto-convert if requested (e.g., from scheduled scan)
        if auto_convert and non_compliant:
            logger.info(f"Auto-converting {len(non_compliant)} non-compliant files...")
            file_paths = [f['path'] for f in non_compliant]
            thread = threading.Thread(target=run_conversion, args=(file_paths,), daemon=True)
            thread.start()
    
    except Exception as e:
        logger.error(f"Error during scan: {e}", exc_info=True)
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        with scan_lock:
            scan_status['error'] = str(e)
            scan_status['running'] = False


def run_conversion(file_paths):
    """Run conversion in background thread."""
    global scan_status
    
    try:
        total_files = len(file_paths)
        logger.info(f"Starting conversion of {total_files} file(s)...")
        
        with scan_lock:
            scan_status['converting'] = True
            scan_status['conversion_progress'] = 0
            scan_status['conversion_total'] = total_files
            scan_status['conversion_success_count'] = 0
            scan_status['conversion_failed_count'] = 0
            scan_status['conversion_current_file'] = None
            scan_status['error'] = None
        
        results = {
            'success': [],
            'failed': [],
            'errors': {}
        }
        
        # Initialize conversion_results early so frontend can see progress
        with scan_lock:
            scan_status['conversion_results'] = results
        
        for idx, file_path in enumerate(file_paths):
            file_path_obj = Path(file_path)
            
            with scan_lock:
                scan_status['conversion_current_file'] = file_path
                scan_status['conversion_progress'] = idx
                scan_status['conversion_file_progress'] = 0  # Progress for current file (0-100)
                scan_status['progress'] = int((idx / total_files) * 100) if total_files > 0 else 0
            
            logger.info(f"Converting file {idx + 1}/{total_files}: {file_path}")
            
            try:
                # Verify file still exists before attempting conversion
                if not file_path_obj.exists():
                    error_msg = f"File no longer exists: {file_path}"
                    logger.warning(error_msg)
                    results['failed'].append(file_path)
                    results['errors'][file_path] = error_msg
                    with scan_lock:
                        scan_status['conversion_failed_count'] += 1
                    continue
                
                # Pass a callback to update file progress
                def update_file_progress(percent):
                    try:
                        with scan_lock:
                            scan_status['conversion_file_progress'] = percent
                    except Exception:
                        pass  # Ignore errors in progress callback
                
                success, error = transcoder.convert_to_mp4_aac(file_path_obj, create_backup_first=True, progress_callback=update_file_progress)
                
                if success:
                    results['success'].append(file_path)
                    with scan_lock:
                        scan_status['conversion_success_count'] += 1
                        # Update results in real-time (make a copy to ensure it's updated)
                        scan_status['conversion_results'] = {
                            'success': list(results['success']),
                            'failed': list(results['failed']),
                            'errors': dict(results['errors'])
                        }
                    logger.info(f"✓ Successfully converted: {file_path}")
                else:
                    error_msg = error if error else "Unknown error occurred - no error message provided"
                    results['failed'].append(file_path)
                    results['errors'][file_path] = error_msg
                    with scan_lock:
                        scan_status['conversion_failed_count'] += 1
                        # Update results in real-time so frontend can see failures immediately (make a copy)
                        scan_status['conversion_results'] = {
                            'success': list(results['success']),
                            'failed': list(results['failed']),
                            'errors': dict(results['errors'])
                        }
                    logger.error(f"✗ Failed to convert {file_path}")
                    logger.error(f"  Error message: {error_msg}")
                    logger.error(f"  Error type: {type(error).__name__ if error else 'None'}")
                    # Also log to help debug
                    if not error_msg or error_msg == "Unknown error occurred":
                        logger.warning(f"  WARNING: Error message was empty or None for {file_path}")
                        logger.warning(f"  Original error value: {repr(error)}")
            
            except Exception as e:
                # Ensure service continues even if individual conversions fail
                error_msg = f"Exception during conversion: {e}"
                error_trace = traceback.format_exc()
                results['failed'].append(file_path)
                results['errors'][file_path] = error_msg
                with scan_lock:
                    scan_status['conversion_failed_count'] += 1
                logger.error(f"✗ Exception converting {file_path}: {e}")
                logger.error(f"Full traceback:\n{error_trace}")
                # Continue processing other files - don't let one failure stop the entire batch
                continue
        
        with scan_lock:
            scan_status['conversion_results'] = results
            scan_status['converting'] = False
            scan_status['conversion_progress'] = total_files
            scan_status['progress'] = 100
            scan_status['conversion_current_file'] = None
            scan_status['conversion_file_progress'] = 0
            # Mark successful files
            scan_status['converted_files'] = results['success']
        
        logger.info(f"Conversion complete. Success: {len(results['success'])}, Failed: {len(results['failed'])}")
    
    except Exception as e:
        logger.error(f"Error during conversion: {e}", exc_info=True)
        with scan_lock:
            scan_status['error'] = str(e)
            scan_status['converting'] = False
            scan_status['running'] = False


if __name__ == '__main__':
    import sys
    import socket
    import subprocess
    
    sys.stdout.flush()
    sys.stderr.flush()
    
    print("=" * 60)
    print("Jellyfin Audio Conversion Service")
    print("=" * 60)
    print()
    
    try:
        # Load configuration
        print("Loading configuration...", flush=True)
        try:
            cfg = config.get_config()
            print(f"Configuration loaded successfully.", flush=True)
        except Exception as e:
            print(f"ERROR loading configuration: {e}", flush=True)
            import traceback
            traceback.print_exc()
            raise
        
        # Check for FFmpeg/FFprobe
        print("Checking for FFmpeg/FFprobe...", flush=True)
        ffmpeg_path = cfg.get('ffmpeg_path', 'ffmpeg')
        ffprobe_path = cfg.get('ffprobe_path', 'ffprobe')
        
        try:
            result = subprocess.run([ffprobe_path, '-version'], capture_output=True, timeout=5, check=False)
            if result.returncode != 0:
                print(f"WARNING: FFprobe not found at '{ffprobe_path}'", flush=True)
                print("  Please ensure FFmpeg is installed and in PATH, or update config.json", flush=True)
            else:
                print(f"FFprobe found: {ffprobe_path}", flush=True)
        except FileNotFoundError:
            print(f"ERROR: FFprobe not found at '{ffprobe_path}'", flush=True)
            print("  Please install FFmpeg from https://ffmpeg.org/download.html", flush=True)
            print("  Or update the 'ffprobe_path' in config.json", flush=True)
        except Exception as e:
            print(f"WARNING: Could not verify FFprobe: {e}", flush=True)
        
        port = cfg.get('web_port', 8080)
        host = cfg.get('web_host', '0.0.0.0')
        print()
        
        # Check if port is available
        print(f"Checking if port {port} is available...", flush=True)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind((host, port))
            sock.close()
            print(f"Port {port} is available.", flush=True)
        except OSError as e:
            print(f"ERROR: Port {port} is already in use!", flush=True)
            print(f"Please stop the other service or change the port in config.json", flush=True)
            sys.exit(1)
        print()
        
        print(f"Starting web server...", flush=True)
        print(f"  Host: {host}", flush=True)
        print(f"  Port: {port}", flush=True)
        print()
        print("=" * 60)
        print(f"Web interface available at: http://localhost:{port}")
        print("=" * 60)
        print()
        print("Press Ctrl+C to stop the server")
        print()
        sys.stdout.flush()
        
        # Try to open browser automatically
        try:
            import webbrowser
            import time
            # Wait a moment for server to start, then open browser
            def open_browser():
                time.sleep(1.5)
                webbrowser.open(f"http://localhost:{port}")
            
            browser_thread = threading.Thread(target=open_browser, daemon=True)
            browser_thread.start()
            print("Opening web browser...")
        except Exception as e:
            logger.warning(f"Could not open browser automatically: {e}")
        
        # Setup and start schedule checking
        setup_schedule()
        
        logger.info(f"Starting web server on {host}:{port}")
        app.run(host=host, port=port, debug=False, use_reloader=False)
        
    except KeyboardInterrupt:
        print("\n\nShutting down server...")
        sys.exit(0)
    except Exception as e:
        print(f"\nERROR: Failed to start application: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

