"""
Windows Service wrapper for Jellyfin Audio Service.
Handles service installation, start, stop, and scheduled scanning.
"""

# CRITICAL: Write to crash log using ONLY built-in functions - no imports yet
# This must work even if Python can't import anything
_crash_log_path = None
try:
    # Use only built-ins to write crash log
    import sys
    _frozen = getattr(sys, 'frozen', False)
    if _frozen:
        import os
        _exe = sys.executable
        _exe_dir = os.path.dirname(_exe)
        _crash_log_path = os.path.join(_exe_dir, "service_crash.log")
    else:
        import os
        _file_dir = os.path.dirname(os.path.abspath(__file__))
        _crash_log_path = os.path.join(_file_dir, "service_crash.log")
except:
    _crash_log_path = "service_crash.log"

def _write_crash(msg):
    """Write to crash log using only built-ins."""
    # Try multiple locations to ensure we capture logs even if one fails
    log_paths = []
    if _crash_log_path:
        log_paths.append(_crash_log_path)
    
    # Add fallback locations
    try:
        import os
        import tempfile
        # Try Windows temp directory as fallback
        temp_dir = tempfile.gettempdir()
        log_paths.append(os.path.join(temp_dir, "JellyfinAudioService_crash.log"))
    except:
        pass
    
    # Try to write to at least one location
    written = False
    for log_path in log_paths:
        if not log_path:
            continue
        try:
            with open(log_path, 'a', encoding='utf-8') as f:
                import datetime
                f.write(f"{datetime.datetime.now().isoformat()}: {msg}\n")
                f.flush()
                written = True
                break
        except:
            try:
                # Fallback: write without timestamp
                with open(log_path, 'a', encoding='utf-8') as f:
                    f.write(f"{msg}\n")
                    f.flush()
                    written = True
                    break
            except:
                continue
    
    # If all file writes failed, try Windows Event Log as last resort
    if not written:
        try:
            import win32evtlog
            import win32evtlogutil
            win32evtlogutil.ReportEvent(
                win32evtlogutil.EVENTLOG_INFORMATION_TYPE,
                0,
                1,
                None,
                [f"JellyfinAudioService: {msg}"]
            )
        except:
            pass

# Write initial crash log entry
try:
    import sys
    import os
    _write_crash("=" * 60)
    _write_crash("Service module loading started")
    _write_crash(f"Python: {sys.version}")
    _write_crash(f"Executable: {sys.executable}")
    _write_crash(f"Frozen: {getattr(sys, 'frozen', False)}")
    _write_crash(f"Current dir: {os.getcwd()}")
    _write_crash(f"Arguments: {sys.argv}")
except Exception as e:
    try:
        with open("service_crash_fatal.log", 'a') as f:
            f.write(f"Fatal error during crash log setup: {e}\n")
    except:
        pass
    # Don't raise - continue to try imports

import time
import logging
import logging.handlers
import threading

try:
    _write_crash("Importing win32 modules...")
    import win32serviceutil
    import win32service
    import win32event
    import servicemanager
    import win32api  # Needed for CloseHandle
    _write_crash("[OK] win32 modules imported")
except ImportError as e:
    _write_crash(f"[FAIL] win32 import error: {e}")
    try:
        print("pywin32 is required for Windows service functionality.")
        print("Install it with: pip install pywin32")
    except:
        pass
    sys.exit(1)
except Exception as e:
    _write_crash(f"[FAIL] win32 import exception: {e}")
    import traceback
    _write_crash(traceback.format_exc())
    raise

# Defer config, scanner, transcoder, schedule until after SERVICE_RUNNING (in SvcDoRun).
# Loading them at module import causes Error 1053 on boot when the service doesn't
# respond to the start request within the default 30-second timeout.

# Configure logging
# Try to use executable directory, fallback to script directory
try:
    from pathlib import Path
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        exe_dir = Path(sys.executable).parent
    else:
        # Running as script
        exe_dir = Path(__file__).parent
except Exception:
    try:
        from pathlib import Path
        exe_dir = Path.cwd()
    except:
        import os
        exe_dir = Path(os.getcwd())

log_file = exe_dir / "service.log"
try:
    # Use RotatingFileHandler to prevent unbounded log growth (32M+ lines).
    # Rotate at 10MB, keep 5 backup files (max ~50MB total).
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding='utf-8'
    )
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[file_handler, logging.StreamHandler()]
    )
except Exception as e:
    # Fallback if logging setup fails
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
logger = logging.getLogger(__name__)


