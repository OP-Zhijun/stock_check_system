#!/usr/bin/env python3
"""
PythonAnywhere Deployment Helper for Nano Lab Stock Check System

This script:
1. Creates a deployment-ready zip file
2. Generates the WSGI config file for PythonAnywhere
3. Prints step-by-step instructions

Usage:
    python3 deploy_pythonanywhere.py
"""

import os
import zipfile
import shutil
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_NAME = 'stock_check_system'

# Files to include in deployment
DEPLOY_FILES = [
    'app.py',
    'templates/base.html',
    'templates/login.html',
    'templates/register.html',
    'templates/dashboard.html',
    'templates/history.html',
    'templates/orders.html',
    'templates/admin.html',
    'templates/admin_items.html',
]

# Files to exclude
EXCLUDE = ['__pycache__', '.pyc', 'app_v1_backup.py', 'stock_check.db', 'deploy_pythonanywhere.py']


def create_wsgi_file(username):
    """Generate the WSGI configuration file for PythonAnywhere."""
    content = f"""# WSGI configuration for PythonAnywhere
# This file tells PythonAnywhere how to run your Flask app.

import sys
import os

# Add your project directory to the sys.path
project_home = '/home/{username}/{PROJECT_NAME}'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# Set the working directory
os.chdir(project_home)

# Import your Flask app
from app import app as application, init_db

# Initialize the database (creates tables + admin user + 34 items if needed)
init_db()
"""
    wsgi_path = os.path.join(SCRIPT_DIR, 'wsgi.py')
    with open(wsgi_path, 'w') as f:
        f.write(content)
    print(f'  Created: wsgi.py')
    return wsgi_path


def create_zip():
    """Create a deployment zip file."""
    zip_path = os.path.join(SCRIPT_DIR, f'{PROJECT_NAME}.zip')
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for filepath in DEPLOY_FILES:
            full_path = os.path.join(SCRIPT_DIR, filepath)
            if os.path.exists(full_path):
                arcname = os.path.join(PROJECT_NAME, filepath)
                zf.write(full_path, arcname)
                print(f'  Added: {filepath}')
            else:
                print(f'  WARNING: Missing file: {filepath}')

        # Add wsgi.py at root of zip (will be moved to correct location)
        wsgi_path = os.path.join(SCRIPT_DIR, 'wsgi.py')
        if os.path.exists(wsgi_path):
            zf.write(wsgi_path, os.path.join(PROJECT_NAME, 'wsgi.py'))
            print(f'  Added: wsgi.py')

    size_kb = os.path.getsize(zip_path) / 1024
    print(f'\n  Zip created: {zip_path} ({size_kb:.1f} KB)')
    return zip_path


def print_instructions(username):
    """Print step-by-step PythonAnywhere deployment instructions."""
    print(f"""
{'='*60}
  PYTHONANYWHERE DEPLOYMENT INSTRUCTIONS
{'='*60}

Your zip file is ready. Follow these steps:

STEP 1: Create a PythonAnywhere Account
  - Go to https://www.pythonanywhere.com
  - Click "Start running Python online" → Sign up (free)
  - Choose username: {username}
  - Your site will be: https://{username}.pythonanywhere.com

STEP 2: Upload the Zip File
  - Log in to PythonAnywhere
  - Go to "Files" tab
  - Click "Upload a file" button
  - Upload: {PROJECT_NAME}.zip
  - It will be at /home/{username}/{PROJECT_NAME}.zip

STEP 3: Extract the Zip File
  - Go to "Consoles" tab → click "Bash"
  - Run these commands:

    cd ~
    unzip {PROJECT_NAME}.zip
    cd {PROJECT_NAME}
    python3 -c "from app import init_db; init_db()"

  This creates the database with 34 items and the admin account.

STEP 4: Create the Web App
  - Go to "Web" tab
  - Click "Add a new web app"
  - Choose "Manual configuration" (NOT Flask)
  - Choose Python 3.10 (or latest available)

STEP 5: Configure WSGI
  - On the Web tab, find "Code" section
  - Click on the WSGI configuration file link
    (something like /var/www/{username}_pythonanywhere_com_wsgi.py)
  - DELETE all existing content
  - PASTE this:

import sys
import os
project_home = '/home/{username}/{PROJECT_NAME}'
if project_home not in sys.path:
    sys.path.insert(0, project_home)
os.chdir(project_home)
from app import app as application, init_db
init_db()

  - Click "Save"

STEP 6: Set Source Code Path
  - On the Web tab, under "Code" section:
  - Source code: /home/{username}/{PROJECT_NAME}
  - Working directory: /home/{username}/{PROJECT_NAME}

STEP 7: Reload & Test
  - Click the green "Reload" button at the top of the Web tab
  - Visit: https://{username}.pythonanywhere.com
  - Login: admin / admin123

DONE! Share this URL with your 11 lab members:
  https://{username}.pythonanywhere.com

{'='*60}
  ACCOUNTS
{'='*60}
  Admin login: admin / admin123
  Members: Register at /register → admin approves

{'='*60}
  MAINTENANCE
{'='*60}
  - To update code: Files tab → edit directly or re-upload
  - To backup DB: Files tab → download stock_check.db
  - To check errors: Web tab → Error log / Server log
  - Free tier: site sleeps after 3 months, click "Reload" to renew
  - Free tier limit: 1 web app, 512MB disk, 100 seconds CPU/day
    (more than enough for 11 lab members doing stock checks)
""")


def main():
    print(f'\n{"="*60}')
    print(f'  Nano Lab Stock Check — PythonAnywhere Deployer')
    print(f'{"="*60}\n')

    # Ask for PythonAnywhere username
    if len(sys.argv) > 1:
        username = sys.argv[1]
    else:
        username = input('Enter your PythonAnywhere username (or press Enter for "nanolab"): ').strip()
        if not username:
            username = 'nanolab'

    print(f'\n  Username: {username}')
    print(f'  Site URL: https://{username}.pythonanywhere.com\n')

    print('Step 1: Generating WSGI config...')
    create_wsgi_file(username)

    print('\nStep 2: Creating deployment zip...')
    zip_path = create_zip()

    print_instructions(username)

    print(f'  Zip file location:')
    print(f'  {zip_path}\n')


if __name__ == '__main__':
    main()
