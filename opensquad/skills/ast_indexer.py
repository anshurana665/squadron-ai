"""
opensquad/skills/ast_indexer.py
Agent skill interface for extracting AST function contexts.
"""

from pathlib import Path
from typing import Any, Dict
from opensquad.harness.ast_indexer import ASTIndexer


class ASTIndexerSkill:
    name: str = "ast_indexer_skill"
    description: str = "Extracts enclosing function/class AST nodes around a specified line number."

    def __init__(self, workspace_root: Path):
        self.indexer = ASTIndexer(workspace_root)

    def execute(self, file_path: str, line_number: int) -> Dict[str, Any]:
        context = self.indexer.extract_symbol_context(file_path, line_number)
        if not context:
            return {
                "status": "error",
                "message": f"Could not extract AST context for {file_path}:{line_number}"
            }

        return {
            "status": "success",
            "context": context.model_dump()
        }
