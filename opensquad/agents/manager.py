"""
opensquad/agents/manager.py
Manager Agent — nemotron-super-49b-v1.5 (Reasoning ON)
Responsibilities: analyze code, tag CWEs, produce step-by-step repair plan.
"""
import json
import re
import logging
from opensquad.core.state import AgentState
from opensquad.core.llm   import LLMProvider

logger = logging.getLogger("opensquad.manager")


# ── CWE pattern scanner (static pre-scan before LLM) ────────────────
VULN_PATTERNS: dict[str, dict] = {
    "CWE-89": {
        "name":     "SQL Injection",
        "owasp":    "A03:2021",
        "severity": "CRITICAL",
        "cvss":     9.8,
        "patterns": ['" + ', "' + ", "format(", ".format(", "f'SELECT", 'f"SELECT'],
    },
    "CWE-79": {
        "name":     "Cross-Site Scripting (XSS)",
        "owasp":    "A03:2021",
        "severity": "HIGH",
        "cvss":     7.2,
        "patterns": ["innerHTML", "document.write", "render_template_string", "Markup("],
    },
    "CWE-78": {
        "name":     "OS Command Injection",
        "owasp":    "A03:2021",
        "severity": "CRITICAL",
        "cvss":     9.8,
        "patterns": ["os.system(", "subprocess.call(", "shell=True", "exec(", "eval("],
    },
    "CWE-22": {
        "name":     "Path Traversal",
        "owasp":    "A01:2021",
        "severity": "HIGH",
        "cvss":     7.5,
        "patterns": ["open(", "../", "os.path.join(request", "filename ="],
    },
    "CWE-798": {
        "name":     "Hardcoded Credentials",
        "owasp":    "A07:2021",
        "severity": "HIGH",
        "cvss":     7.5,
        "patterns": ["password =", "api_key =", "secret =", "token =", "PASSWORD ="],
    },
    "CWE-502": {
        "name":     "Insecure Deserialization",
        "owasp":    "A08:2021",
        "severity": "HIGH",
        "cvss":     8.1,
        "patterns": ["pickle.loads(", "yaml.load(", "marshal.loads("],
    },
    "CWE-327": {
        "name":     "Weak Cryptography",
        "owasp":    "A02:2021",
        "severity": "MEDIUM",
        "cvss":     5.9,
        "patterns": ["md5(", "sha1(", "DES(", "RC4("],
    },
}


def classify_vulnerabilities(code: str) -> list[dict]:
    """
    Static pre-scan: find likely vulnerabilities by pattern matching.
    Returns a list of CWE-tagged findings.
    """
    findings = []
    lines    = code.splitlines()

    for cwe_id, info in VULN_PATTERNS.items():
        for line_no, line in enumerate(lines, start=1):
            for pattern in info["patterns"]:
                if pattern in line:
                    findings.append({
                        "cwe_id":   cwe_id,
                        "name":     info["name"],
                        "owasp":    info["owasp"],
                        "severity": info["severity"],
                        "cvss":     info["cvss"],
                        "line":     line_no,
                        "snippet":  line.strip()[:120],
                    })
                    break  # one finding per CWE per line

    return findings


def _parse_plan(raw: str) -> list[str]:
    """
    Robustly extract a JSON list from LLM output.
    Falls back to line-by-line split if JSON parse fails.
    """
    # Try JSON array extraction
    match = re.search(r'\[.*?\]', raw, re.DOTALL)
    if match:
        try:
            plan = json.loads(match.group())
            if isinstance(plan, list) and all(isinstance(s, str) for s in plan):
                return plan
        except json.JSONDecodeError:
            pass

    # Fallback: treat each non-empty line as a step
    lines = [l.strip().lstrip("0123456789.-) ") for l in raw.splitlines() if l.strip()]
    return lines[:5] if lines else ["Analyze code for bugs and fix them."]


# ── Main agent function ──────────────────────────────────────────────

def run_manager(state: AgentState) -> AgentState:
    """
    LangGraph node: Manager Agent
    Input  : state with file_content + issue_description
    Output : state updated with plan, vulnerabilities, latest_thoughts
    """
    llm = LLMProvider.manager()

    # 1. Static vulnerability pre-scan
    static_findings = classify_vulnerabilities(state["file_content"])

    # 2. Build context hint for LLM
    vuln_hint = ""
    if static_findings:
        vuln_list = ", ".join(
            f"{f['cwe_id']} ({f['name']}) at line {f['line']}"
            for f in static_findings[:5]
        )
        vuln_hint = f"\n\nSTATIC PRE-SCAN FOUND: {vuln_list}\nInclude fixes for these in your plan."

    prompt_content = (
        f"{state['issue_description']}{vuln_hint}\n\n"
        f"FILE: {state['current_file']}\n\n"
        f"CODE:\n{state['file_content']}"
    )

    # 3. Call deepseek-v3.2 with thinking mode
    try:
        logger.info("Manager analyzing code...")
        thinking, raw_plan = llm.plan(
            file_content  = state["file_content"],
            issue         = state["issue_description"] + vuln_hint,
            security_mode = state["security_mode"],
        )
    except Exception as e:
        # Graceful degradation — don't crash the pipeline
        return {
            **state,
            "plan":            [f"Analyze and fix: {state['issue_description']}"],
            "vulnerabilities": static_findings,
            "latest_thoughts": f"Manager LLM error: {str(e)}",
            "status":          "coding",
            "error":           str(e),
        }

    # 4. Parse plan
    plan = _parse_plan(raw_plan)

    # 5. Return updated state
    return {
        **state,
        "plan":            plan,
        "vulnerabilities": static_findings,
        "latest_thoughts": thinking[:4000] if thinking else raw_plan[:1000],
        "status":          "coding",
        "error":           None,
    }