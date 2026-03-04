#!/usr/bin/env python3
"""
HELENA Startup Script
Automatically detects its own location so it works on any platform.
"""
import sys
import os
from pathlib import Path

# Resolve HELENA root to the directory containing this script
HELENA_ROOT = Path(__file__).resolve().parent

# Ensure HELENA packages are importable
sys.path.insert(0, str(HELENA_ROOT))

# Import HELENA
from helena_desktop.main_window import main

if __name__ == "__main__":
    # Set environment variables (override with env vars if already set)
    os.environ.setdefault("HELENA_HOME", str(HELENA_ROOT))
    os.environ.setdefault("HELENA_OPERATOR", "Sean Francis")

    # Start HELENA
    main()
