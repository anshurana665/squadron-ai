"""
opensquad/agents/developer.py
Developer Agent — Gemma 3 27B via OpenRouter
Responsibilities: generate a secure, production-grade patch from Manager's plan.
"""
import re
import logging
from opensquad.core.state import AgentState
from opensquad.core.llm   import LLMProvider

logger = logging.getLogger("opensquad.developer")


def clean_llm_output(raw: str) -> str:
    """
    Strip markdown code fences from LLM output, with support for <final_executable_code> tags.
    """
    if not raw:
        return ""

    # 1. Try extracting from <final_executable_code> tag first
    xml_match = re.search(r'<final_executable_code>.*?(```.*?```).*?</final_executable_code>', raw, re.DOTALL | re.IGNORECASE)
    if xml_match:
        inner_markdown = xml_match.group(1)
        # Extract content from markdown block inside XML
        code_match = re.search(r'```(?:[a-zA-Z]*)?\n?(.*?)```', inner_markdown, re.DOTALL | re.IGNORECASE)
        if code_match:
            return code_match.group(1).strip()

    # 2. Fallback: Search for any markdown code block
    match = re.search(r'```(?:[a-zA-Z]*)?\n?(.*?)```', raw, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()

    # 3. Fallback: Strip backticks
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
    """
    logger.info("Developer starting patch generation...")
    
    # Update thoughts for UI
    state["latest_thoughts"] = f"Developer (L8_EXECUTIONER) is ingesting the Architect's plan and drafting a secure fix (Attempt {state.get('attempt_count', 0) + 1})..."
    
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