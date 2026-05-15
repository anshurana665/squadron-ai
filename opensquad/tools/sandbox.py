import logging
import os
import shlex
from typing import Optional

logger = logging.getLogger(__name__)


def run_in_sandbox(code: str, filename: str = "patched_file.py") -> dict:
    """
    Execute Python code in an E2B cloud sandbox.

    Args:
        code:     Python source code to execute.
        filename: Name to write on the sandbox filesystem.

    Returns:
        dict with keys: exit_code, stdout, stderr, passed (bool)
    """
    from opensquad.config import Config

    result = {
        "exit_code": -1,
        "stdout":    "",
        "stderr":    "E2B not attempted.",
        "passed":    False,
    }

    if not Config.E2B_API_KEY:
        result["stderr"] = "E2B_API_KEY not configured — sandbox skipped."
        logger.warning(result["stderr"])
        return result

    try:
        from e2b_code_interpreter import Sandbox
    except ImportError:
        result["stderr"] = "e2b-code-interpreter package not installed."
        logger.error(result["stderr"])
        return result

    try:
        logger.info(f"🔬 Spawning E2B sandbox for '{filename}'...")
        with Sandbox(api_key=Config.E2B_API_KEY) as sandbox:
            # Always write to /home/user/ — root path writes fail on E2B
            remote_path = f"/home/user/{filename}"
            sandbox.filesystem.write(remote_path, code)

            # CWE-78 FIX: shlex.quote prevents shell injection
            proc = sandbox.process.start_and_wait(f"python {shlex.quote(remote_path)}")

            result["exit_code"] = proc.exit_code if proc.exit_code is not None else -1
            result["stdout"]    = proc.stdout or ""
            result["stderr"]    = proc.stderr or ""
            result["passed"]    = result["exit_code"] == 0

            logger.info(f"Sandbox exit code: {result['exit_code']}")
    except Exception as exc:
        logger.error(f"E2B sandbox error: {exc}")
        result["stderr"] = str(exc)

    return result
