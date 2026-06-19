#!/usr/bin/env python3
"""SITA — Self-Improving Trading Agent. Entry point."""
import sys
import os

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sita.__main__ import main

if __name__ == "__main__":
    main()
