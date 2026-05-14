"""
opensquad/core/state.py
LangGraph state schema — shared across all agents.
total=False makes all keys optional at the TypedDict level,
which prevents LangGraph from rejecting state updates that
only modify a subset of keys.
"""
from typing import TypedDict, Optional


class AgentState(TypedDict, total=False):
    # ── Input ────────────────────────────────────────────────────────
    issue_description: str
    repo_url:          str
    file_content:      str
    current_file:      str
    security_mode:     bool

    # ── Pipeline data ────────────────────────────────────────────────
    plan:              list
    generated_code:    Optional[str]
    test_output:       Optional[str]
    error:             Optional[str]

    # ── Control flow ─────────────────────────────────────────────────
    status:            str   # planning | coding | reviewing | done | failed
    attempt_count:     int

    # ── UI / reporting ───────────────────────────────────────────────
    messages:          list
    latest_thoughts:   Optional[str]   # Manager chain-of-thought
    vulnerabilities:   Optional[list]  # CWE-tagged findings
    evpc_score:        Optional[float] # 1.0 verified | 0.5 inconclusive | 0.0 failed
    confidence:        Optional[float] # Reviewer confidence (0.0–1.0)
    remaining_issues:  Optional[list]  # Unresolved issues from Reviewer