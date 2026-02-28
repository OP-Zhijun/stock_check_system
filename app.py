#!/usr/bin/env python3
"""
Nano Lab Stock Check System V4
A shared web-based stock check system for lab members.
V4: 12 corrections — teams config, 9999=infinity, number-only input, notes modal,
    required fields, legend top, KST timestamps, monthly DB, CSV BOM, column split,
    email system, duty alerts.
"""

import os
import re
import csv
import io
import json
import sqlite3
import secrets as _secrets_mod
from datetime import datetime, date, timedelta, timezone
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, g, jsonify, Response
)
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

# Persistent random secret key
_secret_key_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.secret_key')
if os.path.exists(_secret_key_file):
    with open(_secret_key_file, 'r') as f:
        app.secret_key = f.read().strip()
else:
    app.secret_key = _secrets_mod.token_hex(32)
    with open(_secret_key_file, 'w') as f:
        f.write(app.secret_key)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'stock_check.db')
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ============================================================
# Item 5: KST timezone
# ============================================================
KST = timezone(timedelta(hours=9))

def now_kst():
    """Return current time in KST as formatted string."""
    return datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')

def today_kst():
    """Return today's date in KST."""
    return datetime.now(KST).date()

# ============================================================
# Item 12: Teams config from JSON
# ============================================================
TEAMS_CONFIG_PATH = os.path.join(BASE_DIR, 'teams_config.json')

