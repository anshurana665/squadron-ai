"""
opensquad/agents/manager.py
Manager Agent — Gemma 3 27B via OpenRouter
Responsibilities: analyze code, tag CWEs, produce step-by-step repair plan.
"""
import json
import re
import logging
from opensquad.core.state import AgentState
from opensquad.core.llm   import LLMProvider
from opensquad.core.tools import read_file, search_codebase

from opensquad.config import Config
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from opensquad.core.rag import semantic_search

logger = logging.getLogger("opensquad.manager")

MANAGER_TOOLS = [read_file, search_codebase, semantic_search]
tools_by_name = {t.name: t for t in MANAGER_TOOLS}
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
    Robustly extract a JSON plan from LLM output.
    Supports both legacy list format and the new L8 Architect dictionary format.
    """
    # 1. Extract JSON block
    match = re.search(r'\{.*\}|\[.*\]', raw, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            
            # Case A: New L8 Architect Dictionary
            if isinstance(data, dict):
                directives = data.get("architectural_directives", [])
                if isinstance(directives, list) and all(isinstance(s, str) for s in directives):
                    return directives
                # Fallback: describe the goal from other fields
                target = data.get("primary_target_file", "codebase")
                cwe = data.get("cwe_identified", "unknown issue")
                return [f"Investigate {target} for {cwe}.", "Implement secure remediation."]

            # Case B: Legacy List format
            if isinstance(data, list) and all(isinstance(s, str) for s in data):
                return data
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

    # 3. Setup LangChain ChatOpenAI with tools
    llm = ChatOpenAI(
        model=Config.REASONING_MODEL,
        api_key=Config.OPENROUTER_API_KEY,
        base_url=Config.OPENROUTER_BASE_URL,
        temperature=Config.MANAGER_PARAMS.get("temperature", 0.7),
        max_tokens=Config.MANAGER_PARAMS.get("max_tokens", 8192),
        top_p=Config.MANAGER_PARAMS.get("top_p", 0.95),
    )
    llm_with_tools = llm.bind_tools(MANAGER_TOOLS)
    
    system_prompt = """<system_identity>
You are the Principal Security Architect and Orchestrator for OpenSquad AI (Internal Designation: L8_ARCHITECT). You are a deterministic, analytical engine. You do not write code. Your sole directive is to investigate user-reported issues, map codebase dependencies using your tools, identify the root cause of vulnerabilities, and output a strict, deterministic JSON remediation blueprint for the Developer Agent.
</system_identity>

<operating_principles>
1. ZERO HALLUCINATION: You are blind to the codebase until you use your tools. Do not assume file names, variable names, or directory structures.
2. EXHAUSTIVE EXPLORATION: You must verify the existence of a bug before planning its fix.
3. SECURITY FIRST: You evaluate every issue through the lens of the OWASP Top 10.
4. DETERMINISM: Your output must strictly adhere to the defined XML and JSON schemas. Extraneous conversational text is a fatal error.
</operating_principles>

<tool_usage_protocol>
You have access to the following tools:
- `search_codebase(query: str)`: Returns matching lines and file paths.
- `read_file(filepath: str)`: Returns the full content of a file.
- `semantic_search(query: str)`: Mathematically searches the RAG vector database.

You must invoke tools when you lack context. You may think, invoke a tool, observe the result, and think again. 
</tool_usage_protocol>

<cognitive_workflow>
You must process every request using the following sequential XML tags. Do not skip any tags.

1. <investigation_log>
   - Step 1: List the keywords you need to search based on the user's issue.
   - Step 2: Call `search_codebase` or `semantic_search`. 
   - Step 3: Identify the most likely files containing the issue.
   - Step 4: Call `read_file` on those specific files.
   - Step 5: Document the exact line numbers and functions where the vulnerability or bug resides.
</investigation_log>

