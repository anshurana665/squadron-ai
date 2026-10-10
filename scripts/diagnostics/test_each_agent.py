"""
scripts/diagnostics/test_each_agent.py
Diagnostic tool testing each agent LLM pipeline step independently with timeouts.
Run with: python scripts/diagnostics/test_each_agent.py
"""
import time
import sys
from pathlib import Path

# Ensure repo root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from opensquad.config import Config

CODE = """import sqlite3
conn=sqlite3.connect("db")
cursor=conn.cursor()
user=input("name:")
cursor.execute("SELECT * FROM users WHERE name=" + user)"""


def main():
    print("=" * 60)
    print("AGENT PIPELINE DIAGNOSTIC")
    print(f"  BASE_URL           : {Config.OPENROUTER_BASE_URL}")
    print(f"  REASONING_MODEL    : {Config.REASONING_MODEL}")
    print(f"  CODING_MODEL       : {Config.CODING_MODEL}")
    print(f"  REVIEWER_MODEL     : {Config.REVIEWER_MODEL}")
    print(f"  API KEY CONFIG     : {'Configured' if Config.OPENROUTER_API_KEY else 'Missing'}")
    print("=" * 60)

    # ── Test 1: Manager ──
    print("\n[TEST 1] Manager Agent (Reasoning)...")
    t0 = time.time()
    try:
        from opensquad.core.llm import ManagerLLM
        mgr = ManagerLLM()
        res = mgr.plan(file_content=CODE, issue="Fix SQL injection", security_mode=True)
        thinking, plan = res if isinstance(res, tuple) else ("", res)
        elapsed = time.time() - t0
        print(f"  [PASS] Completed in {elapsed:.1f}s")
        print(f"  Plan: {str(plan)[:150]}...")
    except Exception as e:
        print(f"  [FAIL] {type(e).__name__}: {e}")

    # ── Test 2: Developer ──
    print("\n[TEST 2] Developer Agent (Patching)...")
    t0 = time.time()
    try:
        from opensquad.core.llm import DeveloperLLM
        dev = DeveloperLLM()
        patch = dev.patch(
            file_content=CODE,
            plan=["Fix SQL injection by using parameterized queries"],
            error_feedback="",
        )
        elapsed = time.time() - t0
        print(f"  [PASS] Completed in {elapsed:.1f}s")
        print(f"  Patch preview: {str(patch)[:150]}...")
    except Exception as e:
        print(f"  [FAIL] {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
