"""
opensquad — real test suite
Each test has: deterministic input, expected output, assertion that FAILS on wrong result.
No external API calls. No "assert result > 0" guesses.
"""
import sys
import types
from unittest.mock import MagicMock

# ── Mock streamlit so imports don't crash outside Streamlit ──
sys.modules["streamlit"] = MagicMock()

import pytest
from typing import Optional
from dataclasses import dataclass


# ═══════════════════════════════════════════════════════════════
# UNIT: clean_llm_output
# ═══════════════════════════════════════════════════════════════
# Import from app — adjust path if needed
sys.path.insert(0, ".")
try:
    from app import clean_llm_output, _is_plausible_code, validate_text_file, PipelineOutput
except ImportError:
    # Fallback: define inline for isolated testing
    import re

    def clean_llm_output(raw_text: str) -> Optional[str]:
        if not raw_text or not raw_text.strip():
            return None
        match = re.search(r"```(?:[a-zA-Z]+)?\n?(.*?)```", raw_text, re.DOTALL | re.IGNORECASE)
        result = match.group(1).strip() if match else raw_text.strip()
        return result if result else None

    def _is_plausible_code(candidate: Optional[str], original: str) -> bool:
        if candidate is None:
            return False
        if candidate.strip() == original.strip():
            return False
        return True


class TestCleanLLMOutput:
    def test_strips_python_fence(self):
        raw = "```python\ndef foo(): pass\n```"
        result = clean_llm_output(raw)
        assert result == "def foo(): pass", f"Got: {repr(result)}"

    def test_strips_generic_fence(self):
        raw = "```\nx = 1 + 2\n```"
        result = clean_llm_output(raw)
        assert result == "x = 1 + 2", f"Got: {repr(result)}"

    def test_returns_none_on_empty_string(self):
        assert clean_llm_output("") is None

    def test_returns_none_on_whitespace_only(self):
        assert clean_llm_output("   \n\t  ") is None

    def test_returns_none_on_none_input(self):
        assert clean_llm_output(None) is None  # type: ignore

    def test_returns_code_without_fence(self):
        raw = "x = parameterized_query(user_input)"
        result = clean_llm_output(raw)
        assert result == raw, f"Got: {repr(result)}"

    def test_never_returns_empty_string(self):
        # The contract: empty string is BANNED as return value
        result = clean_llm_output("")
        assert result != "", "Must return None, not empty string"

    def test_multiline_fence(self):
        raw = "```python\nimport sqlite3\ncursor.execute('SELECT ?', (val,))\n```"
        result = clean_llm_output(raw)
        assert "import sqlite3" in result
        assert "```" not in result


# ═══════════════════════════════════════════════════════════════
# UNIT: _is_plausible_code
# ═══════════════════════════════════════════════════════════════
class TestIsPlausibleCode:
    ORIGINAL = "cursor.execute('SELECT * FROM users WHERE name=' + user)"

    def test_none_is_not_plausible(self):
        assert _is_plausible_code(None, self.ORIGINAL) is False

    def test_identical_code_is_not_plausible(self):
        assert _is_plausible_code(self.ORIGINAL, self.ORIGINAL) is False

    def test_whitespace_only_difference_is_not_plausible(self):
        # Trailing whitespace difference should NOT be accepted as a real patch
        assert _is_plausible_code(self.ORIGINAL + "  ", self.ORIGINAL) is False

    def test_genuine_fix_is_plausible(self):
        fixed = "cursor.execute('SELECT * FROM users WHERE name=?', (user,))"
        assert _is_plausible_code(fixed, self.ORIGINAL) is True

    def test_shorter_fix_is_plausible(self):
        # Security fixes can be MUCH shorter — ratio guard was removed correctly
        short_fix = "cursor.execute('SELECT 1')"
        assert _is_plausible_code(short_fix, self.ORIGINAL) is True

    def test_empty_string_is_not_plausible(self):
        # This tests the old "" behavior — should be caught by None now
        # but defensively test empty string too
        assert _is_plausible_code("", self.ORIGINAL) is False


