"""
opensquad/harness/sast_engine.py
High-performance deterministic static analysis harness wrapper for Semgrep and Bandit.
"""

import json
import subprocess
from pathlib import Path
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class SASTFinding(BaseModel):
    cwe_id: str = Field(description="CWE Identifier, e.g., CWE-78")
    file_path: str = Field(description="Relative target file path")
    start_line: int = Field(description="Starting line number of finding")
    end_line: int = Field(description="Ending line number of finding")
    severity: str = Field(description="Severity rating: HIGH, MEDIUM, LOW")
    match_snippet: str = Field(description="Matched source code text")
    rule_id: str = Field(description="Static analysis rule identifier")


class SASTEngine:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root.resolve()

    def run_semgrep_scan(self, target_subdir: Optional[str] = None) -> List[SASTFinding]:
        scan_path = self.workspace_root / target_subdir if target_subdir else self.workspace_root
        cmd = [
            "semgrep",
            "--config=auto",
            "--json",
            "--quiet",
            str(scan_path)
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if not result.stdout.strip():
                return []
            
            raw_data = json.loads(result.stdout)
            findings: List[SASTFinding] = []
            
            for item in raw_data.get("results", []):
                extra = item.get("extra", {})
                metadata = extra.get("metadata", {})
                cwe_raw = metadata.get("cwe", ["CWE-000"])[0] if metadata.get("cwe") else "CWE-000"
                cwe_id = cwe_raw.split(":")[0].strip()
                
                findings.append(
                    SASTFinding(
                        cwe_id=cwe_id,
                        file_path=str(Path(item["path"]).relative_to(self.workspace_root)),
                        start_line=item["start"]["line"],
                        end_line=item["end"]["line"],
                        severity=extra.get("severity", "MEDIUM").upper(),
                        match_snippet=extra.get("lines", "").strip(),
                        rule_id=item.get("check_id", "custom-rule")
                    )
                )
            return findings
        except Exception as err:
            # Fallback to empty list if binary is uninstalled or fails
            return []

    def run_bandit_scan(self, file_path: str) -> List[SASTFinding]:
        target_file = self.workspace_root / file_path
        if not target_file.exists():
            return []
            
        cmd = ["bandit", "-f", "json", str(target_file)]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if not result.stdout.strip():
                return []
                
            raw_data = json.loads(result.stdout)
            findings: List[SASTFinding] = []
            
            for item in raw_data.get("results", []):
                findings.append(
                    SASTFinding(
                        cwe_id=f"CWE-{item.get('issue_cwe', {}).get('id', '000')}",
                        file_path=file_path,
                        start_line=item.get("line_number", 1),
                        end_line=item.get("line_number", 1),
                        severity=item.get("issue_severity", "MEDIUM").upper(),
                        match_snippet=item.get("code", "").strip(),
                        rule_id=item.get("test_id", "bandit-rule")
                    )
                )
            return findings
        except Exception:
            return []
