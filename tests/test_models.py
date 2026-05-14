"""
Quick diagnostic: verifies each agent calls the correct NVIDIA model.
Run from d:\\squadron.ai with: python test_models.py
"""
import sys
import os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))

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
    print(f"  AI Provider     : {Config.AI_PROVIDER}")
    print(f"  CODING_MODEL    : {Config.CODING_MODEL}  <- Developer")
    print(f"  REASONING_MODEL : {Config.REASONING_MODEL}  <- Manager, Reviewer")

    # Test 1: Developer -> Mamba-Codestral
    test_model(
        label="DEVELOPER  (mamba-codestral-7b — fast coding, no thinking)",
        model=Config.CODING_MODEL,
        prompt="Write a Python function that returns the factorial of n using recursion. Only output code."
    )

    # Test 2: Manager -> DeepSeek with thinking
    test_model(
        label="MANAGER    (deepseek-v3.2 — reasoning + thinking=True)",
        model=Config.REASONING_MODEL,
        prompt="Create a short 3-step plan (JSON list) to fix a Python KeyError bug. Output ONLY a JSON list."
    )

    # Test 3: Reviewer -> DeepSeek with thinking
    test_model(
        label="REVIEWER   (deepseek-v3.2 — reasoning + thinking=True)",
        model=Config.REASONING_MODEL,
        prompt="Review this code: `def get(d,k): return d[k]`. Reply with APPROVE or REJECTED: and reason."
    )

    print(f"\n{SEP}")
    print("All tests done!")
    print(SEP)
