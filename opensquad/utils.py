import os
import difflib
import re
import logging

logger = logging.getLogger("opensquad.utils")

def safe_workspace_path(filename: str, workspace_dir: str) -> str:
    """Check for path traversal. Ensures filename resolves within workspace_dir."""
    resolved = os.path.realpath(os.path.join(workspace_dir, filename))
    if not resolved.startswith(os.path.realpath(workspace_dir)):
        raise ValueError(f"Path traversal detected: {filename}")
    return resolved


def clean_llm_output(raw_text: str) -> str:
    """Strip markdown fences and return pure code."""
    if not raw_text:
        return ""
    match = re.search(r'```(?:[a-zA-Z]*)?\n?(.*?)```', raw_text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return raw_text.strip()


def display_diff(st_ref, original: str, fixed: str) -> None:
    """
    Show a side-by-side visual diff in Streamlit.
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
