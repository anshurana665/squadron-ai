"""Isolate the Manager LLM call — write all output to a log file."""
import time
import sys
import traceback

# Patch streamlit
import types
st_mock = types.ModuleType("streamlit")
st_mock.toast = lambda *a, **kw: None
st_mock.warning = lambda *a, **kw: None
sys.modules["streamlit"] = st_mock

LOG = "test_debug.log"

def log(msg):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(msg + "\n")
    print(msg)

# Clear log
open(LOG, "w").close()

log("=== STARTING DEBUG ===")

from opensquad.config import Config
log(f"REASONING_MODEL : {Config.REASONING_MODEL}")
log(f"CODING_MODEL    : {Config.CODING_MODEL}")
log(f"REVIEWER_MODEL  : {Config.REVIEWER_MODEL}")
log(f"KEY_MGR first 20: {Config.NVIDIA_KEY_MANAGER[:20]}")
log(f"KEY_DEV first 20: {Config.NVIDIA_KEY_DEVELOPER[:20]}")
log(f"KEY_REV first 20: {Config.NVIDIA_KEY_REVIEWER[:20]}")
log(f"MIN_SEC_BETWEEN : {Config.MIN_SECONDS_BETWEEN_CALLS}")
log(f"MAX_RETRIES     : {Config.MAX_RETRIES}")

CODE = 'x = 1 + "hello"'

# Test 1: Simple raw OpenAI call (bypass all our wrapper logic)
log("\n--- TEST 1: Raw OpenAI call to deepseek-v3.2 ---")
t0 = time.time()
try:
    from openai import OpenAI
    client = OpenAI(
        base_url=Config.NVIDIA_BASE_URL,
        api_key=Config.NVIDIA_KEY_MANAGER,
    )
    resp = client.chat.completions.create(
        model=Config.REASONING_MODEL,
        messages=[{"role": "user", "content": "Say OK in one word"}],
        max_tokens=10,
        stream=False,
    )
    log(f"  ✅ Raw call OK in {time.time()-t0:.1f}s: {resp.choices[0].message.content}")
except Exception as e:
    log(f"  ❌ Raw call FAILED in {time.time()-t0:.1f}s: {e}")
    traceback.print_exc()

# Test 2: Raw OpenAI STREAM call to deepseek-v3.2
log("\n--- TEST 2: Raw OpenAI STREAM call to deepseek-v3.2 ---")
t0 = time.time()
try:
    stream = client.chat.completions.create(
        model=Config.REASONING_MODEL,
        messages=[{"role": "user", "content": "Say OK in one word"}],
        max_tokens=10,
        stream=True,
        temperature=1.0,
        top_p=0.95,
        extra_body={"chat_template_kwargs": {"thinking": True}},
    )
    tokens = []
    for chunk in stream:
        if chunk.choices:
            delta = chunk.choices[0].delta
            reasoning = getattr(delta, "reasoning_content", None)
            if reasoning:
                tokens.append(f"[think:{reasoning[:20]}]")
            if delta.content:
                tokens.append(delta.content)
    log(f"  ✅ Stream OK in {time.time()-t0:.1f}s: {''.join(tokens)}")
except Exception as e:
    log(f"  ❌ Stream FAILED in {time.time()-t0:.1f}s: {e}")
    traceback.print_exc()

# Test 3: ManagerLLM.plan() via our wrapper
log("\n--- TEST 3: ManagerLLM.plan() wrapper ---")
t0 = time.time()
try:
    from opensquad.core.llm import ManagerLLM
    mgr = ManagerLLM()
    thinking, plan = mgr.plan(
        file_content=CODE,
        issue="Fix the type error",
        security_mode=False,
    )
    log(f"  ✅ plan() OK in {time.time()-t0:.1f}s")
    log(f"  Thinking len: {len(thinking)}")
    log(f"  Plan: {plan[:300]}")
except Exception as e:
    log(f"  ❌ plan() FAILED in {time.time()-t0:.1f}s: {e}")
    traceback.print_exc()

# Test 4: DeveloperLLM.patch()
log("\n--- TEST 4: DeveloperLLM.patch() ---")
t0 = time.time()
try:
    from opensquad.core.llm import DeveloperLLM
    dev = DeveloperLLM()
    patch = dev.patch(
        file_content=CODE,
        plan=["Fix the type error on line 1"],
        error_feedback="",
    )
    log(f"  ✅ patch() OK in {time.time()-t0:.1f}s")
    log(f"  Patch: {patch[:300]}")
except Exception as e:
    log(f"  ❌ patch() FAILED in {time.time()-t0:.1f}s: {e}")
    traceback.print_exc()

# Test 5: ReviewerLLM.review()
log("\n--- TEST 5: ReviewerLLM.review() ---")
t0 = time.time()
try:
    from opensquad.core.llm import ReviewerLLM
    rev = ReviewerLLM()
    review = rev.review(
        original_code=CODE,
        patched_code='x = 1 + int("hello")',
        e2b_stdout="(sandbox not configured)",
        e2b_exit_code=0,
        plan=["Fix the type error"],
    )
    log(f"  ✅ review() OK in {time.time()-t0:.1f}s")
    log(f"  Review: {review}")
except Exception as e:
    log(f"  ❌ review() FAILED in {time.time()-t0:.1f}s: {e}")
    traceback.print_exc()

log("\n=== ALL TESTS DONE ===")