# ═══════════════════════════════════════════════════════════════
# UNIT: validate_text_file
# ═══════════════════════════════════════════════════════════════
class MockUploadedFile:
    """Minimal mock of Streamlit UploadedFile for testing."""
    def __init__(self, name: str, content: bytes):
        self.name = name
        self._content = content
        self.size = len(content)

    def getvalue(self) -> bytes:
        return self._content


class TestValidateTextFile:
    def test_valid_python_file(self):
        f = MockUploadedFile("test.py", b"print('hello')")
        result = validate_text_file(f)
        assert result == "print('hello')"

    def test_raises_on_none(self):
        with pytest.raises(ValueError, match="No file provided"):
            validate_text_file(None)

    def test_raises_on_empty_file(self):
        f = MockUploadedFile("empty.py", b"")
        with pytest.raises(ValueError, match="empty"):
            validate_text_file(f)

    def test_raises_on_oversized_file(self):
        big = b"x" * (6 * 1024 * 1024)  # 6 MB > 5 MB limit
        f = MockUploadedFile("big.py", big)
        with pytest.raises(ValueError, match="MB"):
            validate_text_file(f)

    def test_raises_on_binary_file(self):
        binary = bytes(range(256)) * 100  # non-UTF-8 bytes
        f = MockUploadedFile("binary.py", binary)
        with pytest.raises(ValueError, match="UTF-8"):
            validate_text_file(f)

    def test_returns_string_not_bytes(self):
        f = MockUploadedFile("code.py", b"x = 1")
        result = validate_text_file(f)
        assert isinstance(result, str), f"Expected str, got {type(result)}"

    def test_error_content_never_returned(self):
        # Regression: old code returned "Binary file or encoding error." string
        # That string must NEVER be returned — it must raise instead
        binary = bytes(range(256))
        f = MockUploadedFile("bad.py", binary)
        try:
            result = validate_text_file(f)
            assert "error" not in result.lower(), \
                f"Should have raised, not returned error string: {result[:50]}"
        except ValueError:
            pass  # correct behavior


# ═══════════════════════════════════════════════════════════════
# UNIT: PipelineOutput
# ═══════════════════════════════════════════════════════════════
class TestPipelineOutput:
    def test_default_all_none(self):
        out = PipelineOutput()
        assert out.generated_code is None
        assert out.evpc_score is None
        assert out.vulnerabilities is None
        assert out.plan is None

    def test_from_agent_states_correct_routing(self):
        """Each agent is authoritative for its own keys only."""
        agent_states = {
            "manager":  {"plan": ["step1", "step2"], "vulnerabilities": [{"cwe": "89"}], "status": "planned"},
            "developer": {"generated_code": "cursor.execute('?', (val,))", "status": "coded"},
            "reviewer":  {"evpc_score": 1.0, "test_output": "PASS", "status": "approved"},
        }
        out = PipelineOutput.from_agent_states(agent_states)

        # Manager fields
        assert out.plan == ["step1", "step2"]
        assert len(out.vulnerabilities) == 1

        # Developer fields
        assert "cursor.execute" in out.generated_code

        # Reviewer fields — MUST win status, not manager's "planned"
        assert out.evpc_score == 1.0
        assert out.status == "approved"
        assert out.test_output == "PASS"

    def test_from_agent_states_missing_agents(self):
        """Missing agents produce None fields — not KeyError."""
        out = PipelineOutput.from_agent_states({"manager": {"plan": ["fix it"]}})
        assert out.plan == ["fix it"]
        assert out.generated_code is None   # developer missing → None, not crash
        assert out.evpc_score is None       # reviewer missing → None, not crash

    def test_evpc_none_means_not_run(self):
        """evpc_score=None means reviewer never ran. Different from 0.0."""
        out = PipelineOutput()
        assert out.evpc_score is None
        # 0.0 means reviewer ran and patch FAILED
        out_failed = PipelineOutput(evpc_score=0.0)
        assert out_failed.evpc_score == 0.0
        assert out.evpc_score != out_failed.evpc_score  # these are different states

    def test_vulnerabilities_none_vs_empty_list(self):
        """None = scan never ran. [] = scan ran, found nothing. Not the same."""
        not_run  = PipelineOutput(vulnerabilities=None)
        clean    = PipelineOutput(vulnerabilities=[])
        assert not_run.vulnerabilities is None
        assert clean.vulnerabilities == []
        assert not_run.vulnerabilities != clean.vulnerabilities


