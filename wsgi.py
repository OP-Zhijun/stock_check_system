# WSGI configuration for PythonAnywhere
# This file tells PythonAnywhere how to run your Flask app.

import sys
import os
from pathlib import Path

# Add your project directory to the sys.path
project_home = Path(__file__).parent
if str(project_home) not in sys.path:
    sys.path.insert(0, str(project_home))

# Set the working directory
os.chdir(project_home)

# Import your Flask app
from app import app as application, init_db

# Initialize the database (creates tables + admin user + 34 items if needed)
init_db()
