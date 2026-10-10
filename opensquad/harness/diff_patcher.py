"""
opensquad/harness/diff_patcher.py
Deterministic search/replace diff application engine with fuzzy sequence alignment.
"""

import difflib
from pathlib import Path
from typing import Tuple
from pydantic import BaseModel, Field


class PatchBlock(BaseModel):
    file_path: str = Field(description="Target relative file path")
    search_block: str = Field(description="Exact block to search for")
    replace_block: str = Field(description="Replacement code block")


class DiffPatcherEngine:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root.resolve()

    def apply_patch_block(self, patch: PatchBlock) -> Tuple[bool, str]:
        target_file = self.workspace_root / patch.file_path
        if not target_file.exists():
            return False, f"File not found: {patch.file_path}"

        original_content = target_file.read_text(encoding="utf-8")
        search_str = patch.search_block.strip()
        replace_str = patch.replace_block.strip()

        # Step 1: Direct Exact Match
        if search_str in original_content:
            new_content = original_content.replace(search_str, replace_str, 1)
            target_file.write_text(new_content, encoding="utf-8")
            return True, "Patch applied cleanly via exact match."

        # Step 2: Line-by-Line Normalization Match
        orig_lines = original_content.splitlines()
        search_lines = search_str.splitlines()
        
        match_index = self._find_fuzzy_line_sequence(orig_lines, search_lines)
        if match_index != -1:
            before = orig_lines[:match_index]
            after = orig_lines[match_index + len(search_lines):]
            new_lines = before + replace_str.splitlines() + after
            target_file.write_text("\n".join(new_lines), encoding="utf-8")
            return True, "Patch applied cleanly via fuzzy line alignment."

        return False, "Failed to match search block in target file."

    def _find_fuzzy_line_sequence(self, source_lines: list[str], search_lines: list[str]) -> int:
        if not search_lines or len(search_lines) > len(source_lines):
            return -1

        search_normalized = [l.strip() for l in search_lines]
        window_size = len(search_lines)

        for i in range(len(source_lines) - window_size + 1):
            window = [source_lines[i + j].strip() for j in range(window_size)]
            if window == search_normalized:
                return i
        return -1