class JellyfinAudioService(win32serviceutil.ServiceFramework):
    """Windows Service for Jellyfin Audio Conversion."""
    
    _svc_name_ = "JellyfinAudioService"
    _svc_display_name_ = "Jellyfin Audio Conversion Service"
    _svc_description_ = "Monitors video libraries and converts files to AAC-compliant format"
    
    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.scan_thread = None
        self.web_thread = None
        self.web_server = None  # Werkzeug server instance for graceful shutdown
        self.running = False
    
    def SvcStop(self):
        """Stop the service."""
        _write_crash("=" * 60)
        _write_crash("SvcStop() called - Service stopping")
        logger.info("Stopping service...")
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        
        # Set running flag and signal stop event
        self.running = False
        win32event.SetEvent(self.stop_event)
        _write_crash("[OK] Stop event signaled, running=False")
        
        # Stop scheduled tasks (schedule is imported in SvcDoRun; may not exist if stop before run)
        try:
            import schedule
            schedule.clear()
            logger.info("Scheduled tasks cleared")
            _write_crash("[OK] Scheduled tasks cleared")
        except Exception as e:
            logger.error(f"Error clearing schedule: {e}")
            _write_crash(f"[FAIL] Error clearing schedule: {e}")
        
        # Shutdown web server gracefully
        if self.web_server:
            try:
                logger.info("Shutting down web server...")
                _write_crash("Shutting down web server...")
                self.web_server.shutdown()
                logger.info("Web server shutdown complete")
                _write_crash("[OK] Web server shutdown complete")
            except Exception as e:
                logger.error(f"Error shutting down web server: {e}", exc_info=True)
                _write_crash(f"[FAIL] Error shutting down web server: {e}")
        
        # Wait for threads to finish
        if self.scan_thread and self.scan_thread.is_alive():
            logger.info("Waiting for scan thread to finish...")
            self.scan_thread.join(timeout=10)
            if self.scan_thread.is_alive():
                logger.warning("Scan thread did not finish within timeout")
            else:
                logger.info("Scan thread finished")
        
        if self.web_thread and self.web_thread.is_alive():
            logger.info("Waiting for web thread to finish...")
            self.web_thread.join(timeout=10)
            if self.web_thread.is_alive():
                logger.warning("Web thread did not finish within timeout")
            else:
                logger.info("Web thread finished")
        
        logger.info("Service stopped")
        _write_crash("[OK] Service stopped")
    
    def SvcDoRun(self):
        """Main service execution."""
        # CRITICAL: Report service as running IMMEDIATELY to prevent timeout
        # Windows requires service to respond within 30 seconds
        # Write to crash log immediately
        try:
            _write_crash("=" * 60)
            _write_crash("SvcDoRun() called - Service starting")
            _write_crash(f"sys.executable: {sys.executable}")
            _write_crash(f"sys.frozen: {getattr(sys, 'frozen', False)}")
            _write_crash(f"Current dir: {os.getcwd()}")
        except:
            pass
        
        # CRITICAL: Report SERVICE_START_PENDING first, then SERVICE_RUNNING
        # This must happen BEFORE any other initialization to prevent timeout
        try:
            _write_crash("Reporting SERVICE_START_PENDING...")
            self.ReportServiceStatus(win32service.SERVICE_START_PENDING)
            _write_crash("[OK] SERVICE_START_PENDING reported")
        except Exception as e:
            _write_crash(f"[FAIL] Failed to report SERVICE_START_PENDING: {e}")
            import traceback
            _write_crash(traceback.format_exc())
        
        try:
            servicemanager.LogMsg(
                servicemanager.EVENTLOG_INFORMATION_TYPE,
                servicemanager.PYS_SERVICE_STARTED,
                (self._svc_name_, '')
            )
            logger.info("Service reported as started to Windows")
            _write_crash("[OK] Service logged as started to Windows")
        except Exception as e:
            logger.error(f"Failed to report service started: {e}", exc_info=True)
            _write_crash(f"[FAIL] Failed to log service started: {e}")
            import traceback
            _write_crash(traceback.format_exc())
        
        # Report SERVICE_RUNNING immediately after logging (before any heavy imports)
        try:
            _write_crash("Reporting SERVICE_RUNNING...")
            self.ReportServiceStatus(win32service.SERVICE_RUNNING)
            _write_crash("[OK] SERVICE_RUNNING reported - Service is now active")
        except Exception as e:
            _write_crash(f"[FAIL] Failed to report SERVICE_RUNNING: {e}")
            import traceback
            _write_crash(traceback.format_exc())
        
        # Now safe to load application modules (avoids Error 1053 startup timeout)
        try:
            _write_crash("Importing application modules (deferred)...")
            import config
            import scanner
            import transcoder
            import schedule
            _write_crash("[OK] Application modules imported")
        except Exception as e:
            _write_crash(f"[FAIL] Deferred import error: {e}")
            import traceback
            _write_crash(traceback.format_exc())
            logger.error(f"Failed to import application modules: {e}", exc_info=True)
            servicemanager.LogErrorMsg(f"Service import error: {e}")
            return

        # Set working directory immediately
        try:
            if getattr(sys, 'frozen', False):
                exe_dir = Path(sys.executable).parent
            else:
                exe_dir = Path(__file__).parent
            os.chdir(str(exe_dir))
            logger.info(f"Service working directory: {exe_dir}")
        except Exception as e:
            logger.warning(f"Failed to set working directory: {e}")
        
        logger.info("Service starting...")
        self.running = True
        
        # Start initialization in background to avoid blocking
        def initialize_service():
            """Initialize service components in background."""
            try:
                logger.info("Initializing service components...")
                
                # Start web server in background thread
                logger.info("Starting web server thread...")
                self.web_thread = threading.Thread(target=self.run_web_server, daemon=True)
                self.web_thread.start()
                logger.info("Web server thread started")
                
                # Setup scheduled scans
                logger.info("Setting up scheduled scans...")
                self.setup_schedule()
                logger.info("Scheduled scans configured")
                
                logger.info("Service initialization complete")
            except Exception as e:
                logger.error(f"Error during service initialization: {e}", exc_info=True)
                servicemanager.LogErrorMsg(f"Service initialization error: {e}")
        
        # Start initialization in background thread (non-blocking)
        try:
            init_thread = threading.Thread(target=initialize_service, daemon=True)
            init_thread.start()
            logger.info("Initialization thread started")
        except Exception as e:
            logger.error(f"Failed to start initialization thread: {e}", exc_info=True)
        
        # Run main service loop immediately (this keeps service alive and responsive)
        try:
            logger.info("Entering main service loop...")
            self.main_loop()
        except Exception as e:
            logger.error(f"Service error in main loop: {e}", exc_info=True)
            servicemanager.LogErrorMsg(f"Service error: {e}")
        finally:
            servicemanager.LogMsg(
                servicemanager.EVENTLOG_INFORMATION_TYPE,
                servicemanager.PYS_SERVICE_STOPPED,
                (self._svc_name_, '')
            )
    
    def run_web_server(self):
        """Run Flask web server in background thread."""
        try:
            from app import app
            from werkzeug.serving import make_server
            cfg = config.get_config()
            port = cfg.get('web_port', 8080)
            host = cfg.get('web_host', '0.0.0.0')
            
            logger.info(f"Starting web server on {host}:{port}")
            self.web_server = make_server(host, port, app, threaded=True)
            logger.info(f"Web server created, starting...")
            
            # Run server in a way that can be stopped
            def serve_forever():
                try:
                    self.web_server.serve_forever()
                except Exception as e:
                    logger.error(f"Web server serve_forever error: {e}", exc_info=True)
            
            # Start server in a thread that can be interrupted
            server_thread = threading.Thread(target=serve_forever, daemon=True)
            server_thread.start()
            logger.info(f"Web server thread started")
            
            # Wait for stop signal
            while self.running:
                if win32event.WaitForSingleObject(self.stop_event, 1000) == win32event.WAIT_OBJECT_0:
                    logger.info("Stop event signaled, shutting down web server...")
                    break
            
            # Shutdown the server gracefully
            logger.info("Shutting down web server...")
            self.web_server.shutdown()
            logger.info("Web server shut down")
            
        except Exception as e:
            logger.error(f"Web server error: {e}", exc_info=True)
    
    def setup_schedule(self):
        """Setup scheduled scans based on configuration."""
        schedule_config = config.get_scan_schedule()
        
        if not schedule_config.get('enabled', True):
            logger.info("Scheduled scans are disabled")
            return
        
        interval_hours = schedule_config.get('interval_hours', 24)
        scan_time = schedule_config.get('time', '02:00')
        
        # Clear any existing scheduled tasks
        schedule.clear()
        
        # Schedule based on interval_hours
        if interval_hours < 24:
            # Schedule scans every N hours
            schedule.every(interval_hours).hours.do(self.run_scheduled_scan)
            logger.info(f"Scheduled scans: Every {interval_hours} hour(s)")
        else:
            # Schedule daily scan at specified time
            schedule.every().day.at(scan_time).do(self.run_scheduled_scan)
            logger.info(f"Scheduled scans: Daily at {scan_time}")
    
    def run_scheduled_scan(self):
        """Run a scheduled scan and convert non-compliant files."""
        logger.info("Starting scheduled scan...")
        
        try:
            # Scan for non-compliant files
            non_compliant, scan_stats = scanner.scan_unc_paths()
            
            logger.info(f"Scan complete: {scan_stats.get('total_files_found', 0)} total files found, {len(non_compliant)} non-compliant")
            if not non_compliant:
                logger.info("No non-compliant files found")
                return
            
            logger.info(f"Found {len(non_compliant)} non-compliant file(s)")
            
            # Convert all non-compliant files one by one with error handling
            # This ensures one failure doesn't stop the entire batch
            success_count = 0
            failed_count = 0
            
            for file_info in non_compliant:
                file_path = file_info['path']
                file_path_obj = Path(file_path)
                
                try:
                    # Verify file still exists
                    if not file_path_obj.exists():
                        logger.warning(f"File no longer exists, skipping: {file_path}")
                        failed_count += 1
                        continue
                    
                    success, error = transcoder.convert_to_mp4_aac(file_path_obj, create_backup_first=True)
                    
                    if success:
                        success_count += 1
                        logger.debug(f"✓ Successfully converted: {file_path}")
                    else:
                        failed_count += 1
                        error_msg = error or "Unknown error"
                        logger.error(f"✗ Failed to convert {file_path}: {error_msg}")
                
                except Exception as e:
                    # Catch any exceptions to ensure service continues
                    failed_count += 1
                    logger.error(f"✗ Exception converting {file_path}: {e}", exc_info=True)
                    # Continue with next file - don't let one failure stop the service
            
            logger.info(f"Conversion complete. Success: {success_count}, Failed: {failed_count}")
        
        except Exception as e:
            # Log error but don't let it crash the service
            logger.error(f"Error during scheduled scan: {e}", exc_info=True)
            logger.warning("Service will continue running despite scan error")
    
    def main_loop(self):
        """Main service loop - runs scheduled tasks."""
        logger.info("Service running. Waiting for scheduled tasks...")
        
        # Use shorter sleep intervals to keep service responsive to stop requests
        while self.running:
            try:
                # Run pending scheduled tasks
                schedule.run_pending()
                
                # Check if service should stop (with 1 second timeout to keep responsive)
                if win32event.WaitForSingleObject(self.stop_event, 1000) == win32event.WAIT_OBJECT_0:  # 1 second timeout
                    logger.info("Stop event signaled, exiting main loop")
                    break
                
                # Small sleep to prevent CPU spinning but keep responsive
                time.sleep(1)  # Check every second instead of every minute
            
            except Exception as e:
                logger.error(f"Error in main loop: {e}", exc_info=True)
                time.sleep(5)  # Wait 5 seconds on error before retrying


