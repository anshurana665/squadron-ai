"""
opensquad/skills/sast_scanner.py
Agent skill interface for invoking deterministic static analysis tools.
"""

from pathlib import Path
from typing import Any, Dict, List
from opensquad.harness.sast_engine import SASTEngine


class SASTScannerSkill:
    name: str = "sast_scanner_skill"
    description: str = "Scans a project directory for security vulnerabilities using static analysis."

    def __init__(self, workspace_root: Path):
        self.engine = SASTEngine(workspace_root)

    def execute(self, file_path: str = "") -> Dict[str, Any]:
        """
        Executes SAST analysis on a specific file or the whole workspace.
        """
        if file_path:
            bandit_results = self.engine.run_bandit_scan(file_path)
            findings = [f.model_dump() for f in bandit_results]
        else:
            semgrep_results = self.engine.run_semgrep_scan()
            findings = [f.model_dump() for f in semgrep_results]

        return {
            "status": "success",
            "findings_count": len(findings),
            "findings": findings
        }
