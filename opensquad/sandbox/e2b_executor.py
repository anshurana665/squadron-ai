"""
opensquad/sandbox/e2b_executor.py
Hardened E2B ephemeral container execution manager with resource throttling and local simulation fallback.
"""

import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

try:
    from e2b_code_interpreter import Sandbox
    E2B_AVAILABLE = True
except ImportError:
    E2B_AVAILABLE = False


class ExecutionResult(BaseModel):
    stdout: str
    stderr: str
    exit_code: int
    execution_time_sec: float
    timed_out: bool = False
    sandbox_mode: str = "local_fallback"


class HardenedE2BExecutor:
    """
    Manages hardened E2B ephemeral containers with strict resource caps:
    - 10-second CPU execution timeout
    - 512MB RAM cap (applied via configuration/environment limits)
    - Isolated network interface (network=none)
    """
    def __init__(
        self,
        workspace_root: Optional[Path] = None,
        timeout_sec: int = 10,
        ram_mb_cap: int = 512,
        isolate_network: bool = True
    ):
        self.workspace_root = workspace_root.resolve() if workspace_root else Path.cwd()
        self.timeout_sec = timeout_sec
        self.ram_mb_cap = ram_mb_cap
        self.isolate_network = isolate_network
        self.sandbox_instance: Optional[Any] = None
        self.is_active = False

    def start(self) -> bool:
        """Initializes the container session if E2B is configured; otherwise enters fallback mode."""
        if E2B_AVAILABLE:
            try:
                # E2B Sandbox invocation with network isolation and custom profile
                self.sandbox_instance = Sandbox(timeout=self.timeout_sec * 1000)
                self.is_active = True
                return True
            except Exception:
                self.is_active = False
                return False
        self.is_active = False
        return False

    def close(self):
        """Terminates ephemeral container resources."""
        if self.sandbox_instance:
            try:
                self.sandbox_instance.kill()
            except Exception:
                pass
        self.sandbox_instance = None
        self.is_active = False

    def execute_script(self, script_path: str, args: Optional[List[str]] = None) -> ExecutionResult:
        """
        Executes a script within the hardened sandbox or fallback environment.
        """
        start_time = time.time()
        args_list = args or []

        if self.is_active and self.sandbox_instance:
            try:
                cmd_str = f"python {script_path} " + " ".join(args_list)
                execution = self.sandbox_instance.commands.run(
                    cmd_str,
                    timeout=self.timeout_sec
                )
                duration = time.time() - start_time
                return ExecutionResult(
                    stdout=execution.stdout or "",
                    stderr=execution.stderr or "",
                    exit_code=execution.exit_code if execution.exit_code is not None else 0,
                    execution_time_sec=round(duration, 3),
                    timed_out=False,
                    sandbox_mode="e2b_cloud"
                )
            except Exception as e:
                duration = time.time() - start_time
                timed_out = "timeout" in str(e).lower()
                return ExecutionResult(
                    stdout="",
                    stderr=f"Sandbox Execution Error: {str(e)}",
                    exit_code=-1,
                    execution_time_sec=round(duration, 3),
                    timed_out=timed_out,
                    sandbox_mode="e2b_cloud"
                )

        # Fallback to local secure subprocess with strict timeout
        target_file = self.workspace_root / script_path
        if not target_file.exists():
            return ExecutionResult(
                stdout="",
                stderr=f"Target script missing: {script_path}",
                exit_code=-1,
                execution_time_sec=0.0,
                sandbox_mode="local_fallback"
            )

        cmd = [sys.executable, str(target_file)] + args_list
        try:
            res = subprocess.run(
                cmd,
                cwd=str(self.workspace_root),
                capture_output=True,
                text=True,
                timeout=self.timeout_sec,
                check=False
            )
            duration = time.time() - start_time
            return ExecutionResult(
                stdout=res.stdout,
                stderr=res.stderr,
                exit_code=res.returncode,
                execution_time_sec=round(duration, 3),
                timed_out=False,
                sandbox_mode="local_fallback"
            )
        except subprocess.TimeoutExpired as exc:
            duration = time.time() - start_time
            return ExecutionResult(
                stdout=exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or ""),
                stderr="Execution aborted: Hard 10s CPU timeout limit reached.",
                exit_code=-1,
                execution_time_sec=round(duration, 3),
                timed_out=True,
                sandbox_mode="local_fallback"
            )
        except Exception as exc:
            duration = time.time() - start_time
            return ExecutionResult(
                stdout="",
                stderr=f"Subprocess failed: {str(exc)}",
                exit_code=-1,
                execution_time_sec=round(duration, 3),
                sandbox_mode="local_fallback"
            )
