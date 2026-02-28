#!/usr/bin/env python3
"""
Duty Alert Email Sender for Nano Lab Stock Check System.

Run daily at 00:00 UTC (= 09:00 KST) via PythonAnywhere scheduled task.
Checks if today (KST) is a stock check day and sends reminder emails
to the on-duty group members who have verified email addresses.
"""

import os
import sys
import json
import sqlite3
from datetime import datetime, timezone, timedelta

# Add parent dir to path so we can import email_utils
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from email_utils import send_email

KST = timezone(timedelta(hours=9))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'stock_check.db')
CONFIG_PATH = os.path.join(BASE_DIR, 'teams_config.json')


def load_config():
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)


def get_duty_group_today(config):
    """Check if today (KST) is a check day. Returns team dict or None."""
    from datetime import date as date_type
    today = datetime.now(KST).date()
    start = date_type.fromisoformat(config['rotation_start'])
    interval = config['rotation_interval_days']
    order = config['rotation_order']
    teams = {t['key']: t for t in config['teams']}

    days_since = (today - start).days
    if days_since < 0:
        return None
    if days_since % interval != 0:
        return None  # Not a check day

    period = days_since // interval
    key = order[period % len(order)]
    return teams[key]


def main():
    config = load_config()
    team = get_duty_group_today(config)

    if not team:
        print(f"[{datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')} KST] Not a check day. No emails sent.")
        return

    print(f"[{datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')} KST] Check day! Duty group: Team {team['key']} ({team['name']})")

    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    members = db.execute(
        "SELECT display_name, email FROM users WHERE group_name = ? AND email_verified = 1 AND email IS NOT NULL AND email != ''",
        (team['name'],)
    ).fetchall()
    db.close()

    if not members:
        print(f"  No verified email addresses for {team['name']}. No emails sent.")
        return

    today_str = datetime.now(KST).strftime('%Y-%m-%d')
    subject = f"[Nano Lab] Stock Check Duty Reminder - {today_str}"

    for member in members:
        html_body = f"""
        <div style="font-family: sans-serif; max-width: 500px; margin: auto; padding: 20px;">
            <h2 style="color: #1a237e;">Stock Check Reminder</h2>
            <p>Hello <strong>{member['display_name']}</strong>,</p>
            <p>Today (<strong>{today_str}</strong>) is your group's stock check day.</p>
            <p>Group: <strong>Team {team['key']} ({team['name']})</strong></p>
            <p>Please log in and submit your stock check at your earliest convenience.</p>
            <hr style="border: none; border-top: 1px solid #ddd;">
            <p style="font-size: 12px; color: #888;">Nano Lab Stock Check System</p>
        </div>
        """
        result = send_email(member['email'], subject, html_body)
        if result is True:
            print(f"  Sent to {member['display_name']} ({member['email']})")
        else:
            print(f"  FAILED for {member['display_name']} ({member['email']}): {result}")


if __name__ == '__main__':
    main()
