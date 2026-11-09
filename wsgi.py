"""WSGI entry point for PythonAnywhere deployment."""
import os
import sys

# Add project directory to path
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(PROJECT_DIR, ".env"))
except Exception:
    pass

from app import app

application = app