def main():
    """Main entry point for service installation/management."""
    # Import os at function level to avoid variable shadowing issues
    import os
    from datetime import datetime
    
    # Write error log to file for debugging
    error_log = None
    startup_log = None
    try:
        if getattr(sys, 'frozen', False):
            exe_dir = Path(sys.executable).parent
        else:
            exe_dir = Path(__file__).parent
        error_log = exe_dir / "service_error.log"
        startup_log = exe_dir / "service_startup.log"
    except Exception as e:
        error_log = Path("service_error.log")
        startup_log = Path("service_startup.log")
    
    def log_error(msg):
        """Log error to file and console."""
        try:
            with open(error_log, 'a', encoding='utf-8') as f:
                f.write(f"{datetime.now().isoformat()}: {msg}\n")
        except:
            pass
        try:
            print(msg, file=sys.stderr)
        except:
            pass
    
    def log_startup(msg):
        """Log startup info to file."""
        try:
            with open(startup_log, 'a', encoding='utf-8') as f:
                f.write(f"{datetime.now().isoformat()}: {msg}\n")
        except:
            pass
    
    # Log startup information
    try:
        log_startup("=" * 60)
        log_startup("Service main() called")
        log_startup(f"Python version: {sys.version}")
        log_startup(f"Executable: {sys.executable}")
        log_startup(f"Frozen: {getattr(sys, 'frozen', False)}")
        log_startup(f"Current directory: {os.getcwd()}")
        log_startup(f"Arguments: {sys.argv}")
        log_startup(f"Argument count: {len(sys.argv)}")
    except Exception as e:
        log_error(f"Failed to log startup info: {e}")
    
    if len(sys.argv) == 1:
        # Check if running as service or double-clicked
        _write_crash("=" * 60)
        _write_crash("No command-line arguments - checking if running as service")
        _write_crash(f"sys.argv: {sys.argv}")
        _write_crash(f"sys.executable: {sys.executable}")
        _write_crash(f"sys.frozen: {getattr(sys, 'frozen', False)}")
        log_startup("No command-line arguments - checking if running as service")
        try:
            # Try to initialize as service
            _write_crash("Attempting to initialize servicemanager...")
            log_startup("Attempting to initialize servicemanager...")
            servicemanager.Initialize()
            _write_crash("[OK] servicemanager.Initialize() completed")
            log_startup("[OK] servicemanager.Initialize() completed")
            
            _write_crash("Preparing to host service...")
            log_startup("Preparing to host service...")
            servicemanager.PrepareToHostSingle(JellyfinAudioService)
            _write_crash("[OK] servicemanager.PrepareToHostSingle() completed")
            log_startup("[OK] servicemanager.PrepareToHostSingle() completed")
            
            _write_crash("Starting service control dispatcher...")
            log_startup("Starting service control dispatcher...")
            servicemanager.StartServiceCtrlDispatcher()
            _write_crash("[OK] Service control dispatcher started")
            log_startup("Service control dispatcher started")
        except Exception as e:
            # Not running as service - log error and show message
            error_msg = f"Service initialization failed: {type(e).__name__}: {e}"
            log_error(error_msg)
            import traceback
            log_error(traceback.format_exc())
            
            try:
                import win32gui
                import win32con
                message = (
                    "Jellyfin Audio Service\n\n"
                    "This executable is designed to run as a Windows Service.\n\n"
                    "To install the service, open Command Prompt as Administrator and run:\n"
                    "  JellyfinAudioService.exe install\n\n"
                    "To start the service, run:\n"
                    "  JellyfinAudioService.exe start\n\n"
                    "Or use the Windows Services Manager (services.msc).\n\n"
                    "To access the web interface, use:\n"
                    "  JellyfinAudioServiceUI.exe\n\n"
                    f"Error logged to: {error_log}\n"
                    f"Error: {str(e)[:200]}"
                )
                win32gui.MessageBox(
                    0,
                    message,
                    "Jellyfin Audio Service",
                    win32con.MB_OK | win32con.MB_ICONINFORMATION
                )
            except Exception as msg_error:
                # Fallback if win32gui not available or fails
                print("=" * 60)
                print("Jellyfin Audio Service")
                print("=" * 60)
                print("\nThis executable is designed to run as a Windows Service.")
                print("\n" + "=" * 60)
                print("PERMISSION ERROR: Administrator privileges required!")
                print("=" * 60)
                print("\nTo install the service, you MUST run PowerShell or Command Prompt as Administrator:")
                print("  1. Right-click on PowerShell or Command Prompt")
                print("  2. Select 'Run as Administrator'")
                print("  3. Navigate to: C:\\Program Files\\JellyfinAudioService")
                print("  4. Run: .\\JellyfinAudioService.exe install")
                print("\nAlternatively, you can use the Windows Services Manager (services.msc)")
                print("=" * 60)
                print("\nTo start the service, run:")
                print("  JellyfinAudioService.exe start")
                print("\nOr use the Windows Services Manager (services.msc).")
                print("\nTo access the web interface, use:")
                print("  JellyfinAudioServiceUI.exe")
                print(f"\nError logged to: {error_log}")
                print(f"Error: {e}")
                import traceback
                traceback.print_exc()
                input("\nPress Enter to exit...")
    else:
        # Service management commands
        # Normalize command to lowercase (Windows service commands are case-sensitive)
        if len(sys.argv) > 1:
            sys.argv[1] = sys.argv[1].lower()
        
        cmd = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "none"
        _write_crash(f"Command-line arguments provided: {sys.argv[1:]}")
        _write_crash(f"Executing service command: {cmd}")
        log_startup(f"Command-line arguments provided: {sys.argv[1:]}")
        try:
            # Log the command being executed
            log_startup(f"Executing service command: {cmd}")
            log_error(f"Executing service command: {cmd}")
            
            # Test imports before calling HandleCommandLine
            _write_crash("Verifying imports before HandleCommandLine...")
            log_startup("Verifying imports before HandleCommandLine...")
            try:
                import win32serviceutil
                _write_crash("[OK] win32serviceutil imported")
                log_startup("[OK] win32serviceutil imported")
            except Exception as e:
                _write_crash(f"[FAIL] win32serviceutil import: {e}")
                log_startup(f"[FAIL] win32serviceutil import: {e}")
                raise
            
            try:
                # JellyfinAudioService is already imported at module level
                _write_crash("[OK] JellyfinAudioService available")
                log_startup("[OK] JellyfinAudioService available")
            except Exception as e:
                _write_crash(f"[FAIL] JellyfinAudioService check: {e}")
                log_startup(f"[FAIL] JellyfinAudioService check: {e}")
                raise
            
            _write_crash("Calling win32serviceutil.HandleCommandLine...")
            log_startup("Calling win32serviceutil.HandleCommandLine...")
            
            # If running as frozen executable, we need to manually configure the service path
            is_frozen = getattr(sys, 'frozen', False)
            is_install = len(sys.argv) > 1 and sys.argv[1] == 'install'
            
            _write_crash(f"is_frozen: {is_frozen}, is_install: {is_install}, sys.argv: {sys.argv}")
            log_startup(f"is_frozen: {is_frozen}, is_install: {is_install}")
            
            if is_frozen and is_install:
                exe_path = sys.executable
                _write_crash(f"Installing service with frozen executable: {exe_path}")
                log_startup(f"Installing service with frozen executable: {exe_path}")
                
                # First install the service (will use pythonservice.exe initially)
                _write_crash("Calling HandleCommandLine to install service...")
                win32serviceutil.HandleCommandLine(JellyfinAudioService)
                _write_crash("[OK] HandleCommandLine completed")
                
                # Get current logged-in user for service account configuration
                try:
                    current_user = win32api.GetUserName()
                    _write_crash(f"Current logged-in user: {current_user}")
                    log_startup(f"Current logged-in user: {current_user}")
                except Exception as user_err:
                    _write_crash(f"Could not get current user: {user_err}")
                    current_user = None
                
                # Then manually update the service to use our executable
                _write_crash("Updating service binary path...")
                scm = None
                service_handle = None
                try:
                    _write_crash("Opening Service Control Manager...")
                    # #region agent log
                    import json
                    import os
                    debug_log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.cursor', 'debug.log')
                    try:
                        with open(debug_log_path, 'a', encoding='utf-8') as f:
                            f.write(json.dumps({
                                'sessionId': 'debug-session',
                                'runId': 'install-attempt',
                                'hypothesisId': 'A',
                                'location': 'service.py:686',
                                'message': 'Attempting to open Service Control Manager',
                                'data': {'is_frozen': is_frozen, 'is_install': is_install, 'exe_path': exe_path},
                                'timestamp': int(time.time() * 1000)
                            }) + '\n')
                    except: pass
                    # #endregion
                    scm = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_ALL_ACCESS)
                    _write_crash(f"[OK] Opened Service Control Manager, handle: {scm}")
                    
                    _write_crash(f"Opening service: {JellyfinAudioService._svc_name_}")
                    service_handle = win32service.OpenService(
                        scm, 
                        JellyfinAudioService._svc_name_, 
                        win32service.SERVICE_ALL_ACCESS
                    )
                    _write_crash(f"[OK] Opened service handle: {service_handle}")
                    
                    # Query current service config to preserve existing values
                    _write_crash("Querying current service configuration...")
                    current_config = win32service.QueryServiceConfig(service_handle)
                    _write_crash(f"Current config tuple length: {len(current_config)}")
                    _write_crash(f"Current config: {current_config}")
                    for i, val in enumerate(current_config):
                        _write_crash(f"  [{i}] type={type(val).__name__}, value={val}")
                    
                    # QueryServiceConfig returns:
                    # (dwServiceType, dwStartType, dwErrorControl, lpBinaryPathName, lpLoadOrderGroup, 
                    #  lpdwTagId, lpDependencies, lpServiceStartName, lpDisplayName)
                    # Note: lpDependencies is a list/tuple of strings
                    
                    # Extract values with proper type handling
                    service_type = current_config[0]  # int
                    start_type = current_config[1]  # int
                    error_control = current_config[2]  # int
                    old_binary_path = current_config[3]  # str
                    load_order_group = current_config[4] if len(current_config) > 4 else ""  # str or None
                    tag_id = current_config[5] if len(current_config) > 5 else None  # int or None
                    dependencies = current_config[6] if len(current_config) > 6 else []  # list/tuple
                    service_start_name = current_config[7] if len(current_config) > 7 else ""  # str or None
                    display_name = current_config[8] if len(current_config) > 8 else ""  # str or None
                    
                    _write_crash(f"Extracted values:")
                    _write_crash(f"  service_type={service_type} (type: {type(service_type).__name__})")
                    _write_crash(f"  start_type={start_type} (type: {type(start_type).__name__})")
                    _write_crash(f"  error_control={error_control} (type: {type(error_control).__name__})")
                    _write_crash(f"  load_order_group={load_order_group} (type: {type(load_order_group).__name__})")
                    _write_crash(f"  tag_id={tag_id} (type: {type(tag_id).__name__})")
                    _write_crash(f"  dependencies={dependencies} (type: {type(dependencies).__name__})")
                    _write_crash(f"  service_start_name={service_start_name} (type: {type(service_start_name).__name__})")
                    _write_crash(f"  display_name={display_name} (type: {type(display_name).__name__})")
                    
                    # Convert dependencies list to string format if needed
                    if isinstance(dependencies, (list, tuple)):
                        dependencies_str = "\0".join(dependencies) + "\0" if dependencies else ""
                    else:
                        dependencies_str = dependencies if dependencies else ""
                    
                    # Update service configuration to use our executable
                    # ChangeServiceConfig signature:
                    # ChangeServiceConfig(hService, dwServiceType, dwStartType, dwErrorControl, 
                    #                     lpBinaryPathName, lpLoadOrderGroup, lpdwTagId, 
                    #                     lpDependencies, lpServiceStartName, lpPassword, lpDisplayName)
                    _write_crash(f"Calling ChangeServiceConfig with path: {exe_path}")
                    _write_crash(f"Parameters: serviceType={service_type}, startType={start_type}, errorControl={error_control}")
                    
                    # Use current logged-in user for service account (if available)
                    # This allows the service to access UNC paths like standalone mode
                    service_account = service_start_name or ""
                    if current_user and not service_start_name:
                        # Configure to run under current user account for network access
                        # Format: .\username for local account, or DOMAIN\username for domain
                        try:
                            # Try to get domain/username format (SAM format: DOMAIN\username)
                            try:
                                # NameSamCompatible constant value is 2
                                domain_user = win32api.GetUserNameEx(2)  # NameSamCompatible
                                if domain_user:
                                    service_account = domain_user
                                    _write_crash(f"Using domain format: {service_account}")
                                    log_startup(f"Service will be configured to run under: {service_account}")
                            except Exception as domain_err:
                                # Fallback to local format
                                service_account = f".\\{current_user}"
                                _write_crash(f"Using local format: {service_account} (domain format failed: {domain_err})")
                                log_startup(f"Service will be configured to run under: {service_account}")
                        except Exception as account_err:
                            _write_crash(f"Could not format service account: {account_err}")
                            service_account = service_start_name or ""
                    elif current_user:
                        _write_crash(f"Service already configured with account: {service_start_name}")
                    else:
                        _write_crash("Could not determine current user - service will use default account (SYSTEM)")
                        log_startup("WARNING: Service will run under SYSTEM account (no network access)")
                        log_startup("         Run configure_service_account.bat after installation to fix this")
                    
                    win32service.ChangeServiceConfig(
                        service_handle,
                        service_type,  # service type - int
                        start_type,  # start type - int
                        error_control,  # error control - int
                        exe_path,  # binary path name - THIS IS THE KEY CHANGE
                        load_order_group or "",  # load order group - str
                        tag_id,  # tag id - int or None
                        dependencies_str,  # dependencies - str (null-separated)
                        service_account,  # service start name - use current user if available
                        "",  # password - empty string (user must set via services.msc or configure script)
                        display_name or ""  # display name - str
                    )
                    _write_crash(f"[OK] Service configured to use: {exe_path}")
                    log_startup(f"[OK] Service configured to use: {exe_path}")
                    
                    # Verify the change
                    _write_crash("Querying service config to verify...")
                    service_config = win32service.QueryServiceConfig(service_handle)
                    _write_crash(f"Service config tuple length: {len(service_config)}")
                    _write_crash(f"Verified service path: {service_config[4]}")
                    log_startup(f"Verified service path: {service_config[4]}")
                except Exception as config_err:
                    _write_crash(f"[FAIL] Service path update error: {config_err}")
                    import traceback
                    _write_crash(traceback.format_exc())
                    log_startup(f"[FAIL] Service path update error: {config_err}")
                    log_error(f"Failed to update service path: {config_err}")
                    
                    # #region agent log
                    import json
                    debug_log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)) if not getattr(sys, 'frozen', False) else os.path.dirname(sys.executable), '.cursor', 'debug.log')
                    try:
                        error_str = str(config_err)
                        error_type = type(config_err).__name__
                        is_access_denied = 'Access is denied' in error_str or '5' in error_str or 'winerror' in str(config_err).lower()
                        with open(debug_log_path, 'a', encoding='utf-8') as f:
                            f.write(json.dumps({
                                'sessionId': 'debug-session',
                                'runId': 'install-attempt',
                                'hypothesisId': 'B',
                                'location': 'service.py:767',
                                'message': 'Service path update failed',
                                'data': {
                                    'error_type': error_type,
                                    'error_message': error_str,
                                    'is_access_denied': is_access_denied,
                                    'traceback': traceback.format_exc()[:500]
                                },
                                'timestamp': int(time.time() * 1000)
                            }) + '\n')
                    except: pass
                    # #endregion
                    
                    # Check if this is an access denied error
                    error_str = str(config_err)
                    if 'Access is denied' in error_str or (hasattr(config_err, 'winerror') and config_err.winerror == 5):
                        print("\n" + "=" * 60, file=sys.stderr)
                        print("PERMISSION ERROR: Administrator privileges required!", file=sys.stderr)
                        print("=" * 60, file=sys.stderr)
                        print("\nThe service installation requires administrator privileges.", file=sys.stderr)
                        print("\nTo fix this:", file=sys.stderr)
                        print("  1. Right-click on PowerShell or Command Prompt", file=sys.stderr)
                        print("  2. Select 'Run as Administrator'", file=sys.stderr)
                        print(f"  3. Navigate to: {os.path.dirname(exe_path)}", file=sys.stderr)
                        print(f"  4. Run: .\\{os.path.basename(exe_path)} install", file=sys.stderr)
                        print("\n" + "=" * 60, file=sys.stderr)
                    # Continue anyway - service is installed, just might use wrong exe
                finally:
                    # Clean up handles
                    if service_handle:
                        try:
                            win32service.CloseServiceHandle(service_handle)
                            _write_crash("[OK] Closed service handle")
                        except Exception as e:
                            _write_crash(f"[WARNING] Error closing service handle: {e}")
                    if scm:
                        try:
                            win32api.CloseHandle(scm)
                            _write_crash("[OK] Closed SCM handle")
                        except Exception as e:
                            _write_crash(f"[WARNING] Error closing SCM handle: {e}")
            else:
                _write_crash("Using standard HandleCommandLine (not frozen or not install)")
                
                # For non-frozen installs, also try to configure service account
                if is_install:
                    try:
                        current_user = win32api.GetUserName()
                        _write_crash(f"Current logged-in user: {current_user}")
                        log_startup(f"Current logged-in user: {current_user}")
                        log_startup("NOTE: After installation, run configure_service_account.bat")
                        log_startup("      to configure the service to use your user account for UNC access")
                    except Exception as user_err:
                        _write_crash(f"Could not get current user: {user_err}")
                
                # Call HandleCommandLine which handles install, start, stop, remove, etc.
                win32serviceutil.HandleCommandLine(JellyfinAudioService)
            
            _write_crash(f"Service command '{cmd}' completed successfully")
            log_startup(f"Service command '{cmd}' completed successfully")
            log_error(f"Service command '{cmd}' completed successfully")
        except SystemExit as e:
            # HandleCommandLine may call sys.exit() - this is normal
            log_error(f"Service command completed with exit code: {e.code}")
            sys.exit(e.code if e.code is not None else 0)
        except Exception as e:
            error_msg = f"Service command failed: {type(e).__name__}: {e}"
            log_error(error_msg)
            import traceback
            log_error(traceback.format_exc())
            
            # #region agent log
            import json
            debug_log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)) if not getattr(sys, 'frozen', False) else os.path.dirname(sys.executable), '.cursor', 'debug.log')
            try:
                error_str = str(e)
                error_type = type(e).__name__
                is_access_denied = 'Access is denied' in error_str or '5' in error_str or (hasattr(e, 'winerror') and e.winerror == 5)
                with open(debug_log_path, 'a', encoding='utf-8') as f:
                    f.write(json.dumps({
                        'sessionId': 'debug-session',
                        'runId': 'install-attempt',
                        'hypothesisId': 'C',
                        'location': 'service.py:800',
                        'message': 'Service command exception caught',
                        'data': {
                            'error_type': error_type,
                            'error_message': error_str,
                            'is_access_denied': is_access_denied,
                            'command': cmd if 'cmd' in locals() else 'unknown',
                            'traceback': traceback.format_exc()[:500]
                        },
                        'timestamp': int(time.time() * 1000)
                    }) + '\n')
            except: pass
            # #endregion
            
            print(f"ERROR: {error_msg}", file=sys.stderr)
            print(f"Error details logged to: {error_log}", file=sys.stderr)
            
            # Check if this is an access denied error
            error_str = str(e)
            is_access_denied = 'Access is denied' in error_str or (hasattr(e, 'winerror') and e.winerror == 5)
            if is_access_denied:
                print("\n" + "=" * 60, file=sys.stderr)
                print("PERMISSION ERROR: Administrator privileges required!", file=sys.stderr)
                print("=" * 60, file=sys.stderr)
                print("\nThe service installation requires administrator privileges.", file=sys.stderr)
                print("\nTo fix this:", file=sys.stderr)
                print("  1. Right-click on PowerShell or Command Prompt", file=sys.stderr)
                print("  2. Select 'Run as Administrator'", file=sys.stderr)
                try:
                    is_frozen_check = getattr(sys, 'frozen', False)
                    if is_frozen_check:
                        exe_path = sys.executable
                        print(f"  3. Navigate to: {os.path.dirname(exe_path)}", file=sys.stderr)
                        print(f"  4. Run: .\\{os.path.basename(exe_path)} install", file=sys.stderr)
                    else:
                        print("  3. Navigate to the service directory", file=sys.stderr)
                        print("  4. Run: python service.py install", file=sys.stderr)
                except:
                    print("  3. Navigate to the service directory", file=sys.stderr)
                    print("  4. Run the install command again", file=sys.stderr)
                print("\n" + "=" * 60, file=sys.stderr)
            
            # Try to show message box if possible
            try:
                import win32gui
                import win32con
                message = f"Service Command Failed\n\n{error_msg}"
                if is_access_denied:
                    message += "\n\nPERMISSION ERROR: Administrator privileges required!\n\n"
                    message += "Please run PowerShell or Command Prompt as Administrator\n"
                    message += "and try again."
                message += f"\n\nError logged to:\n{error_log}"
                win32gui.MessageBox(
                    0,
                    message,
                    "Jellyfin Audio Service - Error",
                    win32con.MB_OK | win32con.MB_ICONERROR
                )
            except:
                pass
            sys.exit(1)


