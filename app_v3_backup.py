#!/usr/bin/env python3
"""
Nano Lab Stock Check System
A shared web-based stock check system for lab members.
"""

import os
import re
import csv
import io
import sqlite3
from datetime import datetime, date, timedelta
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, g, jsonify, Response
)
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
# Fix #2: Generate a persistent random secret key (stored in a file so sessions survive restarts)
_secret_key_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.secret_key')
if os.path.exists(_secret_key_file):
    with open(_secret_key_file, 'r') as f:
        app.secret_key = f.read().strip()
else:
    import secrets
    app.secret_key = secrets.token_hex(32)
    with open(_secret_key_file, 'w') as f:
        f.write(app.secret_key)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'stock_check.db')

# --- Groups ---
# Rotation order: starting Feb 26 2026, one group checks every 2 weeks
GROUPS = [
    'Dr.Lee/Zhijun',
    'Dr.yoo/dahee',
    'junhyun/thuan',
    'Dr.azary/nattha',
    'Dr.Kim/윤현승',
]

# --- Pre-loaded items ---
INITIAL_ITEMS = [
    # (stock_place, item_name, minimum, category, sort_order)
    ('4°C refrigerator', 'DMEM(LM001-05)', '6 bottles', 'Common', 1),
    ('4°C refrigerator', 'RPMI(sh30255.01)', '6 bottles', 'Common', 2),
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_place TEXT NOT NULL,
            item_name TEXT NOT NULL,
            minimum TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL DEFAULT 'Common',
            sort_order INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            group_name TEXT NOT NULL,
            checked_by TEXT NOT NULL,
            quantity TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'unknown',
            note TEXT NOT NULL DEFAULT '',
            check_date TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resolved_at TIMESTAMP,
            FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_checks_item_group ON checks(item_id, group_name);
        CREATE INDEX IF NOT EXISTS idx_checks_date ON checks(check_date);
        CREATE INDEX IF NOT EXISTS idx_checks_unique ON checks(item_id, group_name, check_date);
    ''')

    # Create admin if not exists
    existing = db.execute('SELECT id FROM users WHERE username = ?', ('admin',)).fetchone()
    if not existing:
        db.execute(
            'INSERT INTO users (username, password_hash, display_name, group_name, role, approved) VALUES (?, ?, ?, ?, ?, ?)',
            ('admin', generate_password_hash('admin123'), 'Admin', 'Dr.Lee/Zhijun', 'admin', 1)
        )

    # Load initial items if table is empty
    count = db.execute('SELECT COUNT(*) FROM items').fetchone()[0]
    if count == 0:
        for item in INITIAL_ITEMS:
            db.execute(
                'INSERT INTO items (stock_place, item_name, minimum, category, sort_order) VALUES (?, ?, ?, ?, ?)',
                item
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
    text = text.strip()
    m = re.match(r'(\d+(?:\.\d+)?)', text)
    if m:
        return float(m.group(1))
    return None


def compute_status(quantity_text, minimum_text):
    """Compare quantity to minimum and return status: ok / low / empty / unknown"""
    qty = parse_number(quantity_text)
    min_val = parse_number(minimum_text)

    if qty is None:
        return 'unknown'
    if qty == 0:
        return 'empty'
    if min_val is not None and qty < min_val:
        return 'low'
    if min_val is not None and qty >= min_val:
        return 'ok'
    return 'unknown'


# ============================================================
# Rotation schedule
# ============================================================

ROTATION_START = date(2026, 2, 26)  # First check day (Thursday)
ROTATION_INTERVAL = 14  # Every 2 Thursdays = 14 days

def get_rotation_info(for_date=None):
    """Return rotation info: which group checks on the nearest check day.
    Returns (duty_group, check_date, next_check_date, next_group)."""
    if for_date is None:
        for_date = date.today()
    if isinstance(for_date, str):
        for_date = date.fromisoformat(for_date)
    days_since_start = (for_date - ROTATION_START).days
    if days_since_start < 0:
        # Before first check day
        return GROUPS[0], ROTATION_START.isoformat(), None, None
    # Which check period are we in (or past)?
    period = days_since_start // ROTATION_INTERVAL
    group_index = period % len(GROUPS)
    check_date = ROTATION_START + timedelta(days=period * ROTATION_INTERVAL)
    # Next check
    next_period = period + 1
    next_group_index = next_period % len(GROUPS)
    next_check_date = ROTATION_START + timedelta(days=next_period * ROTATION_INTERVAL)
    return (GROUPS[group_index], check_date.isoformat(),
            next_check_date.isoformat(), GROUPS[next_group_index])


# ============================================================
# Context processor
# ============================================================

@app.context_processor
def inject_globals():
    return {
        'current_user': session.get('display_name', ''),
        'current_role': session.get('role', ''),
        'current_group': session.get('group_name', ''),
        'groups': GROUPS,
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


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        display_name = request.form.get('display_name', '').strip()
        group_name = request.form.get('group_name', '')

        if not username or not password or not display_name:
            flash('All fields are required.', 'danger')
            return render_template('register.html')

        db = get_db()
        existing = db.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
        if existing:
            flash('Username already taken.', 'danger')
            return render_template('register.html')

        db.execute(
            'INSERT INTO users (username, password_hash, display_name, group_name, role, approved) VALUES (?, ?, ?, ?, ?, ?)',
            (username, generate_password_hash(password), display_name, group_name, 'member', 0)
        )
        db.commit()
        flash('Registration submitted! Please wait for admin approval.', 'info')
        return redirect(url_for('login'))

    return render_template('register.html')


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
    check_date = request.args.get('date', date.today().isoformat())

    # FIX #1: Get only ONE record per item+group for the selected date (the latest)
    latest_checks = {}
    for group in GROUPS:
        rows = db.execute('''
            SELECT c.* FROM checks c
            INNER JOIN (
                SELECT item_id, MAX(id) as max_id
                FROM checks
                WHERE group_name = ? AND check_date = ?
                GROUP BY item_id
            ) latest ON c.id = latest.max_id
        ''', (group, check_date)).fetchall()
        for row in rows:
            key = (row['item_id'], group)
            latest_checks[key] = dict(row)

    # Get pending order requests for showing order status (with date info)
    pending_orders = {}
    order_rows = db.execute(
        "SELECT item_id, status, created_at FROM order_requests WHERE status IN ('pending', 'ordered') ORDER BY created_at DESC"
    ).fetchall()
    for row in order_rows:
        if row['item_id'] not in pending_orders:
            pending_orders[row['item_id']] = {
                'status': row['status'],
                'date': row['created_at'][:10] if row['created_at'] else ''
            }

    # Summary stats: count statuses per group that has checked today
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
    # Unchecked = items not checked by groups that DID check (partial submissions)
    summary['unchecked'] = total_items * len(groups_with_data) - len(latest_checks) if groups_with_data else 0
    for oid, oinfo in pending_orders.items():
        if oinfo['status'] == 'pending':
            summary['pending_orders'] += 1
        elif oinfo['status'] == 'ordered':
            summary['ordered'] += 1

    # Fix #4: Get last checked date per group
    last_checked = {}
    for group in GROUPS:
        row = db.execute(
            'SELECT MAX(check_date) as last_date FROM checks WHERE group_name = ?',
            (group,)
        ).fetchone()
        last_checked[group] = row['last_date'] if row and row['last_date'] else None

    # Rotation schedule
    rotation_group, rotation_check_date, next_check_date, next_group = get_rotation_info(check_date)

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
                           today=date.today().isoformat(),
                           rotation_group=rotation_group,
                           rotation_check_date=rotation_check_date,
                           next_check_date=next_check_date,
                           next_group=next_group)


@app.route('/submit_check', methods=['POST'])
@login_required
def submit_check():
    """FIX #1: UPSERT — delete old records for same item+group+date, then insert new."""
    db = get_db()
    group_name = session.get('group_name', '')
    username = session.get('username', '')
    check_date = request.form.get('check_date', date.today().isoformat())

    items = db.execute('SELECT * FROM items ORDER BY sort_order').fetchall()

    # Delete old records for this group+date first
    db.execute(
        'DELETE FROM checks WHERE group_name = ? AND check_date = ?',
        (group_name, check_date)
    )

    warnings = []
    count = 0
    for item in items:
        quantity = request.form.get(f'qty_{item["id"]}', '').strip()
        note = request.form.get(f'note_{item["id"]}', '').strip()

        if not quantity:
            continue

        # Fix #3: Warn if quantity has no parseable number
        if parse_number(quantity) is None:
            warnings.append(item['item_name'])

        status = compute_status(quantity, item['minimum'])

        db.execute(
            'INSERT INTO checks (item_id, group_name, checked_by, quantity, status, note, check_date) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (item['id'], group_name, username, quantity, status, note, check_date)
        )
        count += 1

    db.commit()
    if warnings:
        flash(f'Warning: No number detected for: {", ".join(warnings)}. Use format like "3 bottles".', 'warning')
    flash(f'Stock check submitted ({count} items).', 'success')
    return redirect(url_for('dashboard', date=check_date))


# ============================================================
# Routes: History
# ============================================================

@app.route('/history')
@login_required
def history():
    db = get_db()
    page = request.args.get('page', 1, type=int)
    per_page = 50
    group_filter = request.args.get('group', '')
    date_filter = request.args.get('date', '')

    query = '''
        SELECT c.*, i.item_name, i.stock_place, i.minimum
        FROM checks c
        JOIN items i ON c.item_id = i.id
        WHERE 1=1
    '''
    params = []

    if group_filter:
        query += ' AND c.group_name = ?'
        params.append(group_filter)
    if date_filter:
        query += ' AND c.check_date = ?'
        params.append(date_filter)

    count_query = query.replace('SELECT c.*, i.item_name, i.stock_place, i.minimum', 'SELECT COUNT(*)')
    total = db.execute(count_query, params).fetchone()[0]

    query += ' ORDER BY c.check_date DESC, i.sort_order LIMIT ? OFFSET ?'
    params.extend([per_page, (page - 1) * per_page])
    rows = db.execute(query, params).fetchall()

    total_pages = max(1, (total + per_page - 1) // per_page)

    # Get distinct dates for filter
    dates = db.execute('SELECT DISTINCT check_date FROM checks ORDER BY check_date DESC').fetchall()

    return render_template('history.html',
                           rows=rows,
                           page=page,
                           total_pages=total_pages,
                           total=total,
                           group_filter=group_filter,
                           date_filter=date_filter,
                           dates=[d['check_date'] for d in dates])


# ============================================================
# Routes: Order Requests (FIX #5)
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

    # Check if there's already a pending/ordered request for this item
    existing = db.execute(
        "SELECT id FROM order_requests WHERE item_id = ? AND status IN ('pending', 'ordered')",
        (item_id,)
    ).fetchone()
    if existing:
        flash('An order request already exists for this item.', 'warning')
        return redirect(url_for('dashboard'))

    group_name = session.get('group_name', '')
    db.execute(
        'INSERT INTO order_requests (item_id, requested_by, requested_by_group, quantity_needed, note) VALUES (?, ?, ?, ?, ?)',
        (item_id, username, group_name, quantity_needed, note)
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

    # Only admin can refuse or mark as ordered/received
    if new_status in ('refused', 'ordered', 'received') and session.get('role') != 'admin':
        flash('Only admin can perform this action.', 'danger')
        return redirect(url_for('orders'))

    # Cancel: only own group or admin
    if new_status == 'cancelled':
        order = db.execute('SELECT * FROM order_requests WHERE id = ?', (order_id,)).fetchone()
        if order and session.get('role') != 'admin' and order['requested_by_group'] != session.get('group_name', ''):
            flash('You can only cancel your own group\'s order requests.', 'danger')
            return redirect(url_for('orders'))

    resolved_by = session.get('display_name', session.get('username', ''))
    resolved_at = datetime.now().isoformat() if new_status in ('received', 'cancelled', 'refused') else None
    db.execute(
        'UPDATE order_requests SET status = ?, resolved_at = ?, resolved_by = ? WHERE id = ?',
        (new_status, resolved_at, resolved_by, order_id)
    )
    db.commit()
    flash(f'Order status updated to {new_status}.', 'success')
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
# Routes: Admin — Delete Check Records (FIX #6)
# ============================================================

@app.route('/admin/delete_check/<int:check_id>', methods=['POST'])
@admin_required
def delete_check(check_id):
    """Delete a single check record."""
    db = get_db()
    db.execute('DELETE FROM checks WHERE id = ?', (check_id,))
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

    if group_name and check_date:
        db.execute('DELETE FROM checks WHERE group_name = ? AND check_date = ?',
                   (group_name, check_date))
        flash(f'All checks for {group_name} on {check_date} deleted.', 'success')
    elif check_date:
        db.execute('DELETE FROM checks WHERE check_date = ?', (check_date,))
        flash(f'All checks for {check_date} deleted.', 'success')
    else:
        flash('Please specify at least a date.', 'danger')

    db.commit()
    return redirect(url_for('history'))


# ============================================================
# Routes: Admin Items
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
    minimum = request.form.get('minimum', '').strip()
    category = request.form.get('category', 'Common').strip()

    max_order = db.execute('SELECT MAX(sort_order) FROM items').fetchone()[0] or 0

    db.execute(
        'INSERT INTO items (stock_place, item_name, minimum, category, sort_order) VALUES (?, ?, ?, ?, ?)',
        (stock_place, item_name, minimum, category, max_order + 1)
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
    minimum = request.form.get('minimum', '').strip()
    category = request.form.get('category', 'Common').strip()
    sort_order = request.form.get('sort_order', 0, type=int)

    db.execute(
        'UPDATE items SET stock_place=?, item_name=?, minimum=?, category=?, sort_order=? WHERE id=?',
        (stock_place, item_name, minimum, category, sort_order, item_id)
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
# Routes: Export
# ============================================================

@app.route('/export')
@admin_required
def export_csv():
    """FIX #1: Export only the latest record per item+group+date."""
    db = get_db()
    check_date = request.args.get('date', '')

    query = '''
        SELECT c.check_date, c.group_name, c.checked_by, i.stock_place, i.item_name,
               i.minimum, c.quantity, c.status, c.note, c.created_at
        FROM checks c
        JOIN items i ON c.item_id = i.id
        INNER JOIN (
            SELECT MAX(id) as max_id
            FROM checks
    '''
    params = []
    if check_date:
        query += ' WHERE check_date = ?'
        params.append(check_date)
    query += '''
            GROUP BY item_id, group_name, check_date
        ) latest ON c.id = latest.max_id
        ORDER BY c.check_date DESC, i.sort_order, c.group_name
    '''

    rows = db.execute(query, params).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Date', 'Group', 'Checked By', 'Location', 'Item', 'Minimum', 'Quantity', 'Status', 'Note', 'Timestamp'])
    for row in rows:
        writer.writerow([row['check_date'], row['group_name'], row['checked_by'],
                         row['stock_place'], row['item_name'], row['minimum'],
                         row['quantity'], row['status'], row['note'], row['created_at']])

    filename = f'stock_check_{check_date or "all"}.csv'
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


# ============================================================
# Main
# ============================================================

if __name__ == '__main__':
    init_db()
    print('='*50)
    print('  Nano Lab Stock Check System')
    print('  http://127.0.0.1:5001')
    print('  Admin: admin / admin123')
    print('='*50)
    app.run(host='0.0.0.0', port=5001, debug=True)
