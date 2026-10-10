"""
scripts/diagnostics/debug_agent.py
Isolate and debug direct LLM calls with detailed latency logging.
Run with: python scripts/diagnostics/debug_agent.py
"""
import time
import sys
import traceback
from pathlib import Path

# Ensure repo root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from opensquad.config import Config

LOG = Path(__file__).resolve().parent / "debug_agent.log"


def log(msg: str):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(msg + "\n")
    print(msg)


if __name__ == "__main__":
    # Clear previous log
    open(LOG, "w", encoding="utf-8").close()

    log("=== STARTING AGENT DIAGNOSTIC ===")
    log(f"REASONING_MODEL : {Config.REASONING_MODEL}")
    log(f"CODING_MODEL    : {Config.CODING_MODEL}")
    log(f"REVIEWER_MODEL  : {Config.REVIEWER_MODEL}")
    log(f"BASE_URL        : {Config.OPENROUTER_BASE_URL}")

    log("\n--- TEST 1: Direct OpenAI client call ---")
    t0 = time.time()
    try:
        from openai import OpenAI
        client = OpenAI(
            base_url=Config.OPENROUTER_BASE_URL,
            api_key=Config.OPENROUTER_API_KEY,
        )
        resp = client.chat.completions.create(
            model=Config.REASONING_MODEL,
            messages=[{"role": "user", "content": "Say OK in one word"}],
            max_tokens=10,
            stream=False,
        )
        content = resp.choices[0].message.content if resp.choices else ""
        log(f"  [PASS] Call returned in {time.time()-t0:.1f}s: {content.strip()}")
    except Exception as e:
        log(f"  [FAIL] Call failed in {time.time()-t0:.1f}s: {e}")
        traceback.print_exc()

    log("\n=== COMPLETED AGENT DIAGNOSTIC ===")
