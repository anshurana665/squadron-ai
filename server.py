"""
OpenSquad AI — Flask Frontend Server
Serves HTML pages. FastAPI (api.py) handles all API calls.

Run both:
  uvicorn api:app --port 8000 --reload   ← FastAPI API layer
  python server.py                        ← Flask frontend (port 5000)
"""
from flask import Flask, render_template, send_from_directory
import os

app = Flask(__name__, template_folder="templates", static_folder="static")


@app.route("/")
def index():
    """Landing page."""
    return render_template("index.html")


@app.route("/audit")
def audit():
    """Audit dashboard page."""
    return render_template("audit.html")


@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory("static", filename)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
