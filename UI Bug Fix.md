Here is the organized report for the order pipeline visual bug. You can copy this directly and save it as a `.md` file (for example, `Bug_Fix_Order_Pipeline_Status.md`) to keep track of your UI corrections.

```markdown
# UI Bug Fix: Order Pipeline Status Display

**Component:** Dashboard (`dashboard.html`)
**Issue:** Visual inconsistency in the Order Pipeline columns.
**Reported:** 2026-03-01

---

## 1. The Situation

In the "Order Pipeline" section of the dashboard, there are three columns tracking an order's lifecycle: **Request**, **Decision**, and **Result**. 

When an Admin updates an order's status (e.g., changing it to "Ordered" or "Received"), the Decision and Result columns update correctly. However, the first column ("Request") continuously displays a bright orange **"Pending"** badge. This creates visual confusion, as a request cannot be "Pending" if it has already been "Ordered" or "Received".

---

## 2. The Root Cause (Problem Code)

The bug originates in `dashboard.html` under the `{# Pipeline Column 1: Request #}` section. 

The Jinja2 templating logic only checks *if an order exists* (`{% if order_info %}`), but it completely ignores the actual status of that order (`order_info.status`). Because the condition is met simply by the order existing, it lazily prints the hardcoded "Pending" HTML block every time.

**The Flawed Code (`dashboard.html`):**
```html
{# Pipeline Column 1: Request #}
<td style="text-align: center; font-size: 11px;">
    {% if order_info %}
        <span style="background: #ff9800; color: white; padding: 2px 8px; border-radius: 10px;">Pending</span>
        <br><small style="color:#555;">Qty: <strong>{{ order_info.quantity }}</strong></small>
        <br><small style="color:#888;">{{ order_info.requested_by }}</small>
        <br><small style="color:#999;">{{ order_info.date }}</small>
        {% if order_info.note %}<br><small style="color:#f57f17;">{{ order_info.note }}</small>{% endif %}
    {% else %}
        <span style="color: #ddd;">-</span>
    {% endif %}
</td>

```

---

## 3. The Proposed Solution

To fix this, we need to make the badge in the first column dynamic by evaluating `order_info.status`.

* If the status is actually `'pending'`, it should show the orange "Pending" badge.
* If the status is anything else (e.g., `'ordered'`, `'received'`, `'refused'`), the badge should change to a quiet, muted gray **"Requested"** badge. This acknowledges that the request was made in the past, pushing the user's visual attention to the active status in the Decision/Result columns.

**The Corrected Code (`dashboard.html`):**

```html
{# Pipeline Column 1: Request #}
<td style="text-align: center; font-size: 11px;">
    {% if order_info %}
        {% if order_info.status == 'pending' %}
            <span style="background: #ff9800; color: white; padding: 2px 8px; border-radius: 10px;">Pending</span>
        {% else %}
            <span style="background: #9e9e9e; color: white; padding: 2px 8px; border-radius: 10px;">Requested</span>
        {% endif %}
        
        <br><small style="color:#555;">Qty: <strong>{{ order_info.quantity }}</strong></small>
        <br><small style="color:#888;">{{ order_info.requested_by }}</small>
        <br><small style="color:#999;">{{ order_info.date }}</small>
        {% if order_info.note %}<br><small style="color:#f57f17;">{{ order_info.note }}</small>{% endif %}
    {% else %}
        <span style="color: #ddd;">-</span>
    {% endif %}
</td>

```

---

## 4. Expected Behavior After Fix

1. **New Request:** User requests an item. Column 1 shows an orange **Pending**. Columns 2 & 3 show waiting/in-progress text.
2. **Admin Orders:** Admin marks as "Ordered". Column 1 changes to a gray **Requested**. Column 2 shows a blue **Ordered**.
3. **Item Arrives:** Admin marks as "Received". Column 1 stays gray **Requested**. Column 2 stays blue **Ordered**. Column 3 shows a green **Received**.

This logical progression prevents contradictory statuses from appearing in the same row.

```
It is incredibly frustrating when you click "Save" in an admin panel, the system says "User updated," but the changes don't actually seem to apply where you need them to!

You are entirely correct that this is a flaw in your current setup. Even though the Admin Panel *appears* to let you change their `display_name` in the database, there are **three major structural reasons** why this modification has zero effect on the actual stock checks and orders.

Here is exactly what is happening under the hood:

### 1. Stock Checks Record the "Login ID", not the "Display Name"

When a user submits their daily stock check, the backend needs to record who did it. Look at the very beginning of your `submit_check()` function:

```python
@app.route('/submit_check', methods=['POST'])
@login_required
def submit_check():
    """UPSERT with validation..."""
    db = get_db()
    username = session.get('username', '') # <-- THE CULPRIT!

```

The system is grabbing their `username` (the ID they used to log in), not their `display_name`! So, even if the admin changes their display name to "Team B Member," the database will forever stamp their submissions with their login ID (e.g., "superman123").

### 2. The "Stale Cookie" Problem

For Order Requests, your system *does* try to use the Display Name:

```python
username = session.get('display_name', session.get('username', ''))

```

However, Flask uses **client-side session cookies** to remember who is logged in. When a user logs in, your server writes their custom display name into a cookie inside their browser.
If the Admin goes into the database and updates their `display_name`, **the user's browser cookie does not magically update.** Until that user clicks "Logout" and logs back in, their browser will keep submitting the old, incorrect name to the server.

### 3. Historical Data is "Hard-Printed"

In your database architecture, when a stock check or order request is made, the person's name is saved as plain text directly into the `checks_2026_03` or `order_requests` table. It is not linked to their User ID.
This means if a user makes 10 requests under a fake name, and the Admin changes their name today, those 10 past requests will permanently display the old fake name.

---

### How we fix this in the V5 Upgrade

To solve this so the Admin has absolute control, we need to do two things in our upcoming V5 code:

1. **Fix the Data Source:** We will change `submit_check` and `create_order_request` so that instead of reading the browser's session cookie, they query the `users` database table *at the exact moment of submission* to grab the most up-to-date `display_name`.
2. **Build the "Sync" Button:** As you requested earlier, we will add a button in the Admin Panel that forces the `display_name` to exactly match the `group_name` in the database, overriding whatever arbitrary name the student typed during registration.
