# Nano Lab Stock Check System V4 — Full Documentation

> **Version:** V4 (Feb 28, 2026)
> **Live URL:** https://inhananomedic.pythonanywhere.com
> **Author:** Zhijun (Admin)
> **Tech Stack:** Python Flask + SQLite + Jinja2 + vanilla JavaScript

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [File Structure](#2-file-structure)
3. [Database Schema](#3-database-schema)
4. [Routes & API](#4-routes--api)
5. [Data Flow & User Interaction](#5-data-flow--user-interaction)
6. [Permission Matrix](#6-permission-matrix)
7. [Key Behaviors & Features](#7-key-behaviors--features)
8. [Order Pipeline (3-Column)](#8-order-pipeline-3-column)
9. [Rotation Schedule](#9-rotation-schedule)
10. [Email System](#10-email-system)
11. [Config Files](#11-config-files)
12. [Deployment (PythonAnywhere)](#12-deployment-pythonanywhere)
13. [34 Pre-loaded Items](#13-34-pre-loaded-items)
14. [5 Teams](#14-5-teams)
15. [Accounts](#15-accounts)
16. [Version History](#16-version-history)
17. [V4 12-Item Correction Summary](#17-v4-12-item-correction-summary)

---

## 1. System Overview

A web-based stock checking system for **Inha University Nano Lab**. 5 teams (11 members) take turns every 2 weeks on Thursdays to check lab consumable inventory across 4 storage locations (4C refrigerator, Cell room Drawer, 5th floor Drawer, Dr.Lee personal).

**What it does:**
- Members log in, enter item quantities on their assigned check day
- System auto-compares each quantity against the minimum threshold
- Color-codes status: **Green** (OK), **Yellow** (Low), **Red** (Empty)
- Items below minimum trigger an order request pipeline: Request → Decision → Result
- Admin manages users, items, order approvals, and can export CSV

**Key design principles:**
- Partial submission OK (not all items required per visit)
- Number-only input with unit labels from minimum
- Enter key checks quantity but does NOT submit the form
- 9999 = infinity (always OK, displays ∞)
- All timestamps in KST (Korea Standard Time, UTC+9)
- Monthly partitioned check tables for scalability

---

## 2. File Structure

```
stock_check_system/
│
├── app.py                         # Flask application (1,328 lines) — ALL routes, DB, auth
├── app_v3_backup.py               # V3 backup (safety copy)
├── stock_check.db                 # SQLite database (auto-created on first run)
├── .secret_key                    # Random Flask secret key (auto-generated, persistent)
│
├── teams_config.json              # Team A-E config + rotation schedule
├── email_config.json              # Gmail SMTP credentials (App Password)
├── email_utils.py                 # send_email(to, subject, html_body) utility
├── send_duty_alert.py             # 9am KST daily reminder (PythonAnywhere scheduled task)
│
└── templates/                     # 10 Jinja2 templates
    ├── base.html                  # Layout: nav bar, CSS, flash messages, {% block content %}
    ├── login.html                 # Login form + "Forgot password?" link
    ├── register.html              # Registration with email field + team selector
    ├── dashboard.html             # Main stock check table (529 lines, most complex)
    ├── history.html               # Paginated check history with group/date filters
    ├── orders.html                # Order request management (all statuses)
    ├── admin.html                 # User management panel (approve/edit/delete/reset PW)
    ├── admin_items.html           # Item CRUD (min_value + min_unit split fields)
    ├── forgot_password.html       # Email input for password reset request
    └── reset_password_form.html   # New password form (from email link)
```

---

## 3. Database Schema

All tables live in a single file: `stock_check.db`

### 3.1 `users`

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | INTEGER | PK AUTO | Unique user ID |
| `username` | TEXT UNIQUE | — | Login username |
| `password_hash` | TEXT | — | Werkzeug password hash |
| `display_name` | TEXT | '' | Name shown in UI |
| `group_name` | TEXT | '' | Team name (e.g. "Dr.Lee/Zhijun") |
| `role` | TEXT | 'member' | "admin" or "member" |
| `approved` | INTEGER | 0 | 0 = pending admin approval, 1 = active |
| `email` | TEXT | '' | For verification and password reset |
| `email_verified` | INTEGER | 0 | 0 = unverified, 1 = verified |
| `created_at` | TEXT | '' | KST timestamp "YYYY-MM-DD HH:MM:SS" |

### 3.2 `items` (34 pre-loaded)

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | INTEGER | PK AUTO | Unique item ID |
| `stock_place` | TEXT | — | Storage location |
| `item_name` | TEXT | — | Item name with product code |
| `minimum` | TEXT | '' | Original text "6 bottles" |
| `min_value` | REAL | NULL | Parsed number: 6.0 |
| `min_unit` | TEXT | '' | Parsed unit: "bottles" |
| `category` | TEXT | 'Common' | "Common" or "Dr.Lee" |
| `sort_order` | INTEGER | 0 | Display order in dashboard |

### 3.3 `checks_YYYY_MM` (monthly partitioned)

One table per month, e.g. `checks_2026_02`, `checks_2026_03`, etc.

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | INTEGER | PK AUTO | Unique check record ID |
| `item_id` | INTEGER | FK→items | Which item was checked |
| `group_name` | TEXT | — | Which team submitted |
| `checked_by` | TEXT | — | Username who submitted |
| `quantity` | TEXT | '' | Entered quantity (stored as text) |
| `status` | TEXT | 'unknown' | Computed: ok / low / empty / unknown |
| `note` | TEXT | '' | Optional note from user |
| `check_date` | TEXT | — | Target date "YYYY-MM-DD" |
| `created_at` | TEXT | '' | KST submission timestamp |

**Indexes:** `idx_checks_YYYY_MM_item_group` (item_id, group_name), `idx_checks_YYYY_MM_date` (check_date)

### 3.4 `order_requests`

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | INTEGER | PK AUTO | Unique order ID |
| `item_id` | INTEGER | FK→items | Which item to order |
| `requested_by` | TEXT | — | Who created the request |
| `requested_by_group` | TEXT | '' | Their team |
| `quantity_needed` | TEXT | '' | How many to order |
| `status` | TEXT | 'pending' | pending / ordered / received / cancelled / refused |
| `note` | TEXT | '' | Optional note |
| `ordered_by` | TEXT | '' | Who marked as "ordered" (admin) |
| `ordered_at` | TEXT | '' | When marked as "ordered" |
| `resolved_by` | TEXT | '' | Who set final status |
| `resolved_at` | TEXT | '' | When final status was set |
| `created_at` | TEXT | '' | KST creation timestamp |

### 3.5 `email_tokens`

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | INTEGER | PK AUTO | Token ID |
| `user_id` | INTEGER | FK→users | Token owner |
| `email` | TEXT | '' | Target email address |
| `token` | TEXT | — | URL-safe random token (32 bytes) |
| `token_type` | TEXT | 'verify' | "verify" or "reset" |
| `created_at` | TEXT | '' | KST timestamp |
| `used` | INTEGER | 0 | 0 = unused, 1 = consumed |

### 3.6 `checks_legacy`

Renamed from old V3 `checks` table after migration to monthly tables. Kept as backup, not actively queried.

### 3.7 Data Relationships

```
users.group_name ──────────── teams_config.json (team name)
items.id ──────────────────── checks_YYYY_MM.item_id (FK)
items.id ──────────────────── order_requests.item_id (FK)
users.id ──────────────────── email_tokens.user_id (FK)
items.category ────────────── "Common" (all groups) or "Dr.Lee" (Dr.Lee/Zhijun only)
order_requests.status ─────── Pipeline: pending → ordered → received/cancelled/refused
```

---

## 4. Routes & API

### 4.1 Public Routes (No Login Required)

| Route | Method | Function | Description |
|-------|--------|----------|-------------|
| `/login` | GET/POST | `login()` | Login form; validates credentials + approval status |
| `/register` | GET/POST | `register()` | Registration; sends verification email if email provided |
| `/verify_email/<token>` | GET | `verify_email()` | Click from email → sets email_verified = 1 |
| `/forgot_password` | GET/POST | `forgot_password()` | Enter email → sends reset link (1h expiry) |
| `/reset_password_token/<token>` | GET/POST | `reset_password_token()` | Set new password from email link |

### 4.2 Authenticated Routes (Login Required)

| Route | Method | Function | Description |
|-------|--------|----------|-------------|
| `/` | GET | `dashboard()` | Main stock check table; accepts `?date=YYYY-MM-DD` |
| `/submit_check` | POST | `submit_check()` | UPSERT check data (DELETE + INSERT per group+date) |
| `/order_request` | POST | `create_order_request()` | Create new order request for an item |
| `/orders` | GET | `orders()` | View all order requests; accepts `?status=` filter |
| `/orders/update/<id>` | POST | `update_order()` | Change order status (with permission checks) |
| `/logout` | GET | `logout()` | Clear session, redirect to login |

### 4.3 Admin Routes (Admin Role Required)

| Route | Method | Function | Description |
|-------|--------|----------|-------------|
| `/admin` | GET | `admin_panel()` | User management table |
| `/admin/approve/<id>` | POST | `approve_user()` | Approve pending user |
| `/admin/delete_user/<id>` | POST | `delete_user()` | Delete user (can't delete self) |
| `/admin/update_user/<id>` | POST | `update_user()` | Edit role, group, display name |
| `/admin/reset_password/<id>` | POST | `reset_password()` | Admin resets user's password |
| `/admin/delete_check/<id>` | POST | `delete_check()` | Delete single check record |
| `/admin/delete_checks_bulk` | POST | `delete_checks_bulk()` | Delete all checks for group+date |
| `/admin/items` | GET | `admin_items()` | Item management page |
| `/admin/items/add` | POST | `add_item()` | Add new item |
| `/admin/items/edit/<id>` | POST | `edit_item()` | Edit item details |
| `/admin/items/delete/<id>` | POST | `delete_item()` | Delete item |
| `/export` | GET | `export_csv()` | CSV export with UTF-8 BOM; accepts `?date=` |

---

## 5. Data Flow & User Interaction

### 5.1 Dashboard Load (`GET /`)

```
User opens / (or /?date=2026-02-28)
  │
  ├── 1. Load all items (SELECT * FROM items ORDER BY sort_order)
  │
  ├── 2. Determine check_date (from ?date param, or today KST)
  │
  ├── 3. Determine monthly table: checks_YYYY_MM
  │      (e.g. 2026-02-28 → checks_2026_02)
  │
  ├── 4. Query latest checks per (item_id, group) for that date
  │      → latest_checks = {(item_id, group_name): check_record}
  │      Uses MAX(id) subquery to get only the newest entry
  │
  ├── 5. Query ALL order requests, newest first
  │      → pending_orders = {item_id: {status, qty, requested_by, ...}}
  │      Only keeps the LATEST order per item (first seen in DESC order)
  │
  ├── 6. Compute summary stats:
  │      OK count, Low count, Empty count, groups checked, pending orders, ordered
  │
  ├── 7. Get last_checked date per group (scans ALL monthly tables)
  │
  ├── 8. Compute rotation info from teams_config.json
  │      → duty group, check date, next check date, next group
  │
  ├── 9. Organize items by stock_place for section headers
  │
  └── 10. Render dashboard.html with:
          items, latest_checks, pending_orders, summary, rotation info,
          can_edit (true if date >= today OR admin)
```

### 5.2 Submit Check (`POST /submit_check`)

```
User fills quantity inputs → clicks "Submit Stock Check" button
  │
  ├── Guard: past date + non-admin? → REJECT with flash message
  │
  ├── For each item in items table:
  │   ├── Dr.Lee item + non-Dr.Lee group? → SKIP entirely
  │   ├── Empty input? → SKIP (partial submission OK)
  │   ├── Not a valid number? → ADD to errors list
  │   └── Valid number? → compute_status(qty, min_value) → ok/low/empty
  │
  ├── Any errors? → flash errors, redirect back (nothing saved)
  ├── Zero entries? → flash warning, redirect back
  │
  └── UPSERT:
      ├── DELETE FROM checks_YYYY_MM WHERE group_name = ? AND check_date = ?
      └── INSERT all valid entries with KST timestamp
```

### 5.3 Order Request Creation (`POST /order_request`)

```
User clicks "Need Order" button on dashboard
  │
  ├── Order modal opens (item name, minimum pre-filled)
  ├── User enters quantity (number only, validated) + optional note
  ├── Clicks "Submit Order Request"
  │
  ├── Guard: existing pending/ordered request for this item? → REJECT
  │
  └── INSERT INTO order_requests (item_id, requested_by, group, qty, note, created_at)
      → status = 'pending'
```

### 5.4 Order Status Update (`POST /orders/update/<id>`)

```
On Orders page, admin/user clicks status button
  │
  ├── Validate new_status is valid enum
  ├── Permission checks:
  │   ├── ordered/received/refused → admin only
  │   └── cancelled → own group OR admin
  │
  └── UPDATE order_requests:
      ├── If "ordered": SET ordered_by, ordered_at
      ├── If "received"/"cancelled"/"refused": SET resolved_by, resolved_at
      └── If "pending": SET status only
```

### 5.5 Frontend Validation (dashboard.html JavaScript)

```
Enter key pressed on quantity input:
  ├── e.preventDefault() — blocks form submission
  └── checkQtyVsMin(input):
      ├── Empty? → clear cell color
      ├── Invalid/negative? → red cell + red border
      ├── qty == 9999? → green cell (infinity)
      ├── qty == 0? → red cell (empty)
      ├── qty < min_value? → yellow cell (low)
      └── qty >= min_value? → green cell (ok)

Submit button clicked:
  └── validateForm():
      ├── Count filled inputs
      ├── Zero filled? → alert "enter at least one quantity"
      ├── Any non-number? → alert with list of invalid items
      └── All valid? → allow form submission
```

---

## 6. Permission Matrix

| Action | Regular User | Admin |
|--------|-------------|-------|
| View dashboard | Yes (any date) | Yes |
| Submit check (today/future dates) | Own group only | Any group |
| Submit check (past dates) | **BLOCKED** | Allowed |
| View other groups' data | Read-only | Read-only |
| Create order request | If item needs order + no active order exists | Same |
| Cancel order request | Own group's orders only | Any order |
| Mark order as "ordered" | No | Yes |
| Mark order as "received" | No | Yes |
| Mark order as "refused" | No | Yes |
| View order history | Yes | Yes |
| Delete check records | No | Yes |
| Export CSV | No | Yes |
| Manage users (approve/edit/delete) | No | Yes |
| Manage items (add/edit/delete) | No | Yes |
| Reset other users' passwords | No | Yes |

---

## 7. Key Behaviors & Features

### 7.1 9999 = Infinity (Item A)

- Any quantity entered as `9999` is treated as "always OK"
- `compute_status()` returns `'ok'` immediately for `qty == 9999`
- Dashboard displays **∞** instead of "9999"

### 7.2 Number-Only Input (Item 1)

- Dashboard uses `<input type="number" min="0" step="1">`
- Unit label displayed beside input (from `items.min_unit`)
- Admin Items page: minimum split into separate **Value** and **Unit** fields
- Backend: `min_value` (REAL) + `min_unit` (TEXT) parsed from legacy `minimum` text

### 7.3 Notes via Modal (Item 2)

- Each item row has a `+Note` / `Note*` button (not inline text input)
- Clicking opens a modal with textarea
- **Save Draft**: stores in browser `localStorage` as `note_draft_{itemId}` (survives page refresh)
- **Confirm**: copies text to hidden `<input name="note_{itemId}">`, clears localStorage draft
- On page load: buttons show "Draft*" with orange background if localStorage draft exists
- Notes submitted with the form, stored in checks table

### 7.4 Partial Submission (Item 3)

- Users do NOT need to fill every item — only filled items are validated and saved
- If a value IS entered, it must be a valid non-negative number (reject "three", "-5", etc.)
- Dr.Lee items (Tips 1000/200/10uL) are completely skipped for non-Dr.Lee groups
- At least 1 item must be filled to submit

### 7.5 Status Legend at Top (Item 4)

- Legend block placed above the data table (after Summary Bar)
- Shows: OK (green), Low (yellow), Empty (red), ∞ = 9999 (blue)
- Right side: live Seoul clock (Asia/Seoul timezone, updates every second)

### 7.6 KST Timestamps (Item 5)

- All `datetime.now()` calls use `datetime.now(KST)` where `KST = timezone(timedelta(hours=9))`
- Formatted as `'YYYY-MM-DD HH:MM:SS'`
- Explicit `created_at` in all INSERTs (not relying on SQLite DEFAULT)
- Client-side: live clock uses `toLocaleString('en-GB', {timeZone: 'Asia/Seoul'})`

### 7.7 Monthly DB Tables (Item 6)

- Check data partitioned into `checks_2026_02`, `checks_2026_03`, etc.
- `get_checks_table(date)` → returns table name from date
- `ensure_checks_table(db, name)` → CREATE TABLE IF NOT EXISTS + indexes
- `validate_checks_table_name(name)` → regex `^checks_\d{4}_\d{2}$` (SQL injection prevention)
- History page: UNION ALL across all `checks_*` tables
- Old V3 `checks` table migrated to monthly tables, renamed to `checks_legacy`

### 7.8 CSV Export with BOM (Item 7)

- UTF-8 BOM (`\ufeff`) prepended for Excel compatibility with Korean characters
- Columns: Date, Group, Checked By, Location, Item, Minimum, Quantity, Status, Note, Timestamp (KST)
- Only exports latest record per item+group+date (deduplication via MAX(id))
- Admin-only feature

### 7.9 Enter Key Behavior

- **Enter key does NOT submit the form** — only the Submit button can submit
- `keydown` listener on `#checkForm`: `e.preventDefault()` when `e.key === 'Enter'`
- **But**: if pressed on a quantity input (`qty_*`), calls `checkQtyVsMin()` to instantly color-code the cell
- This was a **critical user requirement** — auto-submit on Enter was explicitly forbidden

### 7.10 Past Date Editing

- **Non-admin users**: can only submit checks for today or future dates
- **Admin**: can submit checks for any date including past
- Controlled by `can_edit` variable: `check_date >= today_kst().isoformat() or role == 'admin'`
- When `can_edit` is false: inputs hidden, read-only display shown, submit button replaced with "Past date — view only" message
- Backend guard in `submit_check()` also enforces this

---

## 8. Order Pipeline (3-Column)

The old single "Status" column was split into 3 pipeline columns for clarity:

### Dashboard Table Headers

```
# | Item | Minimum | Team A | Team B | Team C | Team D | Team E | Order | Request | Decision | Result
```

### 8.1 Order Column

Pure comparison result — does NOT show workflow status.

| Condition | Display |
|-----------|---------|
| Any group reports qty < minimum, no active order | **"Need Order"** button (red, clickable → opens order modal) |
| Any group reports qty < minimum, active order exists | **"Need Order"** badge (red, non-clickable) |
| All groups OK | **"OK"** (green text) |
| No checks yet | **"-"** (grey) |

"Active order" = status is `pending` or `ordered` (not received/cancelled/refused).

### 8.2 Request Column (Pipeline Stage 1)

Always shows the initial request info if any order exists for this item.

| Condition | Display |
|-----------|---------|
| Order exists (any status) | **Pending** badge (orange) + Qty + Requester + Date + Note |
| No order | **"-"** |

### 8.3 Decision Column (Pipeline Stage 2)

Shows the admin's decision.

| Condition | Display |
|-----------|---------|
| Status = ordered | **Ordered** badge (blue) + ordered_by + ordered_at |
| Status = received | **Ordered** badge (blue) + ordered_by + ordered_at (was ordered before received) |
| Status = refused | **Refused** badge (brown) + resolved_by + resolved_at |
| Status = pending | *"Waiting..."* (grey italic) |
| No order | **"-"** |

### 8.4 Result Column (Pipeline Stage 3)

Shows the final outcome.

| Condition | Display |
|-----------|---------|
| Status = received | **Received** badge (green) + resolved_by + resolved_at |
| Status = cancelled | **Cancelled** badge (grey) + resolved_by + resolved_at |
| Status = pending or ordered | *"In progress..."* (grey italic) |
| Status = refused | *"Closed"* (brown text) |
| No order | **"-"** |

### 8.5 Order State Machine

```
                    ┌─── cancelled (own group / admin)
                    │
pending ──── ordered ──── received (admin only)
   │            │
   │            └──── cancelled (own group / admin)
   │
   └──── refused (admin only)
   │
   └──── cancelled (own group / admin)
```

**Who records what:**
- `pending`: created_at, requested_by, requested_by_group
- `ordered`: ordered_by, ordered_at (admin action)
- `received`/`cancelled`/`refused`: resolved_by, resolved_at

---

## 9. Rotation Schedule

### Configuration (`teams_config.json`)

```json
{
    "rotation_start": "2026-02-26",
    "rotation_interval_days": 14,
    "rotation_order": ["A", "B", "C", "D", "E"]
}
```

### Logic (`get_rotation_info()`)

```
days_since = (for_date - rotation_start).days
period = days_since // 14
team_index = period % 5
check_date = start + (period * 14 days)
next_check_date = start + ((period + 1) * 14 days)
```

### Schedule (First Cycle)

| Date | Duty Team |
|------|-----------|
| 2026-02-26 (Thu) | Team A: Dr.Lee/Zhijun |
| 2026-03-12 (Thu) | Team B: Dr.Yoo/Dahee |
| 2026-03-26 (Thu) | Team C: Junhyun/Thuan |
| 2026-04-09 (Thu) | Team D: Dr.Arjaree/Nattha |
| 2026-04-23 (Thu) | Team E: Dr.Kim/윤현승 |
| 2026-05-07 (Thu) | Team A: Dr.Lee/Zhijun (cycle repeats) |

### Dashboard Banner

- Green background + green border when viewing user's group is on duty
- Shows: `Check Day (YYYY-MM-DD): Team X (group_name)`
- Shows: `Next: YYYY-MM-DD — Team Y (group_name)`
- On-duty group's column header turns green with "ON DUTY" label

---

## 10. Email System

### 10.1 Components

| File | Purpose |
|------|---------|
| `email_config.json` | SMTP credentials (Gmail App Password) |
| `email_utils.py` | `send_email(to, subject, html_body)` — shared utility |
| `send_duty_alert.py` | Standalone daily reminder script |

### 10.2 Email Verification Flow

```
1. User registers with email
2. System generates URL-safe token (32 bytes)
3. Token saved to email_tokens (type='verify')
4. Verification email sent with link: /verify_email/<token>
5. User clicks link → email_verified = 1, token marked used
6. Admin still needs to approve the account separately
```

### 10.3 Password Reset Flow

```
1. User clicks "Forgot password?" on login page
2. Enters email address
3. System checks: user exists + email_verified = 1
4. Generates reset token (type='reset'), saves to email_tokens
5. Sends email with link: /reset_password_token/<token>
6. Link expires after 1 hour (checked via created_at)
7. User clicks link → enters new password → hash updated
8. Always shows same message regardless of email existence (anti-enumeration)
```

### 10.4 Duty Alert (send_duty_alert.py)

```
Runs daily at 00:00 UTC (= 09:00 KST) via PythonAnywhere scheduled task

1. Load teams_config.json
2. Check: is today (KST) a check day?
   - Calculate days_since rotation_start
   - If days_since % interval != 0 → exit (not a check day)
3. Find on-duty team
4. Query users: group_name matches + email_verified = 1 + email not empty
5. Send reminder email to each member
6. Log results to stdout
```

### 10.5 SMTP Configuration

```json
{
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "sender_email": "karolinysyy@gmail.com",
    "sender_password": "<Gmail App Password>",
    "sender_name": "Nano Lab Stock Check"
}
```

**Important:** Must use Gmail **App Password** (16-char code), NOT regular password. Regular password returns error 534.

---

## 11. Config Files

### 11.1 `teams_config.json`

- Defines 5 teams: key (A-E), name, members (currently empty, not used)
- Rotation settings: start date, interval (14 days), rotation order
- Read once at app startup by `load_teams_config()`
- Used by: `get_groups()`, `get_teams_display()`, `get_team_key_for_group()`, `get_rotation_info()`

### 11.2 `email_config.json`

- Gmail SMTP server, port, sender email, sender password, sender name
- Read by `email_utils.py` on every `send_email()` call
- Fails silently if file missing or password not set (app works without email)

### 11.3 `.secret_key`

- Auto-generated random 32-byte hex string on first run
- Persistent across restarts (stored in file, not hardcoded)
- Used as Flask `app.secret_key` for session cookies

---

## 12. Deployment (PythonAnywhere)

### 12.1 Server Details

| Setting | Value |
|---------|-------|
| Username | `InhaNanoMedic` |
| API Token | `61b5985ac78133e7c455de03c3ea91d3c2e2b9c5` |
| App Path | `/home/InhaNanoMedic/stock_check_system/` |
| Templates Path | `/home/InhaNanoMedic/stock_check_system/templates/` |
| Python Version | `python310` |
| Live URL | `https://inhananomedic.pythonanywhere.com` |

### 12.2 Upload via API

```
POST https://www.pythonanywhere.com/api/v0/user/InhaNanoMedic/files/path/home/InhaNanoMedic/stock_check_system/<filename>
Content-Type: multipart/form-data
Authorization: Token 61b5985ac78133e7c455de03c3ea91d3c2e2b9c5

Field: content = <file data>
```

**Critical:** Must use `multipart/form-data` (NOT `application/octet-stream` — returns 415 error).

### 12.3 Reload After Upload

```
POST https://www.pythonanywhere.com/api/v0/user/InhaNanoMedic/webapps/inhananomedic.pythonanywhere.com/reload/
Authorization: Token 61b5985ac78133e7c455de03c3ea91d3c2e2b9c5
```

### 12.4 Deployment Rules

1. **NEVER delete `stock_check.db` on server** — users lose accounts and all data
2. Upload only `.py` and `.html` files, then reload
3. **Correct path:** `/home/InhaNanoMedic/stock_check_system/` (NOT `mysite/`)
4. After upload + reload: **verify rendered page** contains expected changes
5. Use Python `urllib` for testing (not `curl` — `!` in passwords breaks shell)
6. Jinja `{# comments #}` don't appear in rendered HTML; JS `// comments` do

### 12.5 Scheduled Task

| Setting | Value |
|---------|-------|
| Command | `/home/InhaNanoMedic/.virtualenvs/myvirtualenv/bin/python /home/InhaNanoMedic/stock_check_system/send_duty_alert.py` |
| Schedule | Daily at 00:00 UTC (= 09:00 KST) |
| Purpose | Send duty reminder emails |

---

## 13. 34 Pre-loaded Items

### 4°C Refrigerator (2 items)

| # | Item | Minimum |
|---|------|---------|
| 1 | DMEM(LM001-05) | 6 bottles |
| 2 | RPMI(sh30255.01) | 6 bottles |

### Cell Room Drawer (11 items)

| # | Item | Minimum |
|---|------|---------|
| 3 | Microscope slide | 4 cases |
| 4 | cover glass | 4 cases |
| 5 | 100mm dish(20101) | 1 box(full) |
| 6 | 150mm dish(20150) | 1 box(full) |
| 7 | T75(70075) | 1 box(full) |
| 8 | T25(70025) | 1 box(full) |
| 9 | 6well(30006) | 1 box(full) |
| 10 | 12well(30012) | 1 box(full) |
| 11 | 24well(30024) | 1 box(full) |
| 12 | 96well(30096) | 1 box(full) |
| 13 | cryovials(50pieces) | 5 bags |

### 5th Floor Drawer (18 items)

| # | Item | Minimum |
|---|------|---------|
| 14 | conical tube 15ml | 1 box(full) |
| 15 | conical tube 50ml | 1 box(full) |
| 16 | gloves(XS) | 4 boxes |
| 17 | gloves(S) | 4 boxes |
| 18 | gloves(M) | 4 boxes |
| 19 | gloves(L) | 4 boxes |
| 20 | Reservoir Channel 1 | 1 box(full) |
| 21 | Reservoir Channel 2 | 1 box(full) |
| 22 | eptube | 4 boxes(full) |
| 23 | pipets 5ml(91005) | 4 boxes(full) |
| 24 | pipets 10ml(91010) | 4 boxes(full) |
| 25 | pipets 25ml(91025) | 4 boxes(full) |
| 26 | DPBS(LB001-02) | 4 bottles(full) |
| 27 | kim tech | 1 box(full) |
| 28 | paper towel | 1 box(full) |
| 29 | FBS | 3 bottles |
| 30 | Anti-Anti | 3 bottles |
| 31 | Trypsin | 3 bottles |

### Dr.Lee Personal (3 items — Dr.Lee/Zhijun group only)

| # | Item | Minimum |
|---|------|---------|
| 32 | Tip 1000uL | 2 bags |
| 33 | Tip 200uL | 2 bags |
| 34 | Tip 10uL | 2 bags |

---

## 14. 5 Teams

| Key | Team Name | Members |
|-----|-----------|---------|
| A | Dr.Lee/Zhijun | Admin group |
| B | Dr.Yoo/Dahee | — |
| C | Junhyun/Thuan | — |
| D | Dr.Arjaree/Nattha | — |
| E | Dr.Kim/윤현승 | — |

### Name Migrations (V3 → V4)

| Old Name | New Name |
|----------|----------|
| Dr.yoo/dahee | Dr.Yoo/Dahee |
| junhyun/thuan | Junhyun/Thuan |
| Dr.azary/nattha | Dr.Arjaree/Nattha |

Migration runs automatically in `init_db()` — updates `users.group_name`, all monthly `checks_*` tables, and `order_requests.requested_by_group`.

---

## 15. Accounts

| Username | Password | Role | Group | Notes |
|----------|----------|------|-------|-------|
| `admin` | `Zhijun0302!` | admin | Dr.Lee/Zhijun | Full system access |
| `KJM` | (set by user) | member | Dr.Kim/윤현승 | Test user |

Default admin created in `init_db()` with password `admin123` (changed to `Zhijun0302!` on live server).

---

## 16. Version History

| Version | Date | Key Changes |
|---------|------|-------------|
| **V1** | Feb 2026 | Initial release. Bug: duplicate records on every submit (INSERT without DELETE). |
| **V2** | Feb 2026 | UPSERT fix (DELETE+INSERT), admin modal for user edits, CSV dedup. |
| **V3** | Feb 2026 | Reset PW via proper modal, CSS `position:sticky` removed, order date display added. |
| **V4** | Feb 28, 2026 | **Major upgrade** — 12-item correction plan. See section 17 below. |

---

## 17. V4 12-Item Correction Summary

| # | Feature | Status | Description |
|---|---------|--------|-------------|
| A | 9999 = infinity | Done | Always OK, displays ∞ |
| B | Biweekly Thursday rotation | Already in V3 | No change needed |
| 1 | Number-only input | Done | `<input type="number">` + unit label from min_unit |
| 2 | Notes via modal | Done | Button → modal + localStorage draft |
| 3 | Partial submission | Done | Validates filled fields only; rejects non-numbers |
| 4 | Status Legend at top | Done | Moved from bottom to above the table |
| 5 | KST timestamps | Done | All times in UTC+9 "YYYY-MM-DD HH:MM:SS" |
| 6 | Monthly DB tables | Done | `checks_YYYY_MM` partitioning |
| 7 | CSV UTF-8 BOM | Done | Excel-compatible Korean character export |
| 8 | Order column split | Done | OK / Need Order (pure comparison) |
| 9 | Status → 3-column pipeline | Done | Request / Decision / Result |
| 10 | Email system | Done | Registration verification + password reset |
| 11 | Duty alert email | Done | 9am KST daily (PythonAnywhere scheduled task) |
| 12 | Team A-E naming | Done | `teams_config.json` + group name migration |

### Additional V4 Fixes (Post-Launch)

| Fix | Description |
|-----|-------------|
| Enter key blocking | Block form submit; Enter checks qty vs minimum instead |
| Past date blocking | Non-admin cannot submit for past dates; future dates OK |
| Order modal validation | Quantity field rejects non-numbers |
| Live Seoul clock | Asia/Seoul timezone in legend area |
| ordered_by/ordered_at | Track who/when marked order as "ordered" |
| "Need Order" button logic | Clickable only when no active (pending/ordered) order exists |

---

## Appendix: Context Processor Variables

The `inject_globals()` function adds these variables to **every** template:

| Variable | Type | Description |
|----------|------|-------------|
| `current_user` | str | Session display_name |
| `current_role` | str | "admin" or "member" |
| `current_group` | str | Session group_name |
| `groups` | list[str] | All 5 group names |
| `teams_display` | list[dict] | [{key: "A", name: "Dr.Lee/Zhijun"}, ...] |
| `get_team_key` | function | group_name → team key (A-E) |
| `now_kst` | str | Current time "HH:MM:SS" (server-rendered) |
| `now_kst_date_full` | str | Current date "Wednesday, 28 February 2026" (server-rendered) |

---

*Document generated: Feb 28, 2026*
