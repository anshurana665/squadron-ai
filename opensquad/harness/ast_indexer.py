"""
opensquad/harness/ast_indexer.py
Tree-sitter driven AST node extractor to isolate minimal functional boundaries.
"""

import ast
from pathlib import Path
from typing import Dict, Optional
from pydantic import BaseModel


class ASTContextBlock(BaseModel):
    file_path: str
    target_symbol: str
    start_line: int
    end_line: int
    source_code: str
    imports_header: str


class ASTIndexer:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root.resolve()

    def extract_symbol_context(self, file_path: str, line_number: int) -> Optional[ASTContextBlock]:
        abs_path = self.workspace_root / file_path
        if not abs_path.exists():
            return None

        source_text = abs_path.read_text(encoding="utf-8")
        try:
            parsed_ast = ast.parse(source_text, filename=str(abs_path))
        except SyntaxError:
            return None

        imports: list[str] = []
        for node in ast.iter_child_nodes(parsed_ast):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imports.append(ast.get_source_segment(source_text, node) or "")

        imports_header = "\n".join(filter(None, imports))

        target_node: Optional[ast.AST] = None
        target_name: str = "global_scope"

        for node in ast.walk(parsed_ast):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if hasattr(node, "lineno") and hasattr(node, "end_lineno"):
                    if node.lineno <= line_number <= (node.end_lineno or node.lineno):
                        target_node = node
                        target_name = node.name
                        break

        if target_node and hasattr(target_node, "lineno") and hasattr(target_node, "end_lineno"):
            snippet = ast.get_source_segment(source_text, target_node) or ""
            return ASTContextBlock(
                file_path=file_path,
                target_symbol=target_name,
                start_line=target_node.lineno,
                end_line=target_node.end_lineno or target_node.lineno,
                source_code=snippet,
                imports_header=imports_header
            )

        # Fallback if line is outside specific function definitions
        lines = source_text.splitlines()
        start = max(0, line_number - 15)
        end = min(len(lines), line_number + 15)
        return ASTContextBlock(
            file_path=file_path,
            target_symbol="block_fallback",
            start_line=start + 1,
            end_line=end,
            source_code="\n".join(lines[start:end]),
            imports_header=imports_header
        )
