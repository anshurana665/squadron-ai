"""
tests/integration/test_graph_backtrack.py
Integration tests for LangGraph state machine, Red-Team insertion, and backtracking logic.
"""
from opensquad.core.graph import _route_after_review, run_backtrack_reset
from opensquad.core.state import AgentState


def test_route_after_review_retry():
    state: AgentState = {"status": "coding", "attempt_count": 1, "backtrack_count": 0}
    route = _route_after_review(state)
    assert route == "developer"


def test_route_after_review_backtrack_trigger():
    # When attempt_count >= 2 and status == 'coding', it should trigger backtrack reset
    state: AgentState = {"status": "coding", "attempt_count": 2, "backtrack_count": 0}
    route = _route_after_review(state)
    assert route == "backtrack_reset"


def test_run_backtrack_reset():
    state: AgentState = {
        "status": "coding",
        "attempt_count": 2,
        "backtrack_count": 0,
        "error": "Failed syntax error trace...",
        "test_output": "old test trace"
    }
    new_state = run_backtrack_reset(state)
    assert new_state["attempt_count"] == 0
    assert new_state["backtrack_count"] == 1
    assert new_state["status"] == "planning"
    assert new_state["test_output"] is None
    assert "Previous architectural plan failed" in new_state["error"]
