# opensquad/agents/__init__.py
from opensquad.agents.manager   import run_manager
from opensquad.agents.developer import run_developer
from opensquad.agents.reviewer  import run_reviewer
from opensquad.agents.red_team  import run_red_team

__all__ = [
    "run_manager",
    "run_developer",
    "run_reviewer",
    "run_red_team",
]