if __name__ == '__main__':
    try:
        _write_crash("=" * 60)
        _write_crash("Starting main() function")
        _write_crash(f"sys.argv: {sys.argv}")
        _write_crash(f"Argument count: {len(sys.argv)}")
        main()
        _write_crash("main() completed successfully")
    except SystemExit as e:
        _write_crash(f"SystemExit with code: {e.code}")
        # Don't re-raise SystemExit - let it propagate normally
        raise
    except KeyboardInterrupt:
        _write_crash("KeyboardInterrupt - user cancelled")
        sys.exit(0)
    except Exception as e:
        _write_crash(f"FATAL ERROR in main(): {type(e).__name__}: {e}")
        import traceback
        _write_crash(traceback.format_exc())
        
        # Try to write to a simple text file as backup
        try:
            with open("service_fatal_error.txt", 'w', encoding='utf-8') as f:
                import datetime
                f.write(f"Fatal Error in Jellyfin Audio Service\n")
                f.write(f"{'=' * 60}\n")
                f.write(f"Time: {datetime.datetime.now().isoformat()}\n")
                f.write(f"Error: {type(e).__name__}: {e}\n")
                f.write(f"\nTraceback:\n{traceback.format_exc()}\n")
                f.write(f"\nCheck crash log: {_crash_log_path}\n")
        except:
            pass
        
        try:
            # Try to show error to user
            import win32gui
            import win32con
            error_msg = (
                f"Fatal Error in Jellyfin Audio Service\n\n"
                f"Error: {type(e).__name__}\n"
                f"Message: {str(e)[:300]}\n\n"
                f"Crash log: {_crash_log_path}\n"
                f"Error file: service_fatal_error.txt"
            )
            win32gui.MessageBox(
                0,
                error_msg,
                "Jellyfin Audio Service - Fatal Error",
                win32con.MB_OK | win32con.MB_ICONERROR
            )
        except Exception as msg_err:
            _write_crash(f"Failed to show message box: {msg_err}")
            # Fallback: try to print to console
            try:
                print(f"FATAL ERROR: {e}", file=sys.stderr)
                print(f"Check: {_crash_log_path}", file=sys.stderr)
            except:
                pass
        
        sys.exit(1)




