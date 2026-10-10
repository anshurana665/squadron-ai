"""
opensquad/skills/diff_patcher.py
Agent skill interface for executing structured search/replace code edits.
"""

from pathlib import Path
from typing import Any, Dict
from opensquad.harness.diff_patcher import DiffPatcherEngine, PatchBlock


class DiffPatcherSkill:
    name: str = "diff_patcher_skill"
    description: str = "Applies a targeted search/replace patch to a specified source code file."

    def __init__(self, workspace_root: Path):
        self.patcher = DiffPatcherEngine(workspace_root)

    def execute(self, file_path: str, search_block: str, replace_block: str) -> Dict[str, Any]:
        patch = PatchBlock(
            file_path=file_path,
            search_block=search_block,
            replace_block=replace_block
        )
        success, message = self.patcher.apply_patch_block(patch)
        return {
            "status": "success" if success else "failed",
            "message": message,
            "file_path": file_path
        }
