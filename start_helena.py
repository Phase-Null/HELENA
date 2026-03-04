#!/usr/bin/env python3
"""
HELENA Startup Script
"""
import sys
import os

# Add HELENA to path
sys.path.insert(0, r"C:\Users\franc\OneDrive\Desktop")

# Import HELENA
from helena_desktop.main_window import main

if __name__ == "__main__":
    # Set environment variables
    os.environ["HELENA_HOME"] = r"C:\Users\franc\OneDrive\Desktop\HELENA"
    os.environ["HELENA_OPERATOR"] = "Sean Francis"
    
    # Start HELENA
    main()