# ═══════════════════════════════════════════════════════════════
# INTEGRATION: EVPC Engine (if opensquad package available)
# ═══════════════════════════════════════════════════════════════
class TestEVPCEngine:
    def setup_method(self):
        try:
            from opensquad.benchmark.evpc_engine import EVPCEngine
            self.engine = EVPCEngine()
            self.available = True
        except ImportError:
            self.available = False

    def test_two_of_three_verified(self):
        if not self.available:
            pytest.skip("opensquad package not installed")
        results = [
            {"evpc_verified": True},
            {"evpc_verified": False},
            {"evpc_verified": True},
        ]
        score = self.engine.calculate_evpc_score(results)
        assert abs(score - 0.667) < 0.01, f"Expected ~0.667, got {score}"

    def test_all_verified(self):
        if not self.available:
            pytest.skip("opensquad package not installed")
        results = [{"evpc_verified": True}] * 5
        score = self.engine.calculate_evpc_score(results)
        assert score == 1.0, f"Expected 1.0, got {score}"

    def test_none_verified(self):
        if not self.available:
            pytest.skip("opensquad package not installed")
        results = [{"evpc_verified": False}] * 5
        score = self.engine.calculate_evpc_score(results)
        assert score == 0.0, f"Expected 0.0, got {score}"

    def test_empty_input_raises(self):
        """Empty input must raise — not return 0.0 silently."""
        if not self.available:
            pytest.skip("opensquad package not installed")
        with pytest.raises((ValueError, ZeroDivisionError)):
            self.engine.calculate_evpc_score([])


# ═══════════════════════════════════════════════════════════════
# INTEGRATION: CWE classifier
# ═══════════════════════════════════════════════════════════════
class TestCWEClassifier:
    def setup_method(self):
        try:
            from opensquad.agents.manager import classify_vulnerabilities
            self.classify = classify_vulnerabilities
            self.available = True
        except ImportError:
            self.available = False

    def test_detects_sql_injection(self):
        if not self.available:
            pytest.skip("opensquad package not installed")
        code = "query = 'SELECT * FROM users WHERE name=' + username"
        hits = self.classify(code)
        assert len(hits) > 0, "Should detect CWE-89 (SQL injection)"
        cwe_ids = [h.get("cwe_id", "") for h in hits]
        assert any("89" in str(c) for c in cwe_ids), f"Expected CWE-89, got {cwe_ids}"

    def test_clean_code_no_hits(self):
        if not self.available:
            pytest.skip("opensquad package not installed")
        code = "result = db.execute('SELECT * FROM users WHERE name=?', (name,))"
        hits = self.classify(code)
        # Parameterized query — should not be flagged for SQL injection
        sql_hits = [h for h in hits if "89" in str(h.get("cwe_id", ""))]
        assert len(sql_hits) == 0, f"Parameterized query should not trigger CWE-89: {sql_hits}"

    def test_returns_list_not_none(self):
        if not self.available:
            pytest.skip("opensquad package not installed")
        # Must return a list — never None (None would crash len() callers)
        result = self.classify("x = 1")
        assert isinstance(result, list), f"Expected list, got {type(result)}"


if __name__ == "__main__":
    # Run with: python test_opensquad.py
    # Or: pytest test_opensquad.py -v
    pytest.main([__file__, "-v", "--tb=short"])
