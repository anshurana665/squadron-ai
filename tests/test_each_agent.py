"""Test each NVIDIA LLM call individually with timeouts to find the hang."""
import time
import sys

# Patch streamlit so agents don't crash when imported outside Streamlit
import types
st_mock = types.ModuleType("streamlit")
st_mock.toast = lambda *a, **kw: None
st_mock.warning = lambda *a, **kw: None
sys.modules["streamlit"] = st_mock

from opensquad.config import Config

print("=" * 60)
print("CONFIG CHECK")
print(f"  NVIDIA_BASE_URL    : {Config.NVIDIA_BASE_URL}")
print(f"  REASONING_MODEL    : {Config.REASONING_MODEL}")
print(f"  CODING_MODEL       : {Config.CODING_MODEL}")
print(f"  REVIEWER_MODEL     : {Config.REVIEWER_MODEL}")
print(f"  KEY_MANAGER (len)  : {len(Config.NVIDIA_KEY_MANAGER)}")
print(f"  KEY_DEVELOPER (len): {len(Config.NVIDIA_KEY_DEVELOPER)}")
print(f"  KEY_REVIEWER (len) : {len(Config.NVIDIA_KEY_REVIEWER)}")
print(f"  MIN_SECONDS_BETWEEN: {Config.MIN_SECONDS_BETWEEN_CALLS}")
print(f"  MAX_RETRIES        : {Config.MAX_RETRIES}")
print("=" * 60)

CODE = 'import sqlite3\nconn=sqlite3.connect("db")\ncursor=conn.cursor()\nuser=input("name:")\ncursor.execute("SELECT * FROM users WHERE name=" + user)'

# ── Test 1: Manager (DeepSeek V3.2 685B) ──
print("\n[TEST 1] Manager LLM (deepseek-v3.2)...")
t0 = time.time()
try:
    from opensquad.core.llm import ManagerLLM
    mgr = ManagerLLM()
    thinking, plan = mgr.plan(
        file_content=CODE,
        issue="Fix SQL injection",
        security_mode=True,
    )
    elapsed = time.time() - t0
    print(f"  ✅ SUCCESS in {elapsed:.1f}s")
    print(f"  Thinking length: {len(thinking)}")
    print(f"  Plan: {plan[:200]}")
except Exception as e:
    elapsed = time.time() - t0
    print(f"  ❌ FAILED in {elapsed:.1f}s: {type(e).__name__}: {e}")

# ── Test 2: Developer (Devstral 123B) ──
print("\n[TEST 2] Developer LLM (devstral-2-123b)...")
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
    print(f"  ✅ SUCCESS in {elapsed:.1f}s")
    print(f"  Patch length: {len(patch)}")
    print(f"  Patch preview: {patch[:200]}")
except Exception as e:
    elapsed = time.time() - t0
    print(f"  ❌ FAILED in {elapsed:.1f}s: {type(e).__name__}: {e}")

# ── Test 3: Reviewer (DeepSeek R1 32B) ──
print("\n[TEST 3] Reviewer LLM (deepseek-r1-distill-qwen-32b)...")
t0 = time.time()
try:
    from opensquad.core.llm import ReviewerLLM
    rev = ReviewerLLM()
    review = rev.review(
        original_code=CODE,
        patched_code=CODE.replace('+ user', '?", (user,)'),
        e2b_stdout="(sandbox not configured)",
        e2b_exit_code=0,
        plan=["Fix SQL injection"],
    )
    elapsed = time.time() - t0
    print(f"  ✅ SUCCESS in {elapsed:.1f}s")
    print(f"  Review: {review}")
except Exception as e:
    elapsed = time.time() - t0
    print(f"  ❌ FAILED in {elapsed:.1f}s: {type(e).__name__}: {e}")

print("\n" + "=" * 60)
print("ALL TESTS COMPLETE")
