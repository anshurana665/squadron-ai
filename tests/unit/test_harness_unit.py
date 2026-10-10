"""
tests/unit/test_harness_unit.py
Unit tests for Squadron.AI deterministic harness engines and skills.
"""
import pytest
from pathlib import Path
from opensquad.harness.ast_indexer import ASTIndexer
from opensquad.harness.diff_patcher import DiffPatcherEngine, PatchBlock
from opensquad.harness.test_runner import TestRunnerEngine
from opensquad.skills.poc_generator import PoCGeneratorSkill
from opensquad.core.memory import ExperienceStore
from opensquad.core.telemetry import TelemetryTracker


def test_ast_indexer(tmp_path):
    sample_file = tmp_path / "sample_vuln.py"
    sample_file.write_text(
        "import os\n\ndef dangerous_func(x):\n    os.system(x)\n    return True\n",
        encoding="utf-8"
    )
    indexer = ASTIndexer(workspace_root=tmp_path)
    ctx = indexer.extract_symbol_context("sample_vuln.py", 4)
    assert ctx is not None
    assert ctx.target_symbol == "dangerous_func"
    assert "os.system(x)" in ctx.source_code


def test_diff_patcher_exact(tmp_path):
    target = tmp_path / "app.py"
    target.write_text("def login():\n    query = 'SELECT * FROM users WHERE name=' + user\n", encoding="utf-8")
    
    patcher = DiffPatcherEngine(workspace_root=tmp_path)
    block = PatchBlock(
        file_path="app.py",
        search_block="    query = 'SELECT * FROM users WHERE name=' + user",
        replace_block="    query = 'SELECT * FROM users WHERE name=?', (user,)"
    )
    success, msg = patcher.apply_patch_block(block)
    assert success is True
    assert "WHERE name=?" in target.read_text(encoding="utf-8")


def test_evpc_calculator():
    engine = TestRunnerEngine(workspace_root=Path.cwd())
    score = engine.calculate_evpc_score(
        poc_passed=True,
        regression_pass_ratio=1.0,
        delta_loc=10,
        total_loc=1000
    )
    assert score == round(0.6*1.0 + 0.4*1.0 - 0.1*(10/1000), 4)
    assert score > 0.95


def test_poc_generator_skill(tmp_path):
    skill = PoCGeneratorSkill(workspace_root=tmp_path)
    res = skill.execute(cwe_id="CWE-78", poc_script_code="import sys\nprint('confirmed')")
    assert res["status"] == "success"
    assert "test_poc_cwe_78.py" in res["poc_file_path"]


def test_experience_store(tmp_path):
    store_file = tmp_path / "store.json"
    store = ExperienceStore(store_path=store_file)
    store.record_pattern("pat_01", "CWE-89", "val = 'SQL ' + var", "val = 'SQL ?', (var,)", tags=["sql"])
    matches = store.query_patterns("CWE-89")
    assert len(matches) == 1
    assert matches[0].pattern_id == "pat_01"


def test_telemetry_tracker():
    tracker = TelemetryTracker()
    tracker.start_timer()
    m = tracker.stop_and_record("task_1", prompt_tokens=500, completion_tokens=200)
    assert m.total_tokens == 700
    agg = tracker.get_aggregate_telemetry()
    assert agg["execution_count"] == 1
    assert agg["total_tokens"] == 700
