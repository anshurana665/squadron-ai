"""
demo_login_sqli.py
User Authentication Module — BuggyBank v1.0
CWE-89: SQL Injection (OWASP A03:2021)
"""

import sqlite3

DB_PATH = "users.db"


def setup_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'user'
        )
    """)
    cursor.execute("INSERT OR IGNORE INTO users VALUES (1, 'admin', 'secret123', 'admin')")
    cursor.execute("INSERT OR IGNORE INTO users VALUES (2, 'alice', 'pass456', 'user')")
    conn.commit()
    conn.close()


def login(username: str, password: str):
    """
    BUG (CWE-89): Direct string concatenation into SQL query.
    Attacker input:  username = "' OR '1'='1"
    Resulting query: SELECT * FROM users WHERE username='' OR '1'='1' AND password=''
    This bypasses authentication entirely.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # ❌ VULNERABLE — never do this!
    query = "SELECT * FROM users WHERE username='" + username + "' AND password='" + password + "'"
    print(f"[DEBUG] Executing: {query}")   # debug line makes the injection visible!

    cursor.execute(query)
    user = cursor.fetchone()
    conn.close()

    if user:
        print(f"✅ Login SUCCESS → Welcome, {user[1]}! Role: {user[3]}")
        return user
    else:
        print("❌ Login FAILED — Invalid credentials.")
        return None


def get_user_profile(user_id: str):
    """
    BUG (CWE-89): Same pattern in profile lookup.
    Attacker: user_id = "1 UNION SELECT username, password, password, role FROM users--"
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # ❌ VULNERABLE
    query = "SELECT * FROM users WHERE id=" + user_id
    cursor.execute(query)
    result = cursor.fetchall()
    conn.close()
    return result


if __name__ == "__main__":
    setup_db()

    print("=" * 50)
    print("SCENARIO 1: Normal Login")
    print("=" * 50)
    login("alice", "pass456")

    print("\n" + "=" * 50)
    print("SCENARIO 2: SQL Injection Attack")
    print("=" * 50)
    # This input bypasses the password check completely
    login("' OR '1'='1' --", "anything")

    print("\n" + "=" * 50)
    print("SCENARIO 3: UNION-based data dump via profile")
    print("=" * 50)
    rows = get_user_profile("1 UNION SELECT id, username, password, role FROM users--")
    print("Dumped rows:", rows)
