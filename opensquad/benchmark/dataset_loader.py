"""
opensquad/benchmark/dataset_loader.py
Built-in OWASP Top 10 vulnerability dataset for EVPC benchmarking.
10 real-world vulnerability patterns — no internet required.
"""

DATASET: list[dict] = [

    # ─── CWE-89 : SQL Injection (3 variants) ───────────────────────

    {
        "filename":            "sqli_basic.py",
        "vulnerability_type":  "SQL Injection",
        "cwe_id":              "CWE-89",
        "owasp_category":      "A03:2021",
        "severity":            "CRITICAL",
        "cvss_score":          9.8,
        "expected_fix_pattern":"parameterized",
        "vulnerable_code": """\
import sqlite3

def get_user(username):
    conn   = sqlite3.connect("users.db")
    cursor = conn.cursor()
    query  = "SELECT * FROM users WHERE name = '" + username + "'"
    cursor.execute(query)
    return cursor.fetchall()
""",
    },

    {
        "filename":            "sqli_login.py",
        "vulnerability_type":  "SQL Injection",
        "cwe_id":              "CWE-89",
        "owasp_category":      "A03:2021",
        "severity":            "CRITICAL",
        "cvss_score":          9.8,
        "expected_fix_pattern":"parameterized",
        "vulnerable_code": """\
import sqlite3

def login(username, password):
    conn   = sqlite3.connect("app.db")
    cursor = conn.cursor()
    sql    = f"SELECT * FROM users WHERE username='{username}' AND password='{password}'"
    cursor.execute(sql)
    user   = cursor.fetchone()
    return user is not None
""",
    },

    {
        "filename":            "sqli_search.py",
        "vulnerability_type":  "SQL Injection",
        "cwe_id":              "CWE-89",
        "owasp_category":      "A03:2021",
        "severity":            "CRITICAL",
        "cvss_score":          9.8,
        "expected_fix_pattern":"parameterized",
        "vulnerable_code": """\
import sqlite3

def search_products(keyword):
    conn   = sqlite3.connect("store.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products WHERE name LIKE '%" + keyword + "%'")
    return cursor.fetchall()
""",
    },

    # ─── CWE-79 : XSS (2 variants) ────────────────────────────────

    {
        "filename":            "xss_template.py",
        "vulnerability_type":  "Cross-Site Scripting (XSS)",
        "cwe_id":              "CWE-79",
        "owasp_category":      "A03:2021",
        "severity":            "HIGH",
        "cvss_score":          7.2,
        "expected_fix_pattern":"html.escape",
        "vulnerable_code": """\
from flask import Flask, request, render_template_string

app = Flask(__name__)

@app.route("/greet")
def greet():
    name = request.args.get("name", "World")
    return render_template_string(f"<h1>Hello, {name}!</h1>")
""",
    },

    {
        "filename":            "xss_comment.py",
        "vulnerability_type":  "Cross-Site Scripting (XSS)",
        "cwe_id":              "CWE-79",
        "owasp_category":      "A03:2021",
        "severity":            "HIGH",
        "cvss_score":          6.8,
        "expected_fix_pattern":"escape",
        "vulnerable_code": """\
from flask import Flask, request

app = Flask(__name__)

@app.route("/comment", methods=["POST"])
def post_comment():
    comment = request.form.get("comment", "")
    return f"<div class='comment'>{comment}</div>"
""",
    },

    # ─── CWE-78 : Command Injection ───────────────────────────────

    {
        "filename":            "cmd_injection.py",
        "vulnerability_type":  "OS Command Injection",
        "cwe_id":              "CWE-78",
        "owasp_category":      "A03:2021",
        "severity":            "CRITICAL",
        "cvss_score":          9.8,
        "expected_fix_pattern":"subprocess",
        "vulnerable_code": """\
import os

def ping_host(host):
    output = os.system(f"ping -c 1 {host}")
    return output
""",
    },

    # ─── CWE-22 : Path Traversal ──────────────────────────────────

    {
        "filename":            "path_traversal.py",
        "vulnerability_type":  "Path Traversal",
        "cwe_id":              "CWE-22",
        "owasp_category":      "A01:2021",
        "severity":            "HIGH",
        "cvss_score":          7.5,
        "expected_fix_pattern":"os.path.abspath",
        "vulnerable_code": """\
from flask import Flask, request, send_file

app   = Flask(__name__)
BASE  = "/var/www/files"

@app.route("/download")
def download():
    filename = request.args.get("file")
    return send_file(BASE + "/" + filename)
""",
    },

    # ─── CWE-798 : Hardcoded Credentials ─────────────────────────

    {
        "filename":            "hardcoded_creds.py",
        "vulnerability_type":  "Hardcoded Credentials",
        "cwe_id":              "CWE-798",
        "owasp_category":      "A07:2021",
        "severity":            "HIGH",
        "cvss_score":          7.5,
        "expected_fix_pattern":"os.environ",
        "vulnerable_code": """\
import boto3

AWS_ACCESS_KEY = "AKIAIOSFODNN7EXAMPLE"
AWS_SECRET_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"

def upload_file(file_path, bucket):
    s3 = boto3.client(
        "s3",
        aws_access_key_id     = AWS_ACCESS_KEY,
        aws_secret_access_key = AWS_SECRET_KEY,
    )
    s3.upload_file(file_path, bucket, file_path)
""",
    },

    # ─── CWE-502 : Insecure Deserialization ───────────────────────

    {
        "filename":            "insecure_deserialize.py",
        "vulnerability_type":  "Insecure Deserialization",
        "cwe_id":              "CWE-502",
        "owasp_category":      "A08:2021",
        "severity":            "HIGH",
        "cvss_score":          8.1,
        "expected_fix_pattern":"json",
        "vulnerable_code": """\
import pickle
from flask import Flask, request

app = Flask(__name__)

@app.route("/load", methods=["POST"])
def load_session():
    data = request.data
    obj  = pickle.loads(data)   # Dangerous: arbitrary code execution
    return str(obj)
""",
    },

    # ─── CWE-327 : Weak Cryptography ─────────────────────────────

    {
        "filename":            "weak_crypto.py",
        "vulnerability_type":  "Weak Cryptographic Algorithm",
        "cwe_id":              "CWE-327",
        "owasp_category":      "A02:2021",
        "severity":            "MEDIUM",
        "cvss_score":          5.9,
        "expected_fix_pattern":"bcrypt",
        "vulnerable_code": """\
import hashlib

def hash_password(password: str) -> str:
    # MD5 is cryptographically broken
    return hashlib.md5(password.encode()).hexdigest()

def verify_password(password: str, hashed: str) -> bool:
    return hash_password(password) == hashed
""",
    },
]
