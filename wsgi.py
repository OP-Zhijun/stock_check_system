# WSGI configuration for PythonAnywhere
# This file tells PythonAnywhere how to run your Flask app.

import sys
import os

# Add your project directory to the sys.path
project_home = '/home/nanolab/stock_check_system'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# Set the working directory
os.chdir(project_home)

# Import your Flask app
from app import app as application, init_db

# Initialize the database (creates tables + admin user + 34 items if needed)
init_db()
