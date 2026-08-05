"""WSGI entry point for PythonAnywhere (and any other WSGI host).

On PythonAnywhere, point the "WSGI configuration file" to import `application`
from this module (see DEPLOY.md for the exact snippet to paste in).
"""
import sys
import os

# Make sure this directory is on the path so `app` and `fair_engine` import
# correctly regardless of the working directory the WSGI server starts in.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app as application  # noqa: E402