def load_teams_config():
    """Load teams configuration from teams_config.json."""
    with open(TEAMS_CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

_teams_config = load_teams_config()

def get_groups():
    """Return list of group names from config."""
    return [t['name'] for t in _teams_config['teams']]

def get_teams_display():
    """Return list of dicts with key and name for template display."""
    return [{'key': t['key'], 'name': t['name']} for t in _teams_config['teams']]

def get_team_key_for_group(group_name):
    """Return team key (A-E) for a group name."""
    for t in _teams_config['teams']:
        if t['name'] == group_name:
            return t['key']
    return '?'

GROUPS = get_groups()

# --- Pre-loaded items ---
INITIAL_ITEMS = [
    # (stock_place, item_name, minimum, category, sort_order)
    ('4\u00b0C refrigerator', 'DMEM(LM001-05)', '6 bottles', 'Common', 1),
    ('4\u00b0C refrigerator', 'RPMI(sh30255.01)', '6 bottles', 'Common', 2),
    ('Cell room Drawer', 'Microscope slide', '4 cases', 'Common', 3),
    ('Cell room Drawer', 'cover glass', '4 cases', 'Common', 4),
    ('Cell room Drawer', '100mm dish(20101)', '1 box(full)', 'Common', 5),
    ('Cell room Drawer', '150mm dish(20150)', '1 box(full)', 'Common', 6),
    ('Cell room Drawer', 'T75(70075)', '1 box(full)', 'Common', 7),
    ('Cell room Drawer', 'T25(70025)', '1 box(full)', 'Common', 8),
    ('Cell room Drawer', '6well(30006)', '1 box(full)', 'Common', 9),
    ('Cell room Drawer', '12well(30012)', '1 box(full)', 'Common', 10),
    ('Cell room Drawer', '24well(30024)', '1 box(full)', 'Common', 11),
    ('Cell room Drawer', '96well(30096)', '1 box(full)', 'Common', 12),
    ('Cell room Drawer', 'cryovials(50pieces)', '5 bags', 'Common', 13),
    ('5th floor Drawer', 'conical tube 15ml', '1 box(full)', 'Common', 14),
    ('5th floor Drawer', 'conical tube 50ml', '1 box(full)', 'Common', 15),
    ('5th floor Drawer', 'gloves(XS)', '4 boxes', 'Common', 16),
    ('5th floor Drawer', 'gloves(S)', '4 boxes', 'Common', 17),
    ('5th floor Drawer', 'gloves(M)', '4 boxes', 'Common', 18),
    ('5th floor Drawer', 'gloves(L)', '4 boxes', 'Common', 19),
    ('5th floor Drawer', 'Reservoir Channel 1', '1 box(full)', 'Common', 20),
    ('5th floor Drawer', 'Reservoir Channel 2', '1 box(full)', 'Common', 21),
    ('5th floor Drawer', 'eptube', '4 boxes(full)', 'Common', 22),
    ('5th floor Drawer', 'pipets 5ml(91005)', '4 boxes(full)', 'Common', 23),
    ('5th floor Drawer', 'pipets 10ml(91010)', '4 boxes(full)', 'Common', 24),
    ('5th floor Drawer', 'pipets 25ml(91025)', '4 boxes(full)', 'Common', 25),
    ('5th floor Drawer', 'DPBS(LB001-02)', '4 bottles(full)', 'Common', 26),
    ('5th floor Drawer', 'kim tech', '1 box(full)', 'Common', 27),
    ('5th floor Drawer', 'paper towel', '1 box(full)', 'Common', 28),
    ('5th floor Drawer', 'FBS', '3 bottles', 'Common', 29),
    ('5th floor Drawer', 'Anti-Anti', '3 bottles', 'Common', 30),
    ('5th floor Drawer', 'Trypsin', '3 bottles', 'Common', 31),
    ('Dr.Lee', 'Tip 1000uL', '2 bags', 'Dr.Lee', 32),
    ('Dr.Lee', 'Tip 200uL', '2 bags', 'Dr.Lee', 33),
    ('Dr.Lee', 'Tip 10uL', '2 bags', 'Dr.Lee', 34),
]


# ============================================================
# Database
# ============================================================

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA journal_mode=WAL')
        g.db.execute('PRAGMA foreign_keys=ON')
    return g.db


@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()


# ============================================================
# Item 6: Monthly check tables helpers
# ============================================================

def get_checks_table(check_date_str):
    """Return monthly table name for a given check date, e.g. 'checks_2026_02'."""
    try:
        d = date.fromisoformat(check_date_str) if isinstance(check_date_str, str) else check_date_str
        return f"checks_{d.year}_{d.month:02d}"
    except (ValueError, AttributeError):
        return "checks_2026_02"


def validate_checks_table_name(name):
    """Ensure table name matches expected pattern to prevent SQL injection."""
    if not re.match(r'^checks_\d{4}_\d{2}$', name):
        raise ValueError(f"Invalid checks table name: {name}")
    return name


def ensure_checks_table(db, table_name):
    """Create monthly checks table if it doesn't exist."""
    validate_checks_table_name(table_name)
    db.execute(f'''
        CREATE TABLE IF NOT EXISTS "{table_name}" (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            group_name TEXT NOT NULL,
            checked_by TEXT NOT NULL,
            quantity TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'unknown',
            note TEXT NOT NULL DEFAULT '',
            check_date TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
        )
    ''')
    db.execute(f'CREATE INDEX IF NOT EXISTS "idx_{table_name}_item_group" ON "{table_name}"(item_id, group_name)')
    db.execute(f'CREATE INDEX IF NOT EXISTS "idx_{table_name}_date" ON "{table_name}"(check_date)')


def get_all_checks_tables(db):
    """Return list of all checks_YYYY_MM table names in the database."""
    rows = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'checks_%'").fetchall()
    tables = []
    for row in rows:
        name = row['name']
        if re.match(r'^checks_\d{4}_\d{2}$', name):
            tables.append(name)
    return sorted(tables)


# ============================================================
# Item 1: Parse minimum into value + unit
# ============================================================

def parse_minimum(text):
    """Parse '6 bottles' into (6.0, 'bottles'). Returns (None, text) if no number."""
    if not text:
        return None, ''
    text = text.strip()
    m = re.match(r'(\d+(?:\.\d+)?)\s*(.*)', text)
    if m:
        return float(m.group(1)), m.group(2).strip()
    return None, text


# ============================================================
# init_db with migrations
# ============================================================

def init_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('PRAGMA foreign_keys=ON')

    db.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL DEFAULT '',
            group_name TEXT NOT NULL DEFAULT '',
            role TEXT NOT NULL DEFAULT 'member',
            approved INTEGER NOT NULL DEFAULT 0,
            email TEXT NOT NULL DEFAULT '',
            email_verified INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_place TEXT NOT NULL,
            item_name TEXT NOT NULL,
            minimum TEXT NOT NULL DEFAULT '',
            min_value REAL,
            min_unit TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL DEFAULT 'Common',
            sort_order INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS order_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            requested_by TEXT NOT NULL,
            requested_by_group TEXT NOT NULL DEFAULT '',
            quantity_needed TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            note TEXT NOT NULL DEFAULT '',
            resolved_by TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT '',
            resolved_at TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS email_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            email TEXT NOT NULL DEFAULT '',
            token TEXT NOT NULL,
            token_type TEXT NOT NULL DEFAULT 'verify',
            created_at TEXT NOT NULL DEFAULT '',
            used INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
    ''')

    # ---- Schema migrations ----
    # Add email columns to users if missing
    cols = [c['name'] for c in db.execute("PRAGMA table_info(users)").fetchall()]
    if 'email' not in cols:
        db.execute("ALTER TABLE users ADD COLUMN email TEXT NOT NULL DEFAULT ''")
    if 'email_verified' not in cols:
        db.execute("ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 0")

    # Add min_value/min_unit columns to items if missing
    item_cols = [c['name'] for c in db.execute("PRAGMA table_info(items)").fetchall()]
    if 'min_value' not in item_cols:
        db.execute("ALTER TABLE items ADD COLUMN min_value REAL")
    if 'min_unit' not in item_cols:
        db.execute("ALTER TABLE items ADD COLUMN min_unit TEXT NOT NULL DEFAULT ''")

    # Add ordered_by/ordered_at columns to order_requests if missing (V4 pipeline)
    or_cols = [c['name'] for c in db.execute("PRAGMA table_info(order_requests)").fetchall()]
    if 'ordered_by' not in or_cols:
        db.execute("ALTER TABLE order_requests ADD COLUMN ordered_by TEXT NOT NULL DEFAULT ''")
    if 'ordered_at' not in or_cols:
        db.execute("ALTER TABLE order_requests ADD COLUMN ordered_at TEXT NOT NULL DEFAULT ''")

    # Populate min_value/min_unit from minimum text where not set
    items_to_parse = db.execute("SELECT id, minimum FROM items WHERE min_value IS NULL AND minimum != ''").fetchall()
    for item in items_to_parse:
        val, unit = parse_minimum(item['minimum'])
        if val is not None:
            db.execute("UPDATE items SET min_value = ?, min_unit = ? WHERE id = ?", (val, unit, item['id']))

    # ---- Item 12: Migrate old group names ----
    name_migrations = {
        'Dr.yoo/dahee': 'Dr.Yoo/Dahee',
        'junhyun/thuan': 'Junhyun/Thuan',
        'Dr.azary/nattha': 'Dr.Arjaree/Nattha',
    }
    for old_name, new_name in name_migrations.items():
        db.execute("UPDATE users SET group_name = ? WHERE group_name = ?", (new_name, old_name))
        # Migrate checks in all monthly tables
        for tbl in get_all_checks_tables(db):
            db.execute(f'UPDATE "{tbl}" SET group_name = ? WHERE group_name = ?', (new_name, old_name))
        db.execute("UPDATE order_requests SET requested_by_group = ? WHERE requested_by_group = ?", (new_name, old_name))

    # ---- Item 6: Migrate legacy checks to monthly tables ----
    # Check if old 'checks' table exists (not monthly format)
    old_checks = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='checks'").fetchone()
    if old_checks:
        # Get distinct months from old checks
        months = db.execute("SELECT DISTINCT substr(check_date, 1, 7) as ym FROM checks WHERE check_date != ''").fetchall()
        for month_row in months:
            ym = month_row['ym']  # e.g. '2026-02'
            if not ym or len(ym) < 7:
                continue
            table_name = f"checks_{ym.replace('-', '_')}"
            ensure_checks_table(db, table_name)
            # Copy data
            db.execute(f'''
                INSERT INTO "{table_name}" (id, item_id, group_name, checked_by, quantity, status, note, check_date, created_at)
                SELECT id, item_id, group_name, checked_by, quantity, status, note, check_date,
                       COALESCE(created_at, '') FROM checks WHERE substr(check_date, 1, 7) = ?
            ''', (ym,))
        # Migrate group names in newly created monthly tables
        for old_name, new_name in name_migrations.items():
            for tbl in get_all_checks_tables(db):
                db.execute(f'UPDATE "{tbl}" SET group_name = ? WHERE group_name = ?', (new_name, old_name))
        # Rename old table
        db.execute("ALTER TABLE checks RENAME TO checks_legacy")

    # Create admin if not exists
    existing = db.execute('SELECT id FROM users WHERE username = ?', ('admin',)).fetchone()
    if not existing:
        db.execute(
            "INSERT INTO users (username, password_hash, display_name, group_name, role, approved, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ('admin', generate_password_hash('admin123'), 'Admin', 'Dr.Lee/Zhijun', 'admin', 1, now_kst())
        )

    # Load initial items if table is empty
    count = db.execute('SELECT COUNT(*) FROM items').fetchone()[0]
    if count == 0:
        for item in INITIAL_ITEMS:
            val, unit = parse_minimum(item[2])
            db.execute(
                'INSERT INTO items (stock_place, item_name, minimum, min_value, min_unit, category, sort_order) VALUES (?, ?, ?, ?, ?, ?, ?)',
                (item[0], item[1], item[2], val, unit, item[3], item[4])
            )

    db.commit()
    db.close()


# ============================================================
# Auth helpers
# ============================================================

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in first.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in first.', 'warning')
            return redirect(url_for('login'))
        if session.get('role') != 'admin':
            flash('Admin access required.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated


def parse_number(text):
    """Extract leading number from quantity text like '3 bottles' -> 3.0"""
    if not text:
        return None
    text = str(text).strip()
    m = re.match(r'(\d+(?:\.\d+)?)', text)
    if m:
        return float(m.group(1))
    return None


def is_valid_number(text):
    """Check if text is a valid number (integer or float, >= 0)."""
    if not text:
        return False
    text = str(text).strip()
    try:
        val = float(text)
        return val >= 0
    except ValueError:
        return False


def compute_status(quantity_val, min_value):
    """Compare quantity number to minimum value and return status: ok / low / empty / unknown.
    Item A: 9999 = infinity, always OK."""
    if quantity_val is None:
        return 'unknown'
    try:
        qty = float(quantity_val)
    except (ValueError, TypeError):
        return 'unknown'

    # Item A: 9999 = infinity → always OK
    if qty == 9999:
        return 'ok'

    if qty == 0:
        return 'empty'
    if min_value is not None:
        try:
            min_val = float(min_value)
        except (ValueError, TypeError):
            return 'unknown'
        if qty < min_val:
            return 'low'
        return 'ok'
    return 'unknown'


# ============================================================
# Rotation schedule (Item 12: from config)
# ============================================================

def get_rotation_info(for_date=None):
    """Return rotation info from teams_config.json.
    Returns (duty_group_name, check_date, next_check_date, next_group_name, duty_team_key, next_team_key)."""
    config = _teams_config
    teams = {t['key']: t['name'] for t in config['teams']}
    order = config['rotation_order']
    start = date.fromisoformat(config['rotation_start'])
    interval = config['rotation_interval_days']

    if for_date is None:
        for_date = today_kst()
    if isinstance(for_date, str):
        for_date = date.fromisoformat(for_date)

    days_since = (for_date - start).days
    if days_since < 0:
        first_key = order[0]
        return teams[first_key], start.isoformat(), None, None, first_key, None

    period = days_since // interval
    key_idx = period % len(order)
    check_date = start + timedelta(days=period * interval)
    next_period = period + 1
    next_key_idx = next_period % len(order)
    next_check_date = start + timedelta(days=next_period * interval)

    return (teams[order[key_idx]], check_date.isoformat(),
            next_check_date.isoformat(), teams[order[next_key_idx]],
            order[key_idx], order[next_key_idx])


# ============================================================
# Context processor
# ============================================================

@app.context_processor
def inject_globals():
    teams_display = get_teams_display()
    kst_now = datetime.now(KST)
    return {
        'current_user': session.get('display_name', ''),
        'current_role': session.get('role', ''),
        'current_group': session.get('group_name', ''),
        'groups': GROUPS,
        'teams_display': teams_display,
        'get_team_key': get_team_key_for_group,
        'now_kst': kst_now.strftime('%H:%M:%S'),
        'now_kst_date_full': kst_now.strftime('%A, %d %B %Y'),
    }


# ============================================================
# Routes: Auth
# ============================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()

        if user and check_password_hash(user['password_hash'], password):
            if not user['approved']:
                flash('Your account is pending admin approval.', 'warning')
                return render_template('login.html')
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['display_name'] = user['display_name']
            session['role'] = user['role']
            session['group_name'] = user['group_name']
            flash(f'Welcome, {user["display_name"]}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password.', 'danger')

    return render_template('login.html')


# ============================================================
# Item 10: Registration with email + verification + password reset
# ============================================================

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        display_name = request.form.get('display_name', '').strip()
        group_name = request.form.get('group_name', '')
        email = request.form.get('email', '').strip().lower()

        if not username or not password or not display_name:
            flash('Username, password, and display name are required.', 'danger')
            return render_template('register.html')

        db = get_db()
        existing = db.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
        if existing:
            flash('Username already taken.', 'danger')
            return render_template('register.html')

        db.execute(
            "INSERT INTO users (username, password_hash, display_name, group_name, role, approved, email, email_verified, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (username, generate_password_hash(password), display_name, group_name, 'member', 0, email, 0, now_kst())
        )
        db.commit()

        # Send verification email if email provided
        if email:
            user = db.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
            token = _secrets_mod.token_urlsafe(32)
            db.execute(
                "INSERT INTO email_tokens (user_id, email, token, token_type, created_at) VALUES (?, ?, ?, ?, ?)",
                (user['id'], email, token, 'verify', now_kst())
            )
            db.commit()
            _send_verification_email(email, token, display_name)

        flash('Registration submitted! Check your email for verification. Admin approval is also required.', 'info')
        return redirect(url_for('login'))

    return render_template('register.html')


def _send_verification_email(email, token, display_name):
    """Try to send verification email. Fail silently if not configured."""
    try:
        from email_utils import send_email
        verify_url = url_for('verify_email', token=token, _external=True)
        html = f"""
        <div style="font-family: sans-serif; max-width: 500px; margin: auto; padding: 20px;">
            <h2 style="color: #1a237e;">Email Verification</h2>
            <p>Hello <strong>{display_name}</strong>,</p>
            <p>Please verify your email address by clicking the link below:</p>
            <p><a href="{verify_url}" style="background: #1a237e; color: white; padding: 10px 24px; border-radius: 6px; text-decoration: none; display: inline-block;">Verify Email</a></p>
            <p style="font-size: 12px; color: #888;">If the button doesn't work, copy and paste this URL:<br>{verify_url}</p>
            <hr style="border: none; border-top: 1px solid #ddd;">
            <p style="font-size: 12px; color: #888;">Nano Lab Stock Check System</p>
        </div>
        """
        send_email(email, 'Nano Lab Stock Check - Verify Your Email', html)
    except Exception:
        pass


@app.route('/verify_email/<token>')
def verify_email(token):
    db = get_db()
    tok = db.execute(
        "SELECT * FROM email_tokens WHERE token = ? AND token_type = 'verify' AND used = 0",
        (token,)
    ).fetchone()
    if not tok:
        flash('Invalid or expired verification link.', 'danger')
        return redirect(url_for('login'))

    db.execute("UPDATE users SET email_verified = 1 WHERE id = ?", (tok['user_id'],))
    db.execute("UPDATE email_tokens SET used = 1 WHERE id = ?", (tok['id'],))
    db.commit()
    flash('Email verified successfully!', 'success')
    return redirect(url_for('login'))


@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        if not email:
            flash('Please enter your email address.', 'danger')
            return render_template('forgot_password.html')

        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email = ? AND email_verified = 1", (email,)).fetchone()
        if user:
            token = _secrets_mod.token_urlsafe(32)
            db.execute(
                "INSERT INTO email_tokens (user_id, email, token, token_type, created_at) VALUES (?, ?, ?, ?, ?)",
                (user['id'], email, token, 'reset', now_kst())
            )
            db.commit()
            _send_reset_email(email, token, user['display_name'])

        # Always show the same message to prevent email enumeration
        flash('If an account with that email exists, a password reset link has been sent.', 'info')
        return redirect(url_for('login'))

    return render_template('forgot_password.html')


def _send_reset_email(email, token, display_name):
    """Try to send password reset email. Fail silently if not configured."""
    try:
        from email_utils import send_email
        reset_url = url_for('reset_password_token', token=token, _external=True)
        html = f"""
        <div style="font-family: sans-serif; max-width: 500px; margin: auto; padding: 20px;">
            <h2 style="color: #c62828;">Password Reset</h2>
            <p>Hello <strong>{display_name}</strong>,</p>
            <p>Click the link below to reset your password. This link expires in 1 hour.</p>
            <p><a href="{reset_url}" style="background: #c62828; color: white; padding: 10px 24px; border-radius: 6px; text-decoration: none; display: inline-block;">Reset Password</a></p>
            <p style="font-size: 12px; color: #888;">If you didn't request this, ignore this email.</p>
            <hr style="border: none; border-top: 1px solid #ddd;">
            <p style="font-size: 12px; color: #888;">Nano Lab Stock Check System</p>
        </div>
        """
        send_email(email, 'Nano Lab Stock Check - Password Reset', html)
    except Exception:
        pass


@app.route('/reset_password_token/<token>', methods=['GET', 'POST'])
def reset_password_token(token):
    db = get_db()
    tok = db.execute(
        "SELECT * FROM email_tokens WHERE token = ? AND token_type = 'reset' AND used = 0",
        (token,)
    ).fetchone()
    if not tok:
        flash('Invalid or expired reset link.', 'danger')
        return redirect(url_for('login'))

    # Check 1 hour expiry
    created = datetime.strptime(tok['created_at'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=KST)
    if datetime.now(KST) - created > timedelta(hours=1):
        flash('Reset link has expired. Please request a new one.', 'danger')
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        new_password = request.form.get('password', '')
        if not new_password or len(new_password) < 4:
            flash('Password must be at least 4 characters.', 'danger')
            return render_template('reset_password_form.html', token=token)

        db.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                   (generate_password_hash(new_password), tok['user_id']))
        db.execute("UPDATE email_tokens SET used = 1 WHERE id = ?", (tok['id'],))
        db.commit()
        flash('Password reset successfully! Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('reset_password_form.html', token=token)


@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out.', 'info')
    return redirect(url_for('login'))


# ============================================================
# Routes: Dashboard
# ============================================================

@app.route('/')
@login_required
def dashboard():
    db = get_db()
    items = db.execute('SELECT * FROM items ORDER BY sort_order').fetchall()
    check_date = request.args.get('date', today_kst().isoformat())

    # Item 6: Use monthly table
    table_name = get_checks_table(check_date)
    ensure_checks_table(db, table_name)

    # Get only ONE record per item+group for the selected date (the latest)
    latest_checks = {}
    for group in GROUPS:
        rows = db.execute(f'''
            SELECT c.* FROM "{table_name}" c
            INNER JOIN (
                SELECT item_id, MAX(id) as max_id
                FROM "{table_name}"
                WHERE group_name = ? AND check_date = ?
                GROUP BY item_id
            ) latest ON c.id = latest.max_id
        ''', (group, check_date)).fetchall()
        for row in rows:
            key = (row['item_id'], group)
            latest_checks[key] = dict(row)

    # Get latest order request per item (any status) with full detail
    pending_orders = {}
    order_rows = db.execute(
        "SELECT item_id, status, quantity_needed, requested_by, note, created_at, resolved_by, resolved_at, ordered_by, ordered_at FROM order_requests ORDER BY created_at DESC"
    ).fetchall()
    for row in order_rows:
        if row['item_id'] not in pending_orders:
            pending_orders[row['item_id']] = {
                'status': row['status'],
                'date': row['created_at'][:10] if row['created_at'] else '',
                'quantity': row['quantity_needed'],
                'requested_by': row['requested_by'],
                'note': row['note'],
                'resolved_by': row['resolved_by'],
                'resolved_at': row['resolved_at'][:10] if row['resolved_at'] else '',
                'ordered_by': row['ordered_by'],
                'ordered_at': row['ordered_at'][:10] if row['ordered_at'] else '',
            }

    # Summary stats
    summary = {'ok': 0, 'low': 0, 'empty': 0, 'unchecked': 0, 'groups_checked': 0, 'pending_orders': 0, 'ordered': 0}
    total_items = db.execute('SELECT COUNT(*) FROM items').fetchone()[0]
    groups_with_data = set()
    for key, check in latest_checks.items():
        groups_with_data.add(key[1])
        if check['status'] == 'ok':
            summary['ok'] += 1
        elif check['status'] == 'low':
            summary['low'] += 1
        elif check['status'] == 'empty':
            summary['empty'] += 1
    summary['groups_checked'] = len(groups_with_data)
    summary['unchecked'] = total_items * len(groups_with_data) - len(latest_checks) if groups_with_data else 0
    for oid, oinfo in pending_orders.items():
        if oinfo['status'] == 'pending':
            summary['pending_orders'] += 1
        elif oinfo['status'] == 'ordered':
            summary['ordered'] += 1

    # Get last checked date per group (scan all monthly tables)
    last_checked = {}
    all_tables = get_all_checks_tables(db)
    for group in GROUPS:
        best = None
        for tbl in all_tables:
            row = db.execute(f'SELECT MAX(check_date) as last_date FROM "{tbl}" WHERE group_name = ?', (group,)).fetchone()
            if row and row['last_date']:
                if best is None or row['last_date'] > best:
                    best = row['last_date']
        last_checked[group] = best

    # Rotation schedule
    rotation_info = get_rotation_info(check_date)
    rotation_group = rotation_info[0]
    rotation_check_date = rotation_info[1]
    next_check_date = rotation_info[2]
    next_group = rotation_info[3]
    duty_team_key = rotation_info[4]
    next_team_key = rotation_info[5]

    # Previous duty day records
    interval_days = _teams_config['rotation_interval_days']
    prev_date_obj = date.fromisoformat(rotation_check_date) - timedelta(days=interval_days)
    prev_duty_date = prev_date_obj.isoformat()
    prev_rot = get_rotation_info(prev_duty_date)
    prev_duty_group = prev_rot[0]
    prev_duty_team_key = prev_rot[4]

    prev_checks = {}
    prev_table = get_checks_table(prev_duty_date)
    if prev_table in get_all_checks_tables(db):
        for group in GROUPS:
            rows = db.execute(f'''
                SELECT c.* FROM "{prev_table}" c
                INNER JOIN (
                    SELECT item_id, MAX(id) as max_id
                    FROM "{prev_table}"
                    WHERE group_name = ? AND check_date = ?
                    GROUP BY item_id
                ) latest ON c.id = latest.max_id
            ''', (group, prev_duty_date)).fetchall()
            for row in rows:
                key = (row['item_id'], group)
                prev_checks[key] = dict(row)

    # Organize items by stock_place
    places = []
    current_place = None
    current_items = []
    for item in items:
        if item['stock_place'] != current_place:
            if current_place is not None:
                places.append((current_place, current_items))
            current_place = item['stock_place']
            current_items = []
        current_items.append(dict(item))
    if current_place is not None:
        places.append((current_place, current_items))

    return render_template('dashboard.html',
                           places=places,
                           items=items,
                           latest_checks=latest_checks,
                           pending_orders=pending_orders,
                           last_checked=last_checked,
                           summary=summary,
                           check_date=check_date,
                           today=today_kst().isoformat(),
                           rotation_group=rotation_group,
                           rotation_check_date=rotation_check_date,
                           next_check_date=next_check_date,
                           next_group=next_group,
                           duty_team_key=duty_team_key,
                           next_team_key=next_team_key,
                           prev_duty_date=prev_duty_date,
                           prev_duty_group=prev_duty_group,
                           prev_duty_team_key=prev_duty_team_key,
                           prev_checks=prev_checks,
                           can_edit=(session.get('role') == 'admin' or (
                               today_kst().isoformat() == rotation_check_date and
                               session.get('group_name') == rotation_group and
                               check_date == today_kst().isoformat()
                           )))


# ============================================================
# Item 3: Refuse empty entries + Item 1: Number-only input
# ============================================================

@app.route('/submit_check', methods=['POST'])
@login_required
def submit_check():
    """UPSERT with validation: all items required (except Dr.Lee items for non-Dr.Lee groups)."""
    db = get_db()
    group_name = session.get('group_name', '')
    username = session.get('username', '')
    check_date = request.form.get('check_date', today_kst().isoformat())

    # Non-admin: can only submit on their exact duty Thursday (today must BE that Thursday)
    if session.get('role') != 'admin':
        today_str = today_kst().isoformat()
        rot_info = get_rotation_info(today_str)
        duty_group = rot_info[0]
        duty_date = rot_info[1]  # the actual Thursday date
        if today_str != duty_date:
            flash('Submissions are only open on duty Thursdays.', 'danger')
            return redirect(url_for('dashboard', date=check_date))
        if group_name != duty_group:
            flash('Only the on-duty group can submit stock checks today.', 'danger')
            return redirect(url_for('dashboard', date=check_date))
        if check_date != today_str:
            flash('You can only submit for today\'s date on your duty day.', 'danger')
            return redirect(url_for('dashboard', date=check_date))

    items = db.execute('SELECT * FROM items ORDER BY sort_order').fetchall()

    # Item 3: Validate entered items — only reject if a value is entered but not a valid number.
    # Empty fields are allowed (partial submission OK, same as V3).
    # Dr.Lee items are skipped entirely for non-Dr.Lee groups.
    is_drlee_group = (group_name == 'Dr.Lee/Zhijun')
    errors = []
    entries = []

    for item in items:
        is_drlee_item = (item['category'] == 'Dr.Lee')
        if not is_drlee_group and is_drlee_item:
            continue  # Non-Dr.Lee group: skip Dr.Lee items entirely

        qty_str = request.form.get(f'qty_{item["id"]}', '').strip()
        note = request.form.get(f'note_{item["id"]}', '').strip()

        if not qty_str:
            continue  # Empty is OK — partial submission allowed

        if not is_valid_number(qty_str):
            errors.append(f'{item["item_name"]}: not a valid number')
            continue

        qty_val = float(qty_str)
        min_val = item['min_value']
        status = compute_status(qty_val, min_val)
        entries.append((item['id'], group_name, username, qty_str, status, note, check_date))

    if errors:
        flash('Submission rejected. Fix the following: ' + '; '.join(errors[:10]), 'danger')
        if len(errors) > 10:
            flash(f'...and {len(errors) - 10} more errors.', 'danger')
        return redirect(url_for('dashboard', date=check_date))

    if not entries:
        flash('No items filled. Please enter at least one quantity.', 'warning')
        return redirect(url_for('dashboard', date=check_date))

    # Item 6: Use monthly table
    table_name = get_checks_table(check_date)
    ensure_checks_table(db, table_name)

    # Delete old records for this group+date first
    db.execute(f'DELETE FROM "{table_name}" WHERE group_name = ? AND check_date = ?',
               (group_name, check_date))

    ts = now_kst()
    for entry in entries:
        db.execute(
            f'INSERT INTO "{table_name}" (item_id, group_name, checked_by, quantity, status, note, check_date, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            entry + (ts,)
        )

    db.commit()
    flash(f'Stock check submitted ({len(entries)} items).', 'success')
    return redirect(url_for('dashboard', date=check_date))


# ============================================================
# Routes: History (Item 6: scan all monthly tables)
# ============================================================

@app.route('/history')
@login_required
def history():
    db = get_db()
    page = request.args.get('page', 1, type=int)
    per_page = 50
    group_filter = request.args.get('group', '')
    date_filter = request.args.get('date', '')

    all_tables = get_all_checks_tables(db)
    if not all_tables:
        return render_template('history.html', rows=[], page=1, total_pages=1, total=0,
                               group_filter=group_filter, date_filter=date_filter, dates=[])

    # If filtering by date, only query the relevant monthly table
    if date_filter:
        target_table = get_checks_table(date_filter)
        if target_table in all_tables:
            tables_to_query = [target_table]
        else:
            tables_to_query = []
    else:
        tables_to_query = all_tables

    if not tables_to_query:
        return render_template('history.html', rows=[], page=1, total_pages=1, total=0,
                               group_filter=group_filter, date_filter=date_filter, dates=[])

    # Build UNION ALL query
    union_parts = []
    params = []
    for tbl in tables_to_query:
        where = "WHERE 1=1"
        if group_filter:
            where += " AND c.group_name = ?"
            params.append(group_filter)
        if date_filter:
            where += " AND c.check_date = ?"
            params.append(date_filter)
        union_parts.append(f'''
            SELECT c.id, c.item_id, c.group_name, c.checked_by, c.quantity, c.status, c.note,
                   c.check_date, c.created_at, i.item_name, i.stock_place, i.minimum
            FROM "{tbl}" c JOIN items i ON c.item_id = i.id {where}
        ''')

    union_query = ' UNION ALL '.join(union_parts)

    # Count
    count_query = f"SELECT COUNT(*) FROM ({union_query})"
    total = db.execute(count_query, params).fetchone()[0]

    # Paginated query
    full_query = f"{union_query} ORDER BY check_date DESC, item_name LIMIT ? OFFSET ?"
    params_page = params + [per_page, (page - 1) * per_page]
    rows = db.execute(full_query, params_page).fetchall()

    total_pages = max(1, (total + per_page - 1) // per_page)

    # Get distinct dates across all tables
    date_union_parts = [f'SELECT DISTINCT check_date FROM "{tbl}"' for tbl in all_tables]
    date_union = ' UNION '.join(date_union_parts)
    dates = db.execute(f'{date_union} ORDER BY check_date DESC').fetchall()

    return render_template('history.html',
                           rows=rows,
                           page=page,
                           total_pages=total_pages,
                           total=total,
                           group_filter=group_filter,
                           date_filter=date_filter,
                           dates=[d['check_date'] for d in dates])


# ============================================================
# Routes: Order Requests
# ============================================================

@app.route('/order_request', methods=['POST'])
@login_required
def create_order_request():
    db = get_db()
    item_id = request.form.get('item_id', type=int)
    quantity_needed = request.form.get('quantity_needed', '').strip()
    note = request.form.get('note', '').strip()
    username = session.get('display_name', session.get('username', ''))

    if not item_id:
        flash('Invalid item.', 'danger')
        return redirect(url_for('dashboard'))

    existing = db.execute(
        "SELECT id FROM order_requests WHERE item_id = ? AND status IN ('pending', 'ordered')",
        (item_id,)
    ).fetchone()
    if existing:
        flash('An order request already exists for this item.', 'warning')
        return redirect(url_for('dashboard'))

    group_name = session.get('group_name', '')
    db.execute(
        'INSERT INTO order_requests (item_id, requested_by, requested_by_group, quantity_needed, note, created_at) VALUES (?, ?, ?, ?, ?, ?)',
        (item_id, username, group_name, quantity_needed, note, now_kst())
    )
    db.commit()
    flash('Order request created.', 'success')
    return redirect(url_for('dashboard'))


@app.route('/orders')
@login_required
def orders():
    db = get_db()
    status_filter = request.args.get('status', '')

    query = '''
        SELECT o.*, i.item_name, i.stock_place, i.minimum
        FROM order_requests o
        JOIN items i ON o.item_id = i.id
        WHERE 1=1
    '''
    params = []
    if status_filter:
        query += ' AND o.status = ?'
        params.append(status_filter)
    query += ' ORDER BY o.created_at DESC'
    rows = db.execute(query, params).fetchall()

    return render_template('orders.html', rows=rows, status_filter=status_filter)


@app.route('/orders/update/<int:order_id>', methods=['POST'])
@login_required
def update_order(order_id):
    db = get_db()
    new_status = request.form.get('status', '')
    if new_status not in ('pending', 'ordered', 'received', 'cancelled', 'refused'):
        flash('Invalid status.', 'danger')
        return redirect(url_for('orders'))

    if new_status in ('refused', 'ordered', 'received') and session.get('role') != 'admin':
        flash('Only admin can perform this action.', 'danger')
        return redirect(url_for('orders'))

    if new_status == 'cancelled':
        order = db.execute('SELECT * FROM order_requests WHERE id = ?', (order_id,)).fetchone()
        if order and session.get('role') != 'admin' and order['requested_by_group'] != session.get('group_name', ''):
            flash('You can only cancel your own group\'s order requests.', 'danger')
            return redirect(url_for('orders'))

    actor = session.get('display_name', session.get('username', ''))
    ts = now_kst()
    if new_status == 'ordered':
        db.execute(
            'UPDATE order_requests SET status = ?, ordered_by = ?, ordered_at = ? WHERE id = ?',
            (new_status, actor, ts, order_id)
        )
    elif new_status in ('received', 'cancelled', 'refused'):
        db.execute(
            'UPDATE order_requests SET status = ?, resolved_by = ?, resolved_at = ? WHERE id = ?',
            (new_status, actor, ts, order_id)
        )
    else:
        db.execute(
            'UPDATE order_requests SET status = ? WHERE id = ?',
            (new_status, order_id)
        )
    db.commit()
    flash(f'Order status updated to {new_status}.', 'success')
    return redirect(url_for('orders'))


@app.route('/admin/delete_all_orders', methods=['POST'])
@admin_required
def delete_all_orders():
    """Delete all order request records."""
    db = get_db()
    count = db.execute('SELECT COUNT(*) FROM order_requests').fetchone()[0]
    db.execute('DELETE FROM order_requests')
    db.commit()
    flash(f'All order requests deleted ({count} records).', 'success')
    return redirect(url_for('orders'))


# ============================================================
# Routes: Admin
# ============================================================

@app.route('/admin')
@admin_required
def admin_panel():
    db = get_db()
    users = db.execute('SELECT * FROM users ORDER BY id').fetchall()
    pending_count = db.execute('SELECT COUNT(*) FROM users WHERE approved = 0').fetchone()[0]
    return render_template('admin.html', users=users, pending_count=pending_count)


@app.route('/admin/approve/<int:user_id>', methods=['POST'])
@admin_required
def approve_user(user_id):
    db = get_db()
    db.execute('UPDATE users SET approved = 1 WHERE id = ?', (user_id,))
    db.commit()
    flash('User approved.', 'success')
    return redirect(url_for('admin_panel'))


@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@admin_required
def delete_user(user_id):
    if user_id == session.get('user_id'):
        flash('Cannot delete yourself.', 'danger')
        return redirect(url_for('admin_panel'))
    db = get_db()
    db.execute('DELETE FROM users WHERE id = ?', (user_id,))
    db.commit()
    flash('User deleted.', 'success')
    return redirect(url_for('admin_panel'))


@app.route('/admin/update_user/<int:user_id>', methods=['POST'])
@admin_required
def update_user(user_id):
    db = get_db()
    role = request.form.get('role', 'member')
    group_name = request.form.get('group_name', '')
    display_name = request.form.get('display_name', '')

    db.execute('UPDATE users SET role = ?, group_name = ?, display_name = ? WHERE id = ?',
               (role, group_name, display_name, user_id))
    db.commit()
    flash('User updated.', 'success')
    return redirect(url_for('admin_panel'))


@app.route('/admin/reset_password/<int:user_id>', methods=['POST'])
@admin_required
def reset_password(user_id):
    db = get_db()
    new_password = request.form.get('new_password', '').strip()
    if not new_password:
        flash('Password cannot be empty.', 'danger')
        return redirect(url_for('admin_panel'))
    db.execute('UPDATE users SET password_hash = ? WHERE id = ?',
               (generate_password_hash(new_password), user_id))
    db.commit()
    flash('Password reset.', 'success')
    return redirect(url_for('admin_panel'))


# ============================================================
# Routes: Admin — Delete Check Records (Item 6: monthly tables)
# ============================================================

@app.route('/admin/delete_check/<int:check_id>', methods=['POST'])
@admin_required
def delete_check(check_id):
    """Delete a single check record. Must specify which monthly table via query param."""
    db = get_db()
    check_date = request.args.get('date', '')
    if check_date:
        table_name = get_checks_table(check_date)
        if table_name in get_all_checks_tables(db):
            db.execute(f'DELETE FROM "{table_name}" WHERE id = ?', (check_id,))
    else:
        # Search all tables
        for tbl in get_all_checks_tables(db):
            db.execute(f'DELETE FROM "{tbl}" WHERE id = ?', (check_id,))
    db.commit()
    flash('Check record deleted.', 'success')
    return redirect(request.referrer or url_for('history'))


@app.route('/admin/delete_checks_bulk', methods=['POST'])
@admin_required
def delete_checks_bulk():
    """Delete all check records matching group + date."""
    db = get_db()
    group_name = request.form.get('group_name', '')
    check_date = request.form.get('check_date', '')

    if check_date:
        table_name = get_checks_table(check_date)
        if table_name in get_all_checks_tables(db):
            if group_name:
                db.execute(f'DELETE FROM "{table_name}" WHERE group_name = ? AND check_date = ?',
                           (group_name, check_date))
                flash(f'All checks for {group_name} on {check_date} deleted.', 'success')
            else:
                db.execute(f'DELETE FROM "{table_name}" WHERE check_date = ?', (check_date,))
                flash(f'All checks for {check_date} deleted.', 'success')
    else:
        flash('Please specify at least a date.', 'danger')

    db.commit()
    return redirect(url_for('history'))


@app.route('/admin/delete_all_checks', methods=['POST'])
@admin_required
def delete_all_checks():
    """Delete ALL check records from ALL monthly tables."""
    db = get_db()
    tables = get_all_checks_tables(db)
    total = 0
    for tbl in tables:
        count = db.execute(f'SELECT COUNT(*) FROM "{tbl}"').fetchone()[0]
        total += count
        db.execute(f'DELETE FROM "{tbl}"')
    db.commit()
    flash(f'All check history deleted ({total} records from {len(tables)} tables).', 'success')
    return redirect(url_for('history'))


# ============================================================
# Routes: Admin Items (Item 1: split minimum into value + unit)
# ============================================================

@app.route('/admin/items')
@admin_required
def admin_items():
    db = get_db()
    items = db.execute('SELECT * FROM items ORDER BY sort_order').fetchall()
    return render_template('admin_items.html', items=items)


@app.route('/admin/items/add', methods=['POST'])
@admin_required
def add_item():
    db = get_db()
    stock_place = request.form.get('stock_place', '').strip()
    item_name = request.form.get('item_name', '').strip()
    min_value_str = request.form.get('min_value', '').strip()
    min_unit = request.form.get('min_unit', '').strip()
    category = request.form.get('category', 'Common').strip()

    min_value = float(min_value_str) if min_value_str else None
    minimum = f"{int(min_value) if min_value is not None and min_value == int(min_value) else min_value} {min_unit}".strip() if min_value is not None else min_unit

    max_order = db.execute('SELECT MAX(sort_order) FROM items').fetchone()[0] or 0

    db.execute(
        'INSERT INTO items (stock_place, item_name, minimum, min_value, min_unit, category, sort_order) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (stock_place, item_name, minimum, min_value, min_unit, category, max_order + 1)
    )
    db.commit()
    flash(f'Item "{item_name}" added.', 'success')
    return redirect(url_for('admin_items'))


@app.route('/admin/items/edit/<int:item_id>', methods=['POST'])
@admin_required
def edit_item(item_id):
    db = get_db()
    stock_place = request.form.get('stock_place', '').strip()
    item_name = request.form.get('item_name', '').strip()
    min_value_str = request.form.get('min_value', '').strip()
    min_unit = request.form.get('min_unit', '').strip()
    category = request.form.get('category', 'Common').strip()
    sort_order = request.form.get('sort_order', 0, type=int)

    min_value = float(min_value_str) if min_value_str else None
    minimum = f"{int(min_value) if min_value is not None and min_value == int(min_value) else min_value} {min_unit}".strip() if min_value is not None else min_unit

    db.execute(
        'UPDATE items SET stock_place=?, item_name=?, minimum=?, min_value=?, min_unit=?, category=?, sort_order=? WHERE id=?',
        (stock_place, item_name, minimum, min_value, min_unit, category, sort_order, item_id)
    )
    db.commit()
    flash(f'Item "{item_name}" updated.', 'success')
    return redirect(url_for('admin_items'))


@app.route('/admin/items/delete/<int:item_id>', methods=['POST'])
@admin_required
def delete_item(item_id):
    db = get_db()
    db.execute('DELETE FROM items WHERE id = ?', (item_id,))
    db.commit()
    flash('Item deleted.', 'success')
    return redirect(url_for('admin_items'))


# ============================================================
# Routes: Export (Item 7: UTF-8 BOM, Item 6: monthly tables)
# ============================================================

@app.route('/export')
@admin_required
def export_csv():
    """Export with UTF-8 BOM for Excel compatibility."""
    db = get_db()
    check_date = request.args.get('date', '')

    if check_date:
        tables_to_query = [get_checks_table(check_date)]
    else:
        tables_to_query = get_all_checks_tables(db)

    if not tables_to_query:
        flash('No data to export.', 'warning')
        return redirect(url_for('dashboard'))

    # Query all relevant tables
    all_rows = []
    for tbl in tables_to_query:
        if tbl not in get_all_checks_tables(db):
            continue
        query = f'''
            SELECT c.check_date, c.group_name, c.checked_by, i.stock_place, i.item_name,
                   i.minimum, c.quantity, c.status, c.note, c.created_at
            FROM "{tbl}" c
            JOIN items i ON c.item_id = i.id
            INNER JOIN (
                SELECT MAX(id) as max_id
                FROM "{tbl}"
        '''
        params = []
        if check_date:
            query += ' WHERE check_date = ?'
            params.append(check_date)
        query += f'''
                GROUP BY item_id, group_name, check_date
            ) latest ON c.id = latest.max_id
            ORDER BY c.check_date DESC, i.sort_order, c.group_name
        '''
        rows = db.execute(query, params).fetchall()
        all_rows.extend(rows)

    output = io.StringIO()
    # Item 7: UTF-8 BOM
    output.write('\ufeff')
    writer = csv.writer(output)
    writer.writerow(['Date', 'Group', 'Checked By', 'Location', 'Item', 'Minimum', 'Quantity', 'Status', 'Note', 'Timestamp (KST)'])
    for row in all_rows:
        writer.writerow([row['check_date'], row['group_name'], row['checked_by'],
                         row['stock_place'], row['item_name'], row['minimum'],
                         row['quantity'], row['status'], row['note'], row['created_at']])

    filename = f'stock_check_{check_date or "all"}.csv'
    resp = Response(
        output.getvalue().encode('utf-8-sig'),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )
    resp.headers['Content-Type'] = 'text/csv; charset=utf-8'
    return resp


# ============================================================
# Main
# ============================================================

if __name__ == '__main__':
    init_db()
    print('=' * 50)
    print('  Nano Lab Stock Check System V4')
    print('  http://127.0.0.1:5001')
    print('  Admin: admin / admin123')
    print('=' * 50)
    app.run(host='0.0.0.0', port=5001, debug=True)
