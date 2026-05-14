"""
opensquad/agents/developer.py
Developer Agent — deepseek-v3.1
Responsibilities: generate a secure, production-grade patch from Manager's plan.
"""
import re
import logging
from opensquad.core.state import AgentState
from opensquad.core.llm   import LLMProvider

logger = logging.getLogger("opensquad.developer")


def clean_llm_output(raw: str) -> str:
    """
    Strip markdown code fences from LLM output.
    Handles: `python ... `,  ` ... `,  `code`
    """
    if not raw:
        return ""

    # Remove fenced blocks → extract inner content
    match = re.search(r'```(?:[a-zA-Z]*)?\n?(.*?)```', raw, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()

    # Remove inline backticks
    raw = re.sub(r'`([^`]+)`', r'\1', raw)

    return raw.strip()


def _is_meaningful_patch(original: str, patched: str) -> bool:
    """Return True if the patch is non-empty and actually different from original."""
    if not patched:
        return False
    if patched.strip() == original.strip():
        return False
    if len(patched.strip()) < 10:
        return False
    return True


# ── Main agent function ──────────────────────────────────────────────

def run_developer(state: AgentState) -> AgentState:
    """
    LangGraph node: Developer Agent
    Input  : state with plan + file_content (+ optional error from Reviewer)
    Output : state updated with generated_code
    """
    llm = LLMProvider.developer()

    # Carry error feedback from Reviewer for retry cycles
    error_feedback = state.get("error") or ""
    if state.get("attempt_count", 0) > 0 and error_feedback:
        retry_context = f"PREVIOUS ATTEMPT FAILED: {error_feedback}"
    else:
        retry_context = ""

    try:
        logger.info(f"Developer patching code (attempt {state.get('attempt_count', 0) + 1})...")
        raw_patch = llm.patch(
            file_content   = state["file_content"],
            plan           = state["plan"],
            error_feedback = retry_context,
        )
    except Exception as e:
        return {
            **state,
            "generated_code": state["file_content"],  # fall back to original
            "status":         "reviewing",
            "error":          f"Developer LLM error: {str(e)}",
        }

    # Clean markdown fences
    patched_code = clean_llm_output(raw_patch)

    # Sanity check — if LLM returned garbage, keep original
    if not _is_meaningful_patch(state["file_content"], patched_code):
        patched_code = state["file_content"]
        warning = "Developer returned empty/identical patch — using original."
    else:
        warning = None

    return {
        **state,
        "generated_code":  patched_code,
        "status":          "reviewing",
        "attempt_count":   state.get("attempt_count", 0) + 1,
        "error":           warning,
    }