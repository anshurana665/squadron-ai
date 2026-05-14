"""
opensquad/graph.py
LangGraph pipeline — connects Manager → Developer → Reviewer
with an automatic retry loop back to Developer on failure.

Flow:
  START
    └─► manager
          └─► developer
                └─► reviewer ──► END          (status = done / failed)
                      └─► developer (retry)   (status = coding, attempt < 3)
"""
from langgraph.graph import StateGraph, END

from opensquad.core.state       import AgentState
from opensquad.agents.manager   import run_manager
from opensquad.agents.developer import run_developer
from opensquad.agents.reviewer  import run_reviewer


# ── Conditional routing from Reviewer ───────────────────────────────

def _route_after_review(state: AgentState) -> str:
    status = state.get("status", "done")

    if status == "coding":
        # Reviewer rejected → retry Developer
        return "developer"

    # done or failed → exit pipeline
    return END


# ── Build Graph ──────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    # Register nodes
    graph.add_node("manager",   run_manager)
    graph.add_node("developer", run_developer)
    graph.add_node("reviewer",  run_reviewer)

    # Static edges
    graph.set_entry_point("manager")
    graph.add_edge("manager",   "developer")
    graph.add_edge("developer", "reviewer")

    # Conditional edge from reviewer (retry loop or END)
    graph.add_conditional_edges(
        "reviewer",
        _route_after_review,
        {
            "developer": "developer",
            END:          END,
        },
    )

    return graph


# ── Compiled app (imported by app.py) ────────────────────────────────
app = build_graph().compile()
