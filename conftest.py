"""
Pytest configuration - ensures project root is in sys.path.

This allows tests to import packages like 'core', 'scheduler', 'strategies', etc.
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