2. <vulnerability_analysis>
   - Map the discovered bug to a Common Weakness Enumeration (CWE) if applicable.
   - Example: "The file `db.py` uses string concatenation (CWE-89: SQL Injection) on line 42."
   - Example: "The `account.py` class uses a global threading lock (CWE-362: Race Condition / Concurrency bottleneck) on line 18."
</vulnerability_analysis>

3. <blueprint_generation>
   - Formulate the logical steps required to fix the issue without breaking downstream dependencies.
   - Ensure the fix adheres to Python PEP8 standards and Enterprise Concurrency patterns.
</blueprint_generation>

4. <final_remediation_plan>
Output a strictly valid JSON object matching this exact schema (do NOT wrap the JSON inside markdown fences, output raw JSON ONLY inside this tag):
{
  "primary_target_file": "string",
  "secondary_files_to_modify": ["string"],
  "cwe_identified": "string",
  "architectural_directives": [
    "Step 1: specific instruction...",
    "Step 2: specific instruction..."
  ],
  "forbidden_patterns": ["List specific coding practices the Developer MUST NOT use for this fix"]
}
</final_remediation_plan>
</cognitive_workflow>"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=(
            f"ISSUE REPORTED: {state['issue_description']}{vuln_hint}\n\n"
            f"--- FILE ALREADY IN MEMORY: {state['current_file']} ---\n"
            f"```python\n{state['file_content'][:6000]}\n```\n\n"
            f"You have the file content above. You MAY skip `read_file` for this file "
            f"and proceed directly to `<vulnerability_analysis>` then `<final_remediation_plan>`."
        ))
    ]
    
    logger.info("Manager starting tool-calling loop...")
    raw_plan = ""
    thinking_log = ""
    
    try:
        # Tool calling loop — max 3 turns for speed
        for i in range(3):
            response = llm_with_tools.invoke(messages)
            messages.append(response)
            
            if not response.tool_calls:
                raw_plan = response.content
                break
                
            for tool_call in response.tool_calls:
                t_name = tool_call["name"]
                t_args = tool_call["args"]
                thinking_log += f"\n[Tool Execution] {t_name}({t_args})"
                logger.info(f"Manager called tool: {t_name}")
                
                tool_fn = tools_by_name.get(t_name)
                if tool_fn:
                    try:
                        tool_result = tool_fn.invoke(t_args)
                    except Exception as e:
                        tool_result = f"Error executing tool: {e}"
                else:
                    tool_result = f"Error: Unknown tool '{t_name}'"
                    
                messages.append(ToolMessage(tool_call_id=tool_call["id"], name=t_name, content=str(tool_result)))
        else:
            raw_plan = messages[-1].content if hasattr(messages[-1], "content") else "Error: Max iterations reached without a final plan."
            
    except Exception as e:
        logger.error(f"Manager tool loop failed: {e}")
        return {
            **state,
            "plan": [f"Analyze and fix: {state['issue_description']}"],
            "vulnerabilities": static_findings,
            "latest_thoughts": f"Manager Tool Loop Error: {str(e)}",
            "status": "coding",
            "error": str(e),
        }

    # 4. Parse plan from XML <final_remediation_plan>
    json_match = re.search(r'<final_remediation_plan>\s*(\{.*?\})\s*</final_remediation_plan>', raw_plan, re.DOTALL | re.IGNORECASE)
    
    primary_target = "codebase"
    if json_match:
        plan_content = json_match.group(1)
        try:
            # Pre-parse to extract metadata for state
            p_data = json.loads(plan_content)
            primary_target = p_data.get("primary_target_file", "codebase")
        except:
            pass
    else:
        plan_content = raw_plan
        
    plan = _parse_plan(plan_content)

    # 5. Return updated state
    return {
        **state,
        "plan": plan,
        "current_file": primary_target,
        "vulnerabilities": static_findings,
        "latest_thoughts": thinking_log + "\n\n" + (raw_plan[:1000] if raw_plan else ""),
        "status": "coding",
        "error": None,
    }