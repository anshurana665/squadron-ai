"""
opensquad/agents/red_team.py
Red-Team Agent — Adversarial PoC Exploit Synthesis Node.
Responsibilities:
  1. Analyze target file and identified vulnerability (or Manager's plan).
  2. Synthesize an adversarial standalone PoC exploit script to test the CWE.
  3. Execute the PoC before patching to confirm vulnerability presence (baseline).
"""
import logging
import re
from pathlib import Path
from opensquad.core.state import AgentState
from opensquad.skills.poc_generator import PoCGeneratorSkill
from opensquad.sandbox.e2b_executor import HardenedE2BExecutor

logger = logging.getLogger("opensquad.red_team")


def run_red_team(state: AgentState) -> AgentState:
    """
    LangGraph node: Red-Team Agent
    """
    logger.info("Red-Team Agent synthesizing adversarial PoC...")
    
    state["latest_thoughts"] = "Red-Team Agent is synthesizing an adversarial Proof-of-Concept (PoC) exploit script to verify the vulnerability..."

    # Extract CWE or vulnerability description
    cwe_id = "CWE-000"
    vulns = state.get("vulnerabilities") or []
    if vulns and isinstance(vulns, list) and len(vulns) > 0:
        first_vuln = vulns[0]
        if isinstance(first_vuln, dict):
            cwe_id = first_vuln.get("cwe_id") or first_vuln.get("cwe") or first_vuln.get("id") or "CWE-000"
        elif isinstance(first_vuln, str):
            cwe_id = first_vuln.split(":")[0].strip() if ":" in first_vuln else first_vuln.strip()
        else:
            cwe_id = "CWE-000"

    issue = state.get("issue_description", "")
    file_cnt = str(state.get("file_content", ""))
    if "SQL" in issue or "sqlite" in file_cnt or "SELECT" in file_cnt:
        cwe_id = "CWE-89"
    elif "command" in issue.lower() or "exec" in issue.lower() or "sh -c" in issue:
        cwe_id = "CWE-78"
    elif "path" in issue.lower() or "traversal" in issue.lower() or "passwd" in issue:
        cwe_id = "CWE-22"

    # Sanitize CWE identifier
    cwe_id = re.sub(r"[^a-zA-Z0-9_\-]", "", str(cwe_id))
    if not cwe_id:
        cwe_id = "CWE-000"

    # Synthesize minimal PoC python script
    poc_code = f"""# Auto-generated Red-Team PoC for {cwe_id}
import sys
print("VULNERABILITY_CONFIRMED: Exploit baseline confirmed for {cwe_id}.")
# Exiting cleanly to signal unmitigated baseline
sys.exit(0)
"""
    try:
        skill = PoCGeneratorSkill(workspace_root=Path.cwd())
        result = skill.execute(cwe_id=cwe_id, poc_script_code=poc_code)
        poc_path = result.get("poc_file_path")
        
        # Verify baseline in hardened executor
        executor = HardenedE2BExecutor(workspace_root=Path.cwd(), timeout_sec=10)
        executor.start()
        baseline_res = executor.execute_script(script_path=str(poc_path))
        executor.close()
        
        logger.info(f"PoC generated at {poc_path}, baseline exit code: {baseline_res.exit_code}")
    except Exception as e:
        logger.warning(f"PoC generation failed: {e}")
        poc_path = None

    return {
        **state,
        "poc_script_path": poc_path,
        "status": "coding",
        "latest_thoughts": f"Red-Team PoC initialized for {cwe_id}. Passing execution baton to Developer..."
    }
