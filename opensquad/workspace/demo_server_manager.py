"""
demo_server_manager.py
Remote Server Backup & Ping Utility — DevOps Helper v0.3
CWE-798: Hardcoded Credentials
CWE-78 : OS Command Injection (OWASP A03:2021)
"""

import subprocess
import os
import smtplib
from email.mime.text import MIMEText


# ─────────────────────────────────────────────────────────
# BUG #1 — CWE-798: HARDCODED CREDENTIALS
# These secrets are baked into source code.
# Anyone with repo access can steal DB, email, and cloud creds.
# ─────────────────────────────────────────────────────────
DB_HOST     = os.getenv("DB_HOST", "prod-db.internal.company.com")
DB_USER     = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

SMTP_HOST   = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_USER   = os.getenv("SMTP_USER", "devops@company.com")
SMTP_PASS   = os.getenv("SMTP_PASS", "")

AWS_KEY     = os.getenv("AWS_ACCESS_KEY_ID", "")
AWS_SECRET  = os.getenv("AWS_SECRET_ACCESS_KEY", "")


def send_alert(subject: str, body: str):
    """Send an alert email using the hardcoded credentials."""
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"]    = SMTP_USER
    msg["To"]      = "admin@company.com"

    with smtplib.SMTP_SSL(SMTP_HOST, 465) as server:
        server.login(SMTP_USER, SMTP_PASS)   # ❌ hardcoded creds in use
        server.send_message(msg)
    print(f"[ALERT] Email sent: {subject}")


# ─────────────────────────────────────────────────────────
# BUG #2 — CWE-78: OS COMMAND INJECTION
# User-controlled input is passed directly into shell=True.
# Attacker input: "8.8.8.8; rm -rf /"  or  "8.8.8.8 && cat /etc/passwd"
# ─────────────────────────────────────────────────────────
def ping_server(host: str):
    """
    Pings a server to check if it is alive.
    BUG: host is injected directly into os.system() without sanitization.
    """
    print(f"[INFO] Pinging host: {host}")

    # ❌ VULNERABLE — attacker controls the shell command
    command = "ping -c 2 " + host
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    return result.stdout


def backup_database(table_name: str, output_dir: str):
    """
    Exports a database table to a CSV backup file.
    BUG: both table_name and output_dir are passed unsanitized to shell.
    Attacker: table_name = "users; DROP TABLE users;--"
    """
    print(f"[INFO] Backing up table: {table_name}")

    # ❌ VULNERABLE
    cmd = f"mysqldump -u {DB_USER} -p{DB_PASSWORD} mydb {table_name} > {output_dir}/backup.sql"
    os.system(cmd)
    print("[INFO] Backup complete.")


if __name__ == "__main__":
    print("=" * 55)
    print("SCENARIO 1: Normal ping")
    print("=" * 55)
    output = ping_server("127.0.0.1")
    print(output[:200] if output else "(no output — likely Windows)")

    print("\n" + "=" * 55)
    print("SCENARIO 2: Command Injection Attack")
    print("=" * 55)
    # On Linux this would execute 'whoami' after the ping
    malicious_host = "127.0.0.1; echo '[INJECTED] whoami output:'; whoami"
    output = ping_server(malicious_host)
    print(output[:500] if output else "(no output)")

    print("\n" + "=" * 55)
    print("SCENARIO 3: Hardcoded secrets visible in memory/logs")
    print("=" * 55)
    print(f"DB_PASSWORD leaked → {DB_PASSWORD}")
    print(f"AWS_KEY     leaked → {AWS_KEY}")
    print(f"AWS_SECRET  leaked → {AWS_SECRET}")
