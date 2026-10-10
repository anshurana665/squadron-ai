import os
import difflib
import re
import logging
from dataclasses import dataclass
from typing import Optional, Any, List

logger = logging.getLogger("opensquad.utils")


def safe_workspace_path(filename: str, workspace_dir: str) -> str:
    """Check for path traversal. Ensures filename resolves within workspace_dir."""
    resolved = os.path.realpath(os.path.join(workspace_dir, filename))
    if not resolved.startswith(os.path.realpath(workspace_dir)):
        raise ValueError(f"Path traversal detected: {filename}")
    return resolved


def clean_llm_output(raw_text: Optional[str]) -> Optional[str]:
    """
    Strip markdown fences and return pure code.
    Returns None if the input is None or whitespace-only (never returns empty string).
    """
    if not raw_text or not raw_text.strip():
        return None
    match = re.search(r"```(?:[a-zA-Z0-9_\-]*)?\n?(.*?)```", raw_text, re.DOTALL | re.IGNORECASE)
    cleaned = match.group(1).strip() if match else raw_text.strip()
    return cleaned if cleaned else None


def is_plausible_code(candidate: Optional[str], original: str) -> bool:
    """
    Check if candidate patch is non-empty, non-identical to original, and meaningful.
    """
    if candidate is None or not candidate.strip():
        return False
    if candidate.strip() == original.strip():
        return False
    return True


_is_plausible_code = is_plausible_code


def validate_text_file(uploaded_file: Any, max_size_mb: int = 5) -> str:
    """
    Validate and decode uploaded file object to a UTF-8 string.
    Raises ValueError on invalid, missing, empty, or oversized files.
    """
    if uploaded_file is None:
        raise ValueError("No file provided.")

    if hasattr(uploaded_file, "size") and uploaded_file.size == 0:
        raise ValueError("Uploaded file is empty.")

    if hasattr(uploaded_file, "getvalue"):
        content = uploaded_file.getvalue()
    elif hasattr(uploaded_file, "read"):
        content = uploaded_file.read()
    elif isinstance(uploaded_file, (bytes, bytearray)):
        content = bytes(uploaded_file)
    else:
        raise ValueError("Unsupported file type.")

    if not content or len(content) == 0:
        raise ValueError("Uploaded file is empty.")

    if len(content) > max_size_mb * 1024 * 1024:
        raise ValueError(f"File size exceeds {max_size_mb} MB limit.")

    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("Uploaded file must be valid UTF-8 text.")


@dataclass
class PipelineOutput:
    """Canonical aggregated output from an agent execution run."""
    generated_code:   Optional[str]   = None
    evpc_score:       Optional[float] = None
    vulnerabilities:  Optional[list]  = None
    plan:             Optional[list]  = None
    status:           Optional[str]   = None
    test_output:      Optional[str]   = None

    @classmethod
    def from_agent_states(cls, agent_states: dict) -> "PipelineOutput":
        mgr = agent_states.get("manager", {})
        dev = agent_states.get("developer", {})
        rev = agent_states.get("reviewer", {})

        status = rev.get("status") or dev.get("status") or mgr.get("status")
        return cls(
            plan=mgr.get("plan"),
            vulnerabilities=mgr.get("vulnerabilities"),
            generated_code=dev.get("generated_code"),
            evpc_score=rev.get("evpc_score"),
            status=status,
            test_output=rev.get("test_output"),
        )


def display_diff(st_ref, original: str, fixed: str) -> None:
    """
    Show a side-by-side visual diff in Streamlit if streamlit is active.
    Green = added lines, Red = removed lines.
    """
    if original == fixed:
        st_ref.info("✅ No changes were made to this file.")
        return

    diff = list(difflib.unified_diff(
        original.splitlines(keepends=True),
        fixed.splitlines(keepends=True),
        fromfile="Original",
        tofile="Patched",
        lineterm="",
    ))

    if not diff:
        return

    st_ref.subheader("📋 Diff — What Changed")

    diff_html_parts = ["<div style='font-family:monospace;font-size:13px;line-height:1.6;'>"]

    for line in diff:
        line_esc = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        if line.startswith("+++") or line.startswith("---"):
            diff_html_parts.append(
                f"<div style='color:#94a3b8;padding:0 8px;'>{line_esc}</div>"
            )
        elif line.startswith("@@"):
            diff_html_parts.append(
                f"<div style='color:#7dd3fc;background:#1e3a5f;"
                f"padding:2px 8px;margin:4px 0;border-radius:4px;'>{line_esc}</div>"
            )
        elif line.startswith("+"):
            diff_html_parts.append(
                f"<div style='background:rgba(34,197,94,0.15);color:#86efac;"
                f"padding:1px 8px;border-left:3px solid #22c55e;'>{line_esc}</div>"
            )
        elif line.startswith("-"):
            diff_html_parts.append(
                f"<div style='background:rgba(239,68,68,0.15);color:#fca5a5;"
                f"padding:1px 8px;border-left:3px solid #ef4444;'>{line_esc}</div>"
            )
        else:
            diff_html_parts.append(
                f"<div style='color:#cbd5e1;padding:1px 8px;'>{line_esc}</div>"
            )

    diff_html_parts.append("</div>")
    st_ref.markdown("".join(diff_html_parts), unsafe_allow_html=True)
