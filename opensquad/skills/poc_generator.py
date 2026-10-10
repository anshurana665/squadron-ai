"""
opensquad/skills/poc_generator.py
Agent skill interface for generating and storing proof-of-concept exploit scripts.
"""
import re
from pathlib import Path
from typing import Any, Dict


class PoCGeneratorSkill:
    name: str = "poc_generator_skill"
    description: str = "Writes a minimal executable Proof-of-Concept (PoC) exploit script to verify bugs."

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root.resolve()

    def execute(self, cwe_id: str, poc_script_code: str) -> Dict[str, Any]:
        poc_dir = self.workspace_root / "tests" / "pocs"
        poc_dir.mkdir(parents=True, exist_ok=True)

        clean_cwe = re.sub(r"[^a-zA-Z0-9_]", "", str(cwe_id).lower().replace("-", "_"))
        if not clean_cwe:
            clean_cwe = "cwe_000"

        target_poc_path = poc_dir / f"test_poc_{clean_cwe}.py"
        target_poc_path.write_text(poc_script_code, encoding="utf-8")

        return {
            "status": "success",
            "poc_file_path": str(target_poc_path.relative_to(self.workspace_root)),
            "message": f"PoC script written to {target_poc_path.name}"
        }
