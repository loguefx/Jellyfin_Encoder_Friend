"""Minimal test to verify executable works."""
import sys
import os
from pathlib import Path

# Write to file immediately - no imports
try:
    test_log = Path("test_minimal.log")
    with open(test_log, 'w', encoding='utf-8') as f:
        f.write("=" * 60 + "\n")
        f.write("Minimal Test Executable\n")
        f.write("=" * 60 + "\n")
        f.write(f"Python: {sys.version}\n")
        f.write(f"Executable: {sys.executable}\n")
        f.write(f"Frozen: {getattr(sys, 'frozen', False)}\n")
        f.write(f"Args: {sys.argv}\n")
        f.write(f"CWD: {os.getcwd()}\n")
        f.write("SUCCESS: Executable can run!\n")
        f.flush()
except Exception as e:
    try:
        with open("test_minimal_error.txt", 'w') as f:
            f.write(f"Error: {e}\n")
    except:
        pass

print("Minimal test executable works!")
print(f"Check test_minimal.log for details")
input("Press Enter to exit...")









