"""
Email utility for Nano Lab Stock Check System.
Sends verification, password reset, and duty alert emails via SMTP.
"""

import os
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

_config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'email_config.json')


def load_email_config():
    """Load SMTP configuration from email_config.json."""
    if not os.path.exists(_config_path):
        return None
    with open(_config_path, 'r') as f:
        return json.load(f)


def send_email(to_email, subject, html_body):
    """Send an email using SMTP settings from email_config.json.
    Returns True on success, error string on failure."""
    config = load_email_config()
    if not config:
        return 'Email not configured (email_config.json missing)'

    if config.get('sender_password', '') in ('', 'your-app-password-here'):
        return 'Email not configured (set sender_password in email_config.json)'

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = f"{config.get('sender_name', 'Stock Check')} <{config['sender_email']}>"
    msg['To'] = to_email

    msg.attach(MIMEText(html_body, 'html'))

    try:
        server = smtplib.SMTP(config['smtp_server'], config['smtp_port'])
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(config['sender_email'], config['sender_password'])
        server.sendmail(config['sender_email'], to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        return str(e)
