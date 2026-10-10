"""
scripts/diagnostics/check_model_routing.py
Diagnostic utility to verify model connectivity and routing across agents.
Run with: python scripts/diagnostics/check_model_routing.py
"""
import sys
import os
from pathlib import Path

# Ensure repo root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from opensquad.config import Config
from opensquad.core.llm import LLMProvider

SEP = "-" * 60


def test_model(label: str, model: str, prompt: str):
    print(f"\n{SEP}")
    print(f"[TEST] {label}")
    print(f"  Model  : {model}")
    print(f"  Prompt : {prompt[:80]}")
    print(SEP)
    try:
        llm = LLMProvider()
        response = llm.generate(prompt, model=model)
        preview = response[:120].strip().replace('\n', ' ')
        print(f"\n  [PASS] Response received ({len(response)} chars)")
        print(f"  Preview: {preview}...")
    except Exception as e:
        print(f"\n  [FAIL] {e}")


if __name__ == "__main__":
    print("\n=== Squadron.AI Model Routing Diagnostic ===")
    print(f"  CODING_MODEL    : {Config.CODING_MODEL}  <- Developer")
    print(f"  REASONING_MODEL : {Config.REASONING_MODEL}  <- Manager, Reviewer")

    test_model(
        label="DEVELOPER  (Coding model)",
        model=Config.CODING_MODEL,
        prompt="Write a Python function that returns the factorial of n using recursion. Only output code."
    )

    test_model(
        label="MANAGER    (Reasoning model)",
        model=Config.REASONING_MODEL,
        prompt="Create a short 3-step plan (JSON list) to fix a Python KeyError bug. Output ONLY a JSON list."
    )

    test_model(
        label="REVIEWER   (Reasoning model)",
        model=Config.REASONING_MODEL,
        prompt="Review this code: `def get(d,k): return d[k]`. Reply with APPROVE or REJECTED: and reason."
    )

    print(f"\n{SEP}")
    print("All diagnostic checks done!")
    print(SEP)
