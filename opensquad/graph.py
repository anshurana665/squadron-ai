"""
opensquad/graph.py
Backward compatibility root layer re-exporting the LangGraph workflow from opensquad.core.graph.
"""
from opensquad.core.graph import app, build_graph

__all__ = ["app", "build_graph"]

