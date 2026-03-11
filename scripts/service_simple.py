"""Simplified service entry point to test if executable works."""
import sys
import os
from pathlib import Path

# Write crash log immediately - before ANY imports
crash_log_path = None
try:
    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).parent
    else:
        exe_dir = Path(__file__).parent
    crash_log_path = exe_dir / "service_crash.log"
except:
    crash_log_path = Path("service_crash.log")

def write_crash(msg):
    try:
        with open(crash_log_path, 'a', encoding='utf-8') as f:
            f.write(f"{msg}\n")
            f.flush()
    except:
        pass

write_crash("=" * 60)
write_crash("SERVICE_SIMPLE.PY STARTED")
write_crash(f"Python: {sys.version}")
write_crash(f"Executable: {sys.executable}")
write_crash(f"Frozen: {getattr(sys, 'frozen', False)}")
write_crash(f"CWD: {os.getcwd()}")
write_crash(f"Args: {sys.argv}")

try:
    write_crash("Importing sys, os, pathlib...")
    import sys as _sys
    import os as _os
    from pathlib import Path as _Path
    write_crash("[OK] Basic imports")
except Exception as e:
    write_crash(f"[FAIL] Basic imports: {e}")
    import traceback
    write_crash(traceback.format_exc())
    raise

try:
    write_crash("Importing datetime...")
    from datetime import datetime
    write_crash("[OK] datetime")
except Exception as e:
    write_crash(f"[FAIL] datetime: {e}")
    import traceback
    write_crash(traceback.format_exc())
    raise

try:
    write_crash("Importing win32 modules...")
    import win32serviceutil
    import win32service
    import win32event
    import servicemanager
    write_crash("[OK] win32 modules")
except Exception as e:
    write_crash(f"[FAIL] win32 modules: {e}")
    import traceback
    write_crash(traceback.format_exc())
    raise

try:
    write_crash("Importing application modules...")
    import schedule
    write_crash("[OK] schedule")
    import config
    write_crash("[OK] config")
    import scanner
    write_crash("[OK] scanner")
    import transcoder
    write_crash("[OK] transcoder")
except Exception as e:
    write_crash(f"[FAIL] Application modules: {e}")
    import traceback
    write_crash(traceback.format_exc())
    raise

try:
    write_crash("Importing service module...")
    from service import JellyfinAudioService, main
    write_crash("[OK] Service module imported")
except Exception as e:
    write_crash(f"[FAIL] Service module: {e}")
    import traceback
    write_crash(traceback.format_exc())
    raise

write_crash("Calling main()...")
try:
    main()
    write_crash("main() completed successfully")
except SystemExit as e:
    write_crash(f"SystemExit: {e.code}")
    raise
except Exception as e:
    write_crash(f"Exception in main(): {type(e).__name__}: {e}")
    import traceback
    write_crash(traceback.format_exc())
    raise









