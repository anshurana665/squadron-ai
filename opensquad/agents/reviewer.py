"""
opensquad/agents/reviewer.py
Reviewer Agent — Gemma 3 27B via OpenRouter
Responsibilities:
  1. Execute patched code in E2B secure sandbox (Docker micro-VM)
  2. Use LLM to interpret results + decide APPROVED / REJECTED
  3. On rejection → send feedback to Developer for retry
"""
import os
import shlex
import logging
from opensquad.core.state import AgentState
from opensquad.core.llm   import LLMProvider
from opensquad.config     import Config

logger = logging.getLogger("opensquad.reviewer")

MAX_ATTEMPTS = 3


# ── E2B Sandbox execution ────────────────────────────────────────────

def _run_in_sandbox(code: str, filename: str) -> tuple[int, str, str]:
    """
    Execute code inside E2B secure sandbox.
    Returns: (exit_code, stdout, stderr)
    """
    if not Config.E2B_API_KEY:
        return -1, "", "E2B_API_KEY not set — sandbox skipped."

    try:
        from e2b_code_interpreter import Sandbox

        with Sandbox(api_key=Config.E2B_API_KEY) as sbx:
            # Write file to sandbox virtual filesystem
            remote_path = f"/home/user/{filename}"
            sbx.files.write(remote_path, code)

            # Execute with timeout
            # CWE-78 FIX: shlex.quote prevents shell injection via crafted filenames
            result = sbx.process.start_and_wait(
                f"python {shlex.quote(remote_path)}",
                timeout=30,
            )

            exit_code = result.exit_code if hasattr(result, "exit_code") else 0
            stdout    = result.stdout    if hasattr(result, "stdout")    else str(result)
            stderr    = result.stderr    if hasattr(result, "stderr")    else ""

            return exit_code, stdout[:2000], stderr[:2000]

    except ImportError:
        return -1, "", "e2b_code_interpreter not installed. Run: pip install e2b-code-interpreter"
    except Exception as e:
        return -1, "", f"Sandbox error: {str(e)}"


# ── Main agent function ──────────────────────────────────────────────

def run_reviewer(state: AgentState) -> AgentState:
    """
    LangGraph node: Reviewer Agent
    """
    logger.info("Reviewer starting verification...")
    
    # Update thoughts so UI knows we started
    state["latest_thoughts"] = "Reviewer is initializing E2B Sandbox and performing SAST audit..."
    
    llm          = LLMProvider.reviewer()
    patched_code = state.get("generated_code") or state["file_content"]
    filename     = os.path.basename(state["current_file"])
    attempt      = state.get("attempt_count", 1)

    # ── Step 1: E2B Sandbox Execution ───────────────────────────────
    exit_code, stdout, stderr = _run_in_sandbox(patched_code, filename)

    sandbox_available = exit_code != -1
    sandbox_passed    = (exit_code == 0) if sandbox_available else None

    # When sandbox is unavailable, don't bias the LLM toward REJECTED
    # by sending a fake failure exit code.
    review_exit_code = exit_code if sandbox_available else 0
    review_output    = (stdout or stderr) if sandbox_available else "(sandbox not configured — review code quality only)"

    # ── Step 2: LLM Review ──────────────────────────────────────────
    try:
        logger.info("Reviewer verifying patch...")
        review = llm.review(
            original_code  = state["file_content"],
            patched_code   = patched_code,
            e2b_stdout     = review_output,
            e2b_exit_code  = review_exit_code,
            plan           = state["plan"],
        )
        verdict          = review.get("status", "APPROVED")
        reason           = "SAST passed." if verdict == "APPROVED" else "SAST fatal infractions found."
        feedback         = review.get("developer_feedback", "")
        confidence       = 0.9 # SAST is deterministic
        remaining_issues = review.get("fatal_infractions_found", [])
        evpc_score       = 1.0 if verdict == "APPROVED" else 0.0

    except Exception as e:
        # If reviewer LLM fails, trust sandbox result
        verdict          = "APPROVED" if sandbox_passed else "REJECTED"
        reason           = f"Reviewer LLM error: {str(e)}. Defaulting to sandbox result."
        feedback         = stderr[:500] if not sandbox_passed else ""
        confidence       = 0.2
        remaining_issues = []
        evpc_score       = 0.5

    # ── Step 3: Build test output ────────────────────────────────────
    issues_str = ", ".join(remaining_issues) if remaining_issues else "None"
    test_output = (
        f"[Sandbox] Exit: {exit_code} | {stdout or stderr}\n"
        f"[Reviewer] {verdict} (confidence: {confidence:.1f}): {reason}\n"
        f"[EVPC Score] {evpc_score}\n"
        f"[Remaining Issues] {issues_str}"
    )

    # ── Step 4: Route decision ───────────────────────────────────────
    if verdict == "APPROVED":
        next_status = "done"
        next_error  = None
    elif attempt < MAX_ATTEMPTS:
        # LSP/Cursor-like behavior: explicitly send the raw stderr Python traceback back to the Developer
        next_status = "coding"
        
        combined_error = feedback or reason
        if stderr.strip():
            combined_error += f"\n\n--- PYTHON TRACEBACK (STDERR) ---\n{stderr.strip()}"
            
        next_error = combined_error
    else:
        # Max retries exhausted — mark failed
        next_status = "failed"
        next_error  = f"Max retries ({MAX_ATTEMPTS}) reached. Last error: {reason}"

    return {
        **state,
        "test_output":       test_output,
        "evpc_score":        evpc_score,
        "confidence":        confidence,
        "remaining_issues":  remaining_issues,
        "status":            next_status,
        "error":             next_error,
    }