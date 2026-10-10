"""
scripts/diagnostics/smoke_test_pipeline.py
Quick smoke test verifying end-to-end agent graph streaming execution.
Run with: python scripts/diagnostics/smoke_test_pipeline.py
"""
import sys
from pathlib import Path

# Ensure repo root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from opensquad.graph import app
from opensquad.core.state import AgentState

SAMPLE_CODE = """import sqlite3
conn = sqlite3.connect("db.sqlite")
cursor = conn.cursor()
user_input = "admin"
cursor.execute("SELECT * FROM users WHERE name=" + user_input)
"""

state = AgentState(
    issue_description="Fix SQL injection on line 5",
    repo_url="LOCAL",
    plan=[],
    current_file="test.py",
    file_content=SAMPLE_CODE,
    security_mode=True,
    generated_code=None,
    test_output=None,
    error=None,
    attempt_count=0,
    status="planning",
    messages=[],
    latest_thoughts=None,
    vulnerabilities=None,
    evpc_score=None,
)

if __name__ == "__main__":
    print("Running pipeline smoke test...")
    try:
        for chunk in app.stream(state):
            for node, s in chunk.items():
                print(f"  [{node}] status={s.get('status')} error={s.get('error')}")
        print("Smoke test finished!")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Smoke test failed: {e}")
