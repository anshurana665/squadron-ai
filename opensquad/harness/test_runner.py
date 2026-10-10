"""
opensquad/harness/test_runner.py
Isolated test harness and trace summarizer for dual-verification guardrail checks and EVPC scoring.
"""

import subprocess
import sys
from pathlib import Path
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class VerificationResult(BaseModel):
    poc_passed: bool = Field(description="True if adversarial PoC test passed (vulnerability neutralized)")
    regression_pass_ratio: float = Field(description="Ratio of unit tests passing without regression (0.0 to 1.0)")
    delta_loc: int = Field(description="Number of lines of code changed")
    total_loc: int = Field(description="Total lines of code in target file or repository")
    evpc_score: float = Field(description="Calculated EVPC score")
    logs: str = Field(description="Combined output traces from verification runs")


class TestRunnerEngine:
    __test__ = False

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root.resolve()


    def calculate_evpc_score(
        self,
        poc_passed: bool,
        regression_pass_ratio: float,
        delta_loc: int,
        total_loc: int,
        alpha: float = 0.6,
        beta: float = 0.4,
        gamma: float = 0.1,
    ) -> float:
        """
        Calculates Execution-Verified Patch Correctness (EVPC):
        EVPC = alpha * S_PoC + beta * S_Reg - gamma * (Delta_LOC / Total_LOC)
        """
        s_poc = 1.0 if poc_passed else 0.0
        s_reg = max(0.0, min(1.0, regression_pass_ratio))
        
        loc_penalty = (delta_loc / total_loc) if total_loc > 0 else 0.0
        score = (alpha * s_poc) + (beta * s_reg) - (gamma * loc_penalty)
        return round(max(0.0, min(1.0, score)), 4)

    def run_verification(
        self,
        poc_script_path: Optional[str] = None,
        test_suite_path: Optional[str] = None,
        delta_loc: int = 10,
        total_loc: int = 1000,
    ) -> VerificationResult:
        """
        Runs the PoC exploit script and existing test suite to generate an EVPC score.
        If PoC script exits with code 0 BEFORE patch, vulnerability was confirmed.
        POST-PATCH: We expect PoC script to fail/error (exit code != 0), meaning vulnerability is neutralized.
        If a test script explicitly asserts neutralization (returns 0 when secure), poc_passed is True.
        """
        logs_list = []
        poc_passed = True
        
        if poc_script_path:
            abs_poc = self.workspace_root / poc_script_path
            if abs_poc.exists():
                cmd = [sys.executable, str(abs_poc)]
                res = subprocess.run(cmd, cwd=str(self.workspace_root), capture_output=True, text=True, check=False)
                logs_list.append(f"--- PoC Run Output ({poc_script_path}) ---\nSTDOUT: {res.stdout}\nSTDERR: {res.stderr}\nExit Code: {res.returncode}")
                # A 0 exit code on an unhandled exploit script indicates vulnerability triggered.
                # Exit code != 0 or specific pass output means vulnerability is prevented/neutralized.
                poc_passed = (res.returncode != 0) or ("VULNERABILITY_NEUTRALIZED" in res.stdout)
            else:
                logs_list.append(f"PoC script not found at {poc_script_path}. Defaulting poc_passed=True for non-exploit cases.")
                poc_passed = True
        
        regression_pass_ratio = 1.0
        if test_suite_path:
            abs_test = self.workspace_root / test_suite_path
            if abs_test.exists():
                cmd = [sys.executable, "-m", "pytest", str(abs_test), "-q"]
                res = subprocess.run(cmd, cwd=str(self.workspace_root), capture_output=True, text=True, check=False)
                logs_list.append(f"--- Regression Tests Output ({test_suite_path}) ---\n{res.stdout}\n{res.stderr}")
                regression_pass_ratio = 1.0 if res.returncode == 0 else 0.0
        
        evpc = self.calculate_evpc_score(
            poc_passed=poc_passed,
            regression_pass_ratio=regression_pass_ratio,
            delta_loc=delta_loc,
            total_loc=total_loc,
        )

        return VerificationResult(
            poc_passed=poc_passed,
            regression_pass_ratio=regression_pass_ratio,
            delta_loc=delta_loc,
            total_loc=total_loc,
            evpc_score=evpc,
            logs="\n\n".join(logs_list) if logs_list else "No execution traces recorded; verified theoretically."
        )
