"""Test script to diagnose app startup issues."""

import sys
print("Python version:", sys.version)
print("Starting imports...")

try:
    print("Importing config...")
    import config
    print("Config imported successfully")
    
    print("Loading config...")
    cfg = config.get_config()
    print("Config loaded:", cfg)
    
    print("Importing Flask...")
    from flask import Flask
    print("Flask imported successfully")
    
    print("Creating Flask app...")
    app = Flask(__name__)
    print("Flask app created")
    
    print("Importing other modules...")
    import scanner
    import transcoder
    print("All modules imported successfully")
    
    print("\nAll checks passed! The app should start normally.")
    print("Try running: python app.py")
    
except Exception as e:
    print(f"\nERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)













