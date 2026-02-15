"""
Console wrapper for service.py - ensures console window stays open and shows all output.
This is the entry point when running as executable to ensure visibility.
"""
import sys
import os

# CRITICAL: Write crash log IMMEDIATELY using only built-ins (before any imports that might fail)
_crash_log_path = None
try:
    _frozen = getattr(sys, 'frozen', False)
    if _frozen:
        _exe = sys.executable
        _exe_dir = os.path.dirname(_exe)
        _crash_log_path = os.path.join(_exe_dir, "service_console_crash.log")
    else:
        _file_dir = os.path.dirname(os.path.abspath(__file__))
        _crash_log_path = os.path.join(_file_dir, "service_console_crash.log")
except:
    _crash_log_path = "service_console_crash.log"

def _write_crash(msg):
    """Write to crash log using only built-ins."""
    try:
        with open(_crash_log_path, 'a', encoding='utf-8') as f:
            import datetime
            f.write(f"{datetime.datetime.now().isoformat()}: {msg}\n")
            f.flush()
    except:
        try:
            with open(_crash_log_path, 'a', encoding='utf-8') as f:
                f.write(f"{msg}\n")
        except:
            pass

# Write initial crash log entry IMMEDIATELY
try:
    _write_crash("=" * 60)
    _write_crash("service_console.py STARTING")
    _write_crash(f"Python: {sys.version}")
    _write_crash(f"Executable: {sys.executable}")
    _write_crash(f"Frozen: {getattr(sys, 'frozen', False)}")
    _write_crash(f"Current dir: {os.getcwd()}")
    _write_crash(f"Arguments: {sys.argv}")
    _write_crash(f"Argument count: {len(sys.argv)}")
except:
    pass

# Import urllib first to ensure it's available for pathlib
try:
    import urllib
except ImportError:
    pass
from pathlib import Path

# Force console output (but don't fail if console doesn't exist)
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except (OSError, AttributeError):
    # Console not available (normal when running as Windows service)
    _write_crash("[INFO] Console not available - running as service")
except:
    pass

# Write immediate startup log
startup_log = None
try:
    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).parent
    else:
        exe_dir = Path(__file__).parent
    startup_log = exe_dir / "service_console.log"
    _write_crash(f"Startup log path: {startup_log}")
except Exception as e:
    startup_log = Path("service_console.log")
    _write_crash(f"Failed to set startup log path: {e}")

def log(msg):
    """Log to file and console (if available)."""
    try:
        with open(startup_log, 'a', encoding='utf-8') as f:
            import datetime
            f.write(f"{datetime.datetime.now().isoformat()}: {msg}\n")
            f.flush()
    except:
        pass
    # Try to write to console, but don't fail if it doesn't exist (e.g., when running as service)
    try:
        print(msg, flush=True)
    except (OSError, AttributeError):
        # Console not available (normal when running as Windows service)
        pass
    except:
        pass

def main():
    """Main entry point - ensures proper module structure for cx_Freeze."""
    log("=" * 60)
    log("Service Console Wrapper Started")
    log(f"Python: {sys.version}")
    log(f"Executable: {sys.executable}")
    log(f"Frozen: {getattr(sys, 'frozen', False)}")
    log(f"CWD: {os.getcwd()}")
    log(f"Args: {sys.argv}")
    log("=" * 60)
    _write_crash("About to import service module")

    try:
        log("Importing service module...")
        _write_crash("Importing service module...")
        # #region agent log
        import json
        import time as time_module
        debug_log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)) if not getattr(sys, 'frozen', False) else os.path.dirname(sys.executable), '.cursor', 'debug.log')
        try:
            os.makedirs(os.path.dirname(debug_log_path), exist_ok=True)
            with open(debug_log_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    'sessionId': 'debug-session',
                    'runId': 'service-console-startup',
                    'hypothesisId': 'A',
                    'location': 'service_console.py:main',
                    'message': 'About to import service module',
                    'data': {
                        'frozen': getattr(sys, 'frozen', False),
                        'executable': sys.executable,
                        'argv': sys.argv,
                        'sys_path': sys.path[:3]  # First 3 entries
                    },
                    'timestamp': int(time_module.time() * 1000)
                }) + '\n')
        except: pass
        # #endregion
        
        from service import main as service_main
        log("[OK] Service module imported")
        _write_crash("[OK] Service module imported")
        
        # #region agent log
        try:
            with open(debug_log_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    'sessionId': 'debug-session',
                    'runId': 'service-console-startup',
                    'hypothesisId': 'A',
                    'location': 'service_console.py:main',
                    'message': 'Service module imported successfully',
                    'data': {'main_function': str(service_main)},
                    'timestamp': int(time_module.time() * 1000)
                }) + '\n')
        except: pass
        # #endregion
        
        log("Calling service.main()...")
        log("")
        _write_crash("Calling service.main()...")
        service_main()
        log("")
        log("[OK] service.main() completed")
        _write_crash("[OK] service.main() completed")
        
    except SystemExit as e:
        _write_crash(f"SystemExit: {e.code}")
        log(f"SystemExit: {e.code}")
        sys.exit(e.code if e.code is not None else 0)
        
    except KeyboardInterrupt:
        _write_crash("KeyboardInterrupt - cancelled by user")
        log("KeyboardInterrupt - cancelled by user")
        sys.exit(0)
        
    except Exception as e:
        import traceback
        error_tb = traceback.format_exc()
        _write_crash("=" * 60)
        _write_crash("FATAL ERROR")
        _write_crash("=" * 60)
        _write_crash(f"Error Type: {type(e).__name__}")
        _write_crash(f"Error Message: {e}")
        _write_crash("Traceback:")
        _write_crash(error_tb)
        _write_crash("=" * 60)
        
        # #region agent log
        try:
            with open(debug_log_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    'sessionId': 'debug-session',
                    'runId': 'service-console-startup',
                    'hypothesisId': 'B',
                    'location': 'service_console.py:main',
                    'message': 'Exception caught in main',
                    'data': {
                        'error_type': type(e).__name__,
                        'error_message': str(e),
                        'traceback': error_tb[:1000]
                    },
                    'timestamp': int(time_module.time() * 1000)
                }) + '\n')
        except: pass
        # #endregion
        
        log("")
        log("=" * 60)
        log("FATAL ERROR")
        log("=" * 60)
        log(f"Error Type: {type(e).__name__}")
        log(f"Error Message: {e}")
        log("")
        log("Traceback:")
        log(error_tb)
        log("=" * 60)
        
        # Try to show message box
        try:
            import win32gui
            import win32con
            win32gui.MessageBox(
                0,
                f"Fatal Error\n\n{type(e).__name__}: {e}\n\nCheck: {startup_log}",
                "Jellyfin Audio Service - Error",
                win32con.MB_OK | win32con.MB_ICONERROR
            )
        except:
            pass
        
        # Keep window open
        log("")
        log("Press Enter to exit...")
        try:
            input()
        except:
            pass
        
        sys.exit(1)


if __name__ == '__main__':
    main()

