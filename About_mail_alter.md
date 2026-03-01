Here is the email sending logic exactly as it is written in your `app.py` file. I will display the code first, and then break down exactly how it works and what it means for your system.

### 1. The Core Email Sending Functions

In your `app.py`, the email logic is handled by two main internal functions: one for **Account Verification** and one for **Password Resets**.

Here is the exact code for the password reset email logic (the verification one is almost identical in structure):

```python
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

```

### 2. How the Logic Actually Works (Step-by-Step)

When a user triggers an email (like submitting the `/forgot_password` form), here is the exact sequence of events your program follows:

* **Step 1: Secure Token Generation:** Before the email function is even called, the system generates a secure, random 32-character string (`token = _secrets_mod.token_urlsafe(32)`).
* **Step 2: Database Logging:** This token is saved into your `email_tokens` database table, linked to the user's ID, categorized as a 'reset' or 'verify' token, and time-stamped with KST time.
* **Step 3: Dynamic URL Creation:** Inside the `_send_reset_email` function, Flask uses `url_for(..., _external=True)` to generate a complete, clickable internet link (e.g., `https://inhananomedic.pythonanywhere.com/reset_password_token/xyz123`).
* **Step 4: HTML Formatting:** The code injects the user's `display_name` and the `reset_url` into a pre-designed HTML template using Python f-strings.
* **Step 5: The "Lazy Import" Hand-off:** Notice the line `from email_utils import send_email`. This means `app.py` doesn't actually know *how* to talk to an email server (like Gmail or Outlook). It relies entirely on a separate file named `email_utils.py` to do the actual sending.
* **Step 6: "Fail Silently" Protection:** The whole thing is wrapped in a `try... except Exception: pass` block. This is a safety mechanism. If `email_utils.py` is missing, or if the email server crashes, your main website won't crash. It will just quietly skip sending the email and let the user continue using the site.

### 3. What about the "Duty Alerts"?

I noticed in the very top of your `app.py` file, the V4 description mentions: `V4: 12 corrections — ... email system, duty alerts.`.

However, **there is no logic in `app.py` that automatically sends duty alerts**.

**Why?** Web applications like Flask are "request-driven." They only do things when a user clicks a button or loads a page. To send an automated "Duty Alert" email every Wednesday night reminding a team it is their turn on Thursday, you cannot rely on `app.py` alone. You would need a separate Python script (often run by a server "Cron Job") that wakes up once a day, runs your `get_rotation_info()` function, and uses `email_utils.py` to blast out the alert.