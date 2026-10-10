"""
opensquad/core/graph.py
LangGraph state machine with Static-Harness hybridization, Red-Team adversarial PoC generation, and Backtracking logic.

Flow:
  START
    └─► manager
          └─► red_team
                └─► developer
                      └─► reviewer ──► END                (status = done / failed)
                            ├─► developer (retry)         (status = coding, attempt < 2)
                            └─► backtrack_reset ──► manager (status = coding, attempt >= 2)
"""
import logging
from langgraph.graph import StateGraph, END

from opensquad.core.state       import AgentState
from opensquad.agents.manager   import run_manager
from opensquad.agents.red_team  import run_red_team
from opensquad.agents.developer import run_developer
from opensquad.agents.reviewer  import run_reviewer

logger = logging.getLogger("opensquad.core.graph")


def run_backtrack_reset(state: AgentState) -> AgentState:
    """
    Backtrack node triggered when repair strategy repeatedly fails (k >= 2 attempts).
    Resets state to Manager Agent to formulate an entirely new architectural plan,
    discarding stale execution stack traces from context.
    """
    logger.info("Triggering Backtrack Node: Resetting state for fresh architectural plan...")
    current_backtracks = state.get("backtrack_count", 0)
    return {
        **state,
        "attempt_count": 0,
        "backtrack_count": current_backtracks + 1,
        "error": "Previous architectural plan failed after multiple repair attempts. Disregard stale execution traces and formulate an entirely new strategy.",
        "test_output": None,
        "execution_trace": None,
        "status": "planning",
        "latest_thoughts": f"Backtrack triggered (Backtrack count: {current_backtracks + 1}). Resetting context for new Manager architectural plan."
    }


def _route_after_review(state: AgentState) -> str:
    status = state.get("status", "done")
    attempt_count = state.get("attempt_count", 1)
    backtrack_count = state.get("backtrack_count", 0)

    if status == "coding":
        # Backtrack on Failed Attempts >= 2 if we haven't exhausted backtracking limits (max 2 backtracks)
        if attempt_count >= 2 and backtrack_count < 2:
            return "backtrack_reset"
        elif attempt_count < 3:
            return "developer"
        else:
            return END

    return END


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    # Register nodes
    graph.add_node("manager",         run_manager)
    graph.add_node("red_team",        run_red_team)
    graph.add_node("developer",       run_developer)
    graph.add_node("reviewer",        run_reviewer)
    graph.add_node("backtrack_reset", run_backtrack_reset)

    # Static edges
    graph.set_entry_point("manager")
    graph.add_edge("manager",         "red_team")
    graph.add_edge("red_team",        "developer")
    graph.add_edge("developer",       "reviewer")
    graph.add_edge("backtrack_reset", "manager")

    # Conditional edge from reviewer
    graph.add_conditional_edges(
        "reviewer",
        _route_after_review,
        {
            "developer":       "developer",
            "backtrack_reset": "backtrack_reset",
            END:               END,
        },
    )

    return graph


# Compiled app
app = build_graph().compile()
