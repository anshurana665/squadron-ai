"""
opensquad.harness
Deterministic local harness engines for static analysis, AST context isolation, diff patching, and test verification.
"""
from opensquad.harness.sast_engine import SASTEngine, SASTFinding
from opensquad.harness.ast_indexer import ASTIndexer, ASTContextBlock
from opensquad.harness.diff_patcher import DiffPatcherEngine, PatchBlock
from opensquad.harness.test_runner import TestRunnerEngine, VerificationResult

__all__ = [
    "SASTEngine",
    "SASTFinding",
    "ASTIndexer",
    "ASTContextBlock",
    "DiffPatcherEngine",
    "PatchBlock",
    "TestRunnerEngine",
    "VerificationResult",
]
