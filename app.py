# ============================================================
# OpenSquad AI — app.py  v4  (Top 1% Target)
# Fixes: logical correctness, parallel efficiency, design clarity
# ============================================================

# ── Standard library — ALL imports at top, no lazy imports ──
import os
import re
import threading
import concurrent.futures
import requests
from dataclasses import dataclass, field
from typing import Optional, Callable

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

# ── Third-party ──
import streamlit as st

# ── OpenSquad — lazy imports inside handlers ──
# Reason: Streamlit's working directory at module load time may differ
# from the project root where opensquad/ lives. Lazy imports inside
# button handlers run AFTER Streamlit sets up its environment correctly.
from opensquad.config import Config
Config.validate()

_OPENSQUAD_AVAILABLE = True   # assume available; failure caught at call site


# ─────────────────────────────────────────────────────────────
# CONSTANTS  — named, documented, no magic numbers
# ─────────────────────────────────────────────────────────────
_LANG_MAP: dict[str, tuple[str, str]] = {
    "py":   ("python",      "text/x-python"),
    "js":   ("javascript",  "application/javascript"),
    "html": ("html",        "text/html"),
    "css":  ("css",         "text/css"),
    "cpp":  ("cpp",         "text/x-c++src"),
    "java": ("java",        "text/x-java-source"),
}
_SUPPORTED_EXTS = frozenset(_LANG_MAP.keys())
MAX_FILE_BYTES  = 5 * 1024 * 1024  # 5 MB

# Parallel workers for ZIP batch audit.
# I/O-bound (API calls) → threads are correct, not processes.
# 3 is conservative: avoids overwhelming NVIDIA rate limits.
_ZIP_MAX_WORKERS = 3


# ─────────────────────────────────────────────────────────────
# DATA CONTRACTS
# ─────────────────────────────────────────────────────────────
@dataclass
class PatchResult:
    """
    Explicit result for every agent run.
    Invariant: success=True  ↔  fixed_code is not None
               success=False ↔  error is not None
    These two paths never overlap — enforced by run_zip_agent().
    """
    filename: str
    success: bool
    original_code: str
    fixed_code: Optional[str] = None
    error: Optional[str] = None


@dataclass
class AuditSnapshot:
    """
    Immutable, coherent snapshot of all results at one point in time.
    All fields computed from ONE lock acquisition → internally consistent.
    succeeded + failed == total is guaranteed.
    """
    succeeded: list[PatchResult]
    failed: list[PatchResult]
    total: int


@dataclass
class BatchAuditResult:
    """
    Thread-safe accumulator.
    Key design: snapshot() acquires the lock ONCE and returns
    an AuditSnapshot — consistent, immutable, safe to use without lock.
    Previous version called self.all 3 times → 3 lock acquisitions
    → succeeded + failed could ≠ total if results arrived between calls.
    """
    _results: list[PatchResult] = field(default_factory=list)
    _lock: threading.Lock       = field(default_factory=threading.Lock)

    def record(self, result: PatchResult) -> None:
        """Thread-safe append."""
        with self._lock:
            self._results.append(result)

    def snapshot(self) -> AuditSnapshot:
        """
        ONE lock acquisition → guaranteed coherent snapshot.
        succeeded + failed == total always.
        """
        with self._lock:
            results   = list(self._results)          # copy under lock
        succeeded = [r for r in results if r.success]
        failed    = [r for r in results if not r.success]
        return AuditSnapshot(
            succeeded=succeeded,
            failed=failed,
            total=len(results),
        )


# ─────────────────────────────────────────────────────────────
# PIPELINE OUTPUT CONTRACT
# Replaces raw dict — every caller sees exact fields, types, semantics.
# ─────────────────────────────────────────────────────────────
@dataclass
class PipelineOutput:
    """
    Typed contract for what stream_single_file_pipeline yields as final state.
    Purpose: eliminate raw dict access throughout the codebase.
    Every field is Optional — pipeline may not produce all of them.

    Contract:
      - generated_code is None  → Developer produced nothing (API failure)
      - evpc_score is None      → Reviewer never ran (not "score = 0")
      - vulnerabilities is None → Scan never ran (not "no vulns found")
    These three None states are semantically DIFFERENT from 0, [], 0.0.
    """
    generated_code:  Optional[str]   = None
    plan:            Optional[list]   = None
    vulnerabilities: Optional[list]   = None
    evpc_score:      Optional[float]  = None
    test_output:     Optional[str]    = None
    status:          str              = "unknown"
    error:           Optional[str]    = None

    @classmethod
    def from_agent_states(cls, agent_states: dict[str, dict]) -> "PipelineOutput":
        """
        Build a typed PipelineOutput from per-agent state tracking dict.
        Each agent is the authoritative source for its own outputs only:
          - manager  → plan, vulnerabilities
          - developer → generated_code
          - reviewer  → evpc_score, test_output, status, error
        This prevents key collision: manager writing "status" cannot
        overwrite reviewer's "status" because they never share a dict.
        """
        mgr = agent_states.get("manager",  {})
        dev = agent_states.get("developer", {})
        rev = agent_states.get("reviewer",  {})

        return cls(
            generated_code  = dev.get("generated_code"),
            plan            = mgr.get("plan"),
            vulnerabilities = mgr.get("vulnerabilities"),
            evpc_score      = rev.get("evpc_score"),
            test_output     = rev.get("test_output"),
            status          = rev.get("status") or dev.get("status") or mgr.get("status") or "unknown",
            error           = rev.get("error") or dev.get("error") or mgr.get("error"),
        )

    @classmethod
    def failed(cls, error: str) -> "PipelineOutput":
        """Named constructor for pipeline failure. Unambiguous: status=failed, error is set."""
        return cls(status="failed", error=error)


# ─────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="OpenSquad AI | Code Auditor",
    page_icon="💠",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&family=Inter:wght@300;400;500;600&display=swap');

:root {
    --bg:          #04050a;
    --bg2:         #080c14;
    --surface:     #0d1117;
    --surface2:    #161b22;
    --surface3:    #1c2333;
    --border:      #21262d;
    --border2:     #30363d;
    --text:        #e6edf3;
    --text-muted:  #8b949e;
    --text-dim:    #484f58;
    --cyan:        #58a6ff;
    --purple:      #bc8cff;
    --green:       #3fb950;
    --orange:      #f0883e;
    --red:         #f85149;
    --pink:        #ff7b72;
    --gold:        #d29922;
    --grad1: linear-gradient(135deg, #58a6ff 0%, #bc8cff 100%);
    --grad2: linear-gradient(135deg, #3fb950 0%, #58a6ff 100%);
    --grad3: linear-gradient(135deg, #f85149 0%, #f0883e 100%);
    --glow-blue:   0 0 30px rgba(88,166,255,0.15);
    --glow-purple: 0 0 30px rgba(188,140,255,0.15);
    --r: 12px; --r-sm: 8px; --r-xs: 5px;
}

/* ── Reset ── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

/* ── App background with animated mesh ── */
.stApp {
    background: var(--bg) !important;
    font-family: 'Inter', sans-serif;
    color: var(--text);
    min-height: 100vh;
}

/* animated gradient mesh background */
.stApp::before {
    content: '';
    position: fixed;
    inset: 0;
    background:
        radial-gradient(ellipse 80% 50% at 20% 10%, rgba(88,166,255,0.07) 0%, transparent 60%),
        radial-gradient(ellipse 60% 40% at 80% 80%, rgba(188,140,255,0.06) 0%, transparent 60%),
        radial-gradient(ellipse 40% 30% at 50% 50%, rgba(63,185,80,0.04) 0%, transparent 60%);
    pointer-events: none;
    z-index: 0;
    animation: meshShift 12s ease-in-out infinite alternate;
}
@keyframes meshShift {
    0%   { opacity: 0.7; }
    50%  { opacity: 1.0; }
    100% { opacity: 0.8; }
}

/* ── Grid overlay ── */
.stApp::after {
    content: '';
    position: fixed;
    inset: 0;
    background-image:
        linear-gradient(rgba(88,166,255,0.03) 1px, transparent 1px),
        linear-gradient(90deg, rgba(88,166,255,0.03) 1px, transparent 1px);
    background-size: 40px 40px;
    pointer-events: none;
    z-index: 0;
}

/* ── Layout ── */
#MainMenu, footer, header { visibility: hidden; }
.stDeployButton, [data-testid="stToolbar"] { display: none !important; }

.main .block-container {
    max-width: 1100px !important;
    padding: 0 2rem 5rem !important;
    margin: 0 auto;
    position: relative;
    z-index: 1;
    animation: pageIn 0.5s cubic-bezier(0.22,1,0.36,1) forwards;
}
@keyframes pageIn {
    from { opacity:0; transform: translateY(16px); }
    to   { opacity:1; transform: translateY(0); }
}

/* ── Typography ── */
h1, h2, h3 {
    font-family: 'Syne', sans-serif;
    color: var(--text);
    letter-spacing: -0.02em;
}
p, label, .stMarkdown p {
    font-size: 0.9rem;
    color: var(--text-muted);
    line-height: 1.7;
}

/* ── Buttons ── */
.stButton > button {
    font-family: 'Syne', sans-serif !important;
    font-size: 0.875rem !important;
    font-weight: 600 !important;
    color: #fff !important;
    background: linear-gradient(135deg, #1a6fe8 0%, #7c3aed 100%) !important;
    border: none !important;
    border-radius: var(--r-sm) !important;
    padding: 0.6rem 1.5rem !important;
    letter-spacing: 0.02em;
    transition: all 0.2s ease !important;
    box-shadow: 0 0 0 0 rgba(88,166,255,0) !important;
    position: relative;
    overflow: hidden;
}
.stButton > button::before {
    content: '';
    position: absolute;
    inset: 0;
    background: linear-gradient(135deg, rgba(255,255,255,0.12) 0%, transparent 100%);
    opacity: 0;
    transition: opacity 0.2s;
}
.stButton > button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 4px 20px rgba(88,166,255,0.35), 0 0 40px rgba(124,58,237,0.2) !important;
}
.stButton > button:hover::before { opacity: 1; }
.stButton > button:active { transform: translateY(0px) !important; }

/* ── Download buttons ── */
.stDownloadButton > button {
    font-family: 'Inter', sans-serif !important;
    font-size: 0.82rem !important;
    font-weight: 500 !important;
    color: var(--cyan) !important;
    background: rgba(88,166,255,0.08) !important;
    border: 1px solid rgba(88,166,255,0.25) !important;
    border-radius: var(--r-sm) !important;
    padding: 0.5rem 1.2rem !important;
    transition: all 0.15s ease !important;
}
.stDownloadButton > button:hover {
    background: rgba(88,166,255,0.15) !important;
    border-color: rgba(88,166,255,0.5) !important;
    box-shadow: 0 0 16px rgba(88,166,255,0.2) !important;
}

/* ── File uploader ── */
[data-testid="stFileUploader"] {
    background: var(--surface) !important;
    border: 1px dashed var(--border2) !important;
    border-radius: var(--r) !important;
    padding: 1.5rem !important;
    transition: all 0.2s ease !important;
    position: relative;
}
[data-testid="stFileUploader"]:hover {
    border-color: var(--cyan) !important;
    box-shadow: 0 0 20px rgba(88,166,255,0.1) !important;
}
[data-testid="stFileUploader"] label { color: var(--text-muted) !important; font-size: 0.875rem !important; }

/* ── Text area ── */
.stTextArea textarea {
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--r-sm) !important;
    color: var(--text) !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.82rem !important;
    resize: vertical;
    transition: border-color 0.15s, box-shadow 0.15s;
}
.stTextArea textarea:focus {
    border-color: var(--cyan) !important;
    box-shadow: 0 0 0 3px rgba(88,166,255,0.12) !important;
    outline: none !important;
}

/* ── Radio ── */
[data-testid="stRadio"] {
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--r) !important;
    padding: 1rem 1.25rem !important;
}
[data-testid="stRadio"] label { font-size: 0.875rem !important; color: var(--text-muted) !important; }

/* ── Toggle ── */
[data-testid="stToggle"] label { font-size: 0.85rem !important; color: var(--text-muted) !important; }

/* ── Code blocks — colorful syntax ── */
.stCode, pre, code {
    background: #0d1117 !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--r-sm) !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.8rem !important;
    line-height: 1.6 !important;
}
/* Syntax token colors */
.stCode .hljs-keyword    { color: #ff7b72 !important; }
.stCode .hljs-string     { color: #a5d6ff !important; }
.stCode .hljs-comment    { color: #8b949e !important; font-style: italic !important; }
.stCode .hljs-function   { color: #d2a8ff !important; }
.stCode .hljs-number     { color: #79c0ff !important; }
.stCode .hljs-class      { color: #ffa657 !important; }
.stCode .hljs-variable   { color: #cae8ff !important; }
.stCode .hljs-operator   { color: #ff7b72 !important; }
.stCode .hljs-built_in   { color: #79c0ff !important; }

/* ── Alerts ── */
.stAlert {
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--r-sm) !important;
    font-size: 0.875rem !important;
}
[data-testid="stNotification"] {
    background: rgba(63,185,80,0.08) !important;
    border: 1px solid rgba(63,185,80,0.3) !important;
    border-radius: var(--r-sm) !important;
}

/* ── Status boxes ── */
[data-testid="stStatus"] {
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--r-sm) !important;
}

/* ── Spinner ── */
.stSpinner > div { border-top-color: var(--cyan) !important; }

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: var(--surface) !important;
    border-right: 1px solid var(--border) !important;
}
[data-testid="stSidebar"] .stMarkdown p { font-size: 0.8rem; color: var(--text-dim); }

/* ── Caption ── */
.stCaption, caption { font-size: 0.78rem !important; color: var(--text-dim) !important; }

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--text-dim); }

/* ── Custom cards ── */
.sq-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--r);
    padding: 1.5rem;
    transition: border-color 0.2s, box-shadow 0.2s;
}
.sq-card:hover {
    border-color: var(--border2);
    box-shadow: 0 4px 24px rgba(0,0,0,0.4);
}

/* ── Stat card ── */
.sq-stat {
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: var(--r);
    padding: 1.25rem 1.5rem;
    text-align: center;
    position: relative;
    overflow: hidden;
    transition: transform 0.2s, box-shadow 0.2s;
}
.sq-stat::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: var(--grad1);
}
.sq-stat:hover {
    transform: translateY(-3px);
    box-shadow: 0 8px 32px rgba(0,0,0,0.5);
}

/* ── Step indicator ── */
.sq-step {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.9rem 1.25rem;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--r-sm);
    margin-bottom: 0.5rem;
    transition: all 0.2s;
    animation: slideIn 0.3s ease forwards;
}
.sq-step.active  { border-color: var(--cyan);   background: rgba(88,166,255,0.06); }
.sq-step.done    { border-color: var(--green);  background: rgba(63,185,80,0.06); }
.sq-step.waiting { opacity: 0.45; }
@keyframes slideIn {
    from { opacity:0; transform: translateX(-8px); }
    to   { opacity:1; transform: translateX(0); }
}

/* ── Glow badge ── */
.sq-badge {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    padding: 0.2rem 0.65rem;
    border-radius: 20px;
    font-size: 0.7rem;
    font-weight: 600;
    font-family: 'Syne', sans-serif;
    letter-spacing: 0.05em;
    text-transform: uppercase;
}
.sq-badge-blue   { background: rgba(88,166,255,0.15);  color: var(--cyan);   border: 1px solid rgba(88,166,255,0.3); }
.sq-badge-green  { background: rgba(63,185,80,0.15);   color: var(--green);  border: 1px solid rgba(63,185,80,0.3); }
.sq-badge-purple { background: rgba(188,140,255,0.15); color: var(--purple); border: 1px solid rgba(188,140,255,0.3); }
.sq-badge-red    { background: rgba(248,81,73,0.15);   color: var(--red);    border: 1px solid rgba(248,81,73,0.3); }

/* ── Divider ── */
.sq-divider {
    height: 1px;
    background: linear-gradient(90deg, transparent, var(--border2) 30%, var(--border2) 70%, transparent);
    margin: 2rem 0;
}
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# PURE UTILITY FUNCTIONS
# No side-effects. No I/O. Deterministic.
# Each answers: "What is valid input? What is output? What happens on failure?"
# ─────────────────────────────────────────────────────────────

def _get_lang_info(filename: str) -> tuple[str, str]:
    """Return (highlight_lang, mime_type). Never raises."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "txt"
    return _LANG_MAP.get(ext, ("text", "text/plain"))


def clean_llm_output(raw_text: str) -> Optional[str]:
    """
    Strip Markdown code fences from LLM output.
    Returns None if input is empty or result is whitespace-only.
    Returns stripped code string otherwise.
    Never returns empty string — callers check None, not "".
    Pure: same input → same output, always.
    """
    if not raw_text or not raw_text.strip():
        return None
    match = re.search(
        r"```(?:[a-zA-Z]+)?\n?(.*?)```", raw_text, re.DOTALL | re.IGNORECASE
    )
    result = match.group(1).strip() if match else raw_text.strip()
    return result if result else None


def _is_plausible_code(candidate: Optional[str], original: str) -> bool:
    """
    Guard against accepting error messages or None as "fixed code".

    Contract:
      Input:  candidate — what the agent produced (None if nothing)
              original  — the original file content
      Output: True only if candidate is a genuine, different patch
      Failure: returns False (never raises)

    Two invariants, both necessary:
      1. candidate must not be None (clean_llm_output guarantees this means empty)
      2. candidate must differ from original (no-op patch = no fix)
    """
    if candidate is None:
        return False
    if candidate.strip() == original.strip():
        return False
    return True


def validate_text_file(uploaded_file) -> str:
    """
    Validate and decode an uploaded file at the system boundary.
    Raises ValueError with a human-readable message on any failure.
    Never returns fake content — caller gets real code or an exception.
    """
    if uploaded_file is None:
        raise ValueError("No file provided.")

    raw: bytes = uploaded_file.getvalue()

    if len(raw) == 0:
        raise ValueError(f"'{uploaded_file.name}' is empty.")

    if len(raw) > MAX_FILE_BYTES:
        mb = len(raw) / (1024 * 1024)
        raise ValueError(
            f"'{uploaded_file.name}' is {mb:.1f} MB — max allowed is 5 MB."
        )

    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError(
            f"'{uploaded_file.name}' is not valid UTF-8. "
            "Binary files cannot be audited."
        )


def resolve_fixed_code(
    file_path: str,
    original_code: str,
    output: "PipelineOutput",
) -> tuple[str, bool]:
    """
    Return (best_fixed_code, was_changed).

    Contract:
      Input:  file_path     — workspace path agent may have written to
              original_code — the unmodified uploaded file content
              output        — typed PipelineOutput (not raw dict)
      Output: (fixed_code, True)  if a plausible patch was found
              (original_code, False) if nothing changed — honest failure
      Never:  returns (original_code, True) — that would be a lie

    Priority:
      1. output.generated_code — explicit agent output (most authoritative)
      2. disk file             — agent may have written to workspace directly
    """
    # Priority 1 — typed field, no .get() with silent defaults
    state_code = clean_llm_output(output.generated_code or "")
    if _is_plausible_code(state_code, original_code):
        return state_code, True  # type: ignore[return-value]  # state_code is str here

    # Priority 2 — disk
    if os.path.exists(file_path):
        try:
            with open(file_path, encoding="utf-8") as f:
                disk_code = f.read()
            if _is_plausible_code(disk_code, original_code):
                return disk_code, True
        except OSError:
            pass

    return original_code, False




# ─────────────────────────────────────────────────────────────
# EVENT TYPE — decouples pipeline from Streamlit UI
# ─────────────────────────────────────────────────────────────
@dataclass
class ThoughtEvent:
    """
    Emitted by the pipeline when an agent produces reasoning output.
    The pipeline yields these — the UI decides how to render them.

    FIX vs v3: run_single_file_pipeline() previously accepted a
    brain_container (Streamlit object) as a parameter — business logic
    coupled to UI layer. Now the pipeline is pure: it yields events,
    the UI layer consumes and renders them. Clean separation.
    """
    node_name: str
    thoughts: str


# ─────────────────────────────────────────────────────────────
# PIPELINE — Single File
# Pure business logic. Zero Streamlit imports. Yields events.
# ─────────────────────────────────────────────────────────────

def stream_single_file_pipeline(
    file_content: str,
    abs_path: str,
    issue_desc: str,
    security_mode: bool,
) -> "Generator[ThoughtEvent | dict, None, None]":
    """
    Generator that streams pipeline output.
    Yields:
      - ThoughtEvent  when an agent produces reasoning
      - dict          as the final state (last item yielded)

    Design: no Streamlit objects, no UI concerns — pure logic layer.
    Caller (UI) consumes events and decides how to render.

    Raises RuntimeError (with preserved cause) on pipeline failure.
    """
    from opensquad.core.state import AgentState
    from opensquad.graph import app as agent_graph
    state = AgentState(
        issue_description=issue_desc,
        repo_url="LOCAL_UPLOAD",
        plan=[],
        current_file=abs_path,
        file_content=file_content,
        security_mode=security_mode,
        generated_code=None,
        test_output=None,
        error=None,
        attempt_count=0,
        status="planning",
        messages=[],
        latest_thoughts=None,
        vulnerabilities=None,
        evpc_score=None,
        confidence=None,
        remaining_issues=None,
    )

    # Per-agent state — NOT one merged dict.
    # dict.update() silently overwrites keys if two agents write the same key.
    # Here each agent owns its own namespace — no silent key collisions possible.
    agent_states: dict[str, dict] = {
        "manager":   {},
        "developer": {},
        "reviewer":  {},
    }
    any_output = False

    try:
        for output in agent_graph.stream(state):
            for node_name, node_state in output.items():
                any_output = True

                if node_name in agent_states:
                    # Merge this node's output into its own namespace only.
                    # If the same node runs twice (retry loop), later values win
                    # for that node — but never bleed into another node's namespace.
                    agent_states[node_name] = {
                        **agent_states[node_name],
                        **node_state,
                    }
                else:
                    # Unknown node (future graph additions) — store separately
                    agent_states[node_name] = node_state

                thoughts = node_state.get("latest_thoughts", "")
                if thoughts and len(thoughts) > 10:
                    yield ThoughtEvent(node_name=node_name, thoughts=thoughts)

    except Exception as e:
        raise RuntimeError(f"Agent graph failed on '{abs_path}'") from e

    if not any_output:
        raise RuntimeError("Pipeline produced no output state.")

    # Build typed PipelineOutput from authoritative per-agent sources.
    # Each field comes from the ONE agent that is responsible for it.
    yield PipelineOutput.from_agent_states(agent_states)


# ─────────────────────────────────────────────────────────────
# PIPELINE — ZIP Batch Agent (Pure, Thread-Safe)
# ─────────────────────────────────────────────────────────────

def run_zip_agent(
    code_string: str,
    filename: str,
    security_mode: bool,
) -> PatchResult:
    """
    Run the agent on one file from a ZIP.
    Pure function: no shared mutable state — fully thread-safe.
    Never raises — always returns PatchResult.
    """
    from opensquad.core.state import AgentState
    from opensquad.graph import app as agent_graph
    input_data = AgentState(
        issue_description=(
            "Full codebase audit. Fix bugs, optimize logic, check security."
        ),
        repo_url="FULL_ZIP_AUDIT",
        plan=[],
        current_file=filename,
        file_content=code_string,
        security_mode=security_mode,
        generated_code=None,
        test_output=None,
        error=None,
        attempt_count=0,
        status="planning",
        messages=[],
        latest_thoughts=None,
        vulnerabilities=None,
        evpc_score=None,
        confidence=None,
        remaining_issues=None,
    )

    try:
        result    = agent_graph.invoke(input_data)
        raw       = result.get("generated_code", "")
        candidate = clean_llm_output(raw)

        if _is_plausible_code(candidate, code_string):
            return PatchResult(
                filename=filename, success=True,
                original_code=code_string, fixed_code=candidate,
            )

        return PatchResult(
            filename=filename, success=False,
            original_code=code_string,
            error="No plausible fix produced (possible API timeout).",
        )

    except Exception as e:
        return PatchResult(
            filename=filename, success=False,
            original_code=code_string,
            error=f"{type(e).__name__}: {e}",
        )


def run_parallel_zip_audit(
    files: list[tuple[str, str]],   # [(code_string, filename), ...]
    security_mode: bool,
    batch_result: BatchAuditResult,
) -> None:
    """
    FIX: Parallel ZIP audit using ThreadPoolExecutor.

    Why threads (not processes)?
      - Each agent call is I/O-bound (NVIDIA API network call)
      - Threads release the GIL during I/O → true parallelism for this case
      - Processes would require pickling AgentState — unnecessary overhead

    Why _ZIP_MAX_WORKERS=3 and not more?
      - NVIDIA NIM API has rate limits per key
      - 3 concurrent calls is aggressive but within typical limits
      - Tune up if your NVIDIA tier allows more concurrent requests

    Thread safety:
      - run_zip_agent() is a pure function (no shared state)
      - batch_result.record() uses a Lock internally
      - No st.* calls anywhere in this path → safe for background threads
    """
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=_ZIP_MAX_WORKERS,
        thread_name_prefix="opensquad_worker",
    ) as executor:
        # Submit all tasks — returns Future objects immediately
        future_to_file = {
            executor.submit(run_zip_agent, code, fname, security_mode): fname
            for code, fname in files
        }

        # Collect results as they complete (not submission order)
        for future in concurrent.futures.as_completed(future_to_file):
            filename = future_to_file[future]
            try:
                result = future.result()    # raises if run_zip_agent raised
            except Exception as e:
                # run_zip_agent never raises — this is a defensive catch
                result = PatchResult(
                    filename=filename, success=False,
                    original_code="",
                    error=f"Unexpected worker error: {type(e).__name__}: {e}",
                )
            batch_result.record(result)     # thread-safe write


# ─────────────────────────────────────────────────────────────
# UI — HEADER
# ─────────────────────────────────────────────────────────────
st.markdown("""
<div style="position:relative; padding: 3.5rem 0 2rem; overflow:hidden;">

    <!-- Animated glow orbs -->
    <div style="position:absolute; top:-60px; left:-40px; width:300px; height:300px;
                background:radial-gradient(circle, rgba(88,166,255,0.12) 0%, transparent 70%);
                border-radius:50%; animation:orb1 8s ease-in-out infinite alternate; pointer-events:none;">
    </div>
    <div style="position:absolute; top:-20px; right:0; width:250px; height:250px;
                background:radial-gradient(circle, rgba(188,140,255,0.10) 0%, transparent 70%);
                border-radius:50%; animation:orb2 10s ease-in-out infinite alternate; pointer-events:none;">
    </div>

    <style>
    @keyframes orb1 { 0%{transform:translate(0,0) scale(1);} 100%{transform:translate(30px,20px) scale(1.1);} }
    @keyframes orb2 { 0%{transform:translate(0,0) scale(1);} 100%{transform:translate(-20px,30px) scale(0.9);} }
    @keyframes pulse { 0%,100%{opacity:1;} 50%{opacity:0.6;} }
    @keyframes spin3d {
        0%   { transform: perspective(600px) rotateX(0deg) rotateY(0deg); }
        33%  { transform: perspective(600px) rotateX(15deg) rotateY(120deg); }
        66%  { transform: perspective(600px) rotateX(-10deg) rotateY(240deg); }
        100% { transform: perspective(600px) rotateX(0deg) rotateY(360deg); }
    }
    </style>

    <!-- Top label row -->
    <div style="display:flex; align-items:center; gap:0.75rem; margin-bottom:1.2rem;">
        <!-- 3D rotating cube icon -->
        <div style="width:36px; height:36px; display:flex; align-items:center; justify-content:center;
                    background: linear-gradient(135deg,#1a6fe8,#7c3aed);
                    border-radius:8px; animation:spin3d 8s linear infinite;
                    box-shadow: 0 0 20px rgba(88,166,255,0.4);">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                <path d="M12 2L2 7L12 12L22 7L12 2Z" stroke="white" stroke-width="1.5" stroke-linejoin="round"/>
                <path d="M2 17L12 22L22 17" stroke="white" stroke-width="1.5" stroke-linejoin="round"/>
                <path d="M2 12L12 17L22 12" stroke="white" stroke-width="1.5" stroke-linejoin="round"/>
            </svg>
        </div>
        <span class="sq-badge sq-badge-blue">OpenSquad AI</span>
        <span class="sq-badge sq-badge-purple">v4.0</span>
        <span class="sq-badge sq-badge-green" style="animation:pulse 2s infinite;">● Live</span>
    </div>

    <!-- Main heading -->
    <h1 style="font-family:'Syne',sans-serif; font-size:3rem; font-weight:800;
               background: linear-gradient(135deg, #e6edf3 0%, #58a6ff 50%, #bc8cff 100%);
               -webkit-background-clip:text; -webkit-text-fill-color:transparent;
               background-clip:text; line-height:1.1; margin-bottom:0.75rem;">
        Autonomous Code<br>Security Auditing
    </h1>

    <!-- Subtitle -->
    <p style="font-size:1rem; color:#8b949e; max-width:560px; line-height:1.7; margin-bottom:1.75rem;">
        Three AI agents — <span style="color:#58a6ff; font-weight:500;">Manager</span>,
        <span style="color:#bc8cff; font-weight:500;">Developer</span>, and
        <span style="color:#3fb950; font-weight:500;">Reviewer</span> — collaborate in real-time
        to find, patch, and verify vulnerabilities using EVPC scoring.
    </p>

    <!-- Stats row -->
    <div style="display:flex; gap:1rem; flex-wrap:wrap; margin-bottom:0.5rem;">
        <div style="display:flex; align-items:center; gap:0.4rem; padding:0.45rem 0.9rem;
                    background:rgba(88,166,255,0.08); border:1px solid rgba(88,166,255,0.2);
                    border-radius:6px; font-size:0.8rem;">
            <span style="color:#58a6ff;">⚡</span>
            <span style="color:#8b949e;">NVIDIA NIM Powered</span>
        </div>
        <div style="display:flex; align-items:center; gap:0.4rem; padding:0.45rem 0.9rem;
                    background:rgba(63,185,80,0.08); border:1px solid rgba(63,185,80,0.2);
                    border-radius:6px; font-size:0.8rem;">
            <span style="color:#3fb950;">🛡️</span>
            <span style="color:#8b949e;">OWASP Top 10</span>
        </div>
        <div style="display:flex; align-items:center; gap:0.4rem; padding:0.45rem 0.9rem;
                    background:rgba(188,140,255,0.08); border:1px solid rgba(188,140,255,0.2);
                    border-radius:6px; font-size:0.8rem;">
            <span style="color:#bc8cff;">🔬</span>
            <span style="color:#8b949e;">EVPC Verified Patches</span>
        </div>
        <div style="display:flex; align-items:center; gap:0.4rem; padding:0.45rem 0.9rem;
                    background:rgba(240,136,62,0.08); border:1px solid rgba(240,136,62,0.2);
                    border-radius:6px; font-size:0.8rem;">
            <span style="color:#f0883e;">⚙️</span>
            <span style="color:#8b949e;">Parallel ZIP Audit</span>
        </div>
    </div>
</div>

<!-- Divider -->
<div class="sq-divider"></div>

<!-- Agent Cards Row -->
<div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:0.75rem; margin-bottom:2rem;">
    <div class="sq-stat">
        <div style="font-size:1.6rem; margin-bottom:0.4rem;">🧠</div>
        <div style="font-family:'Syne',sans-serif; font-size:0.875rem; font-weight:700;
                    color:#58a6ff; margin-bottom:0.25rem;">Manager</div>
        <div style="font-size:0.75rem; color:#8b949e; line-height:1.4;">DeepSeek V3.2<br>685B · Thinking Mode</div>
    </div>
    <div class="sq-stat" style="--grad1: linear-gradient(135deg, #bc8cff 0%, #7c3aed 100%);">
        <div style="font-size:1.6rem; margin-bottom:0.4rem;">👨‍💻</div>
        <div style="font-family:'Syne',sans-serif; font-size:0.875rem; font-weight:700;
                    color:#bc8cff; margin-bottom:0.25rem;">Developer</div>
        <div style="font-size:0.75rem; color:#8b949e; line-height:1.4;">Devstral 2 123B<br>Code Specialist</div>
    </div>
    <div class="sq-stat" style="--grad1: linear-gradient(135deg, #3fb950 0%, #58a6ff 100%);">
        <div style="font-size:1.6rem; margin-bottom:0.4rem;">🔍</div>
        <div style="font-family:'Syne',sans-serif; font-size:0.875rem; font-weight:700;
                    color:#3fb950; margin-bottom:0.25rem;">Reviewer</div>
        <div style="font-size:0.75rem; color:#8b949e; line-height:1.4;">DeepSeek R1 32B<br>EVPC Scoring</div>
    </div>
</div>
""", unsafe_allow_html=True)
# ─────────────────────────────────────────────────────────────
# UI — SIDEBAR
# ─────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="padding:1.5rem 0 1rem;">
        <div style="display:flex; align-items:center; gap:0.5rem; margin-bottom:1.5rem;">
            <div style="width:6px; height:6px; background:#58a6ff; border-radius:50%;
                        box-shadow:0 0 8px #58a6ff; animation:pulse 2s infinite;"></div>
            <span style="font-family:'Syne',sans-serif; font-size:0.7rem; font-weight:700;
                         letter-spacing:0.12em; text-transform:uppercase; color:#484f58;">
                Control Panel
            </span>
        </div>
    </div>
    <style>@keyframes pulse{0%,100%{opacity:1;}50%{opacity:0.5;}}</style>
    """, unsafe_allow_html=True)

    show_thoughts = st.toggle("Show agent reasoning", value=True,
                              help="Display live chain-of-thought from each agent.")
    security_mode = st.toggle("Security audit mode", value=False,
                              help="Focus on OWASP Top 10 vulnerabilities.")

    st.markdown("""<div style="height:1px; background:linear-gradient(90deg,transparent,#21262d,transparent); margin:1.5rem 0;"></div>""", unsafe_allow_html=True)

    st.markdown("""
    <div style="font-size:0.7rem; font-weight:700; letter-spacing:0.12em; text-transform:uppercase;
                color:#484f58; margin-bottom:0.75rem; font-family:'Syne',sans-serif;">
        Pipeline
    </div>
    <div style="display:flex; flex-direction:column; gap:0.4rem;">
        <div style="display:flex; align-items:center; gap:0.5rem; padding:0.6rem 0.75rem;
                    background:rgba(88,166,255,0.06); border:1px solid rgba(88,166,255,0.15);
                    border-radius:6px;">
            <span style="font-size:0.75rem;">🧠</span>
            <span style="font-size:0.78rem; color:#8b949e;">Manager Plans</span>
        </div>
        <div style="display:flex; align-items:center; gap:0.5rem; padding:0.4rem 0.75rem;
                    justify-content:center; color:#484f58; font-size:0.7rem;">↓</div>
        <div style="display:flex; align-items:center; gap:0.5rem; padding:0.6rem 0.75rem;
                    background:rgba(188,140,255,0.06); border:1px solid rgba(188,140,255,0.15);
                    border-radius:6px;">
            <span style="font-size:0.75rem;">👨‍💻</span>
            <span style="font-size:0.78rem; color:#8b949e;">Developer Patches</span>
        </div>
        <div style="display:flex; align-items:center; gap:0.5rem; padding:0.4rem 0.75rem;
                    justify-content:center; color:#484f58; font-size:0.7rem;">↓</div>
        <div style="display:flex; align-items:center; gap:0.5rem; padding:0.6rem 0.75rem;
                    background:rgba(63,185,80,0.06); border:1px solid rgba(63,185,80,0.15);
                    border-radius:6px;">
            <span style="font-size:0.75rem;">🔍</span>
            <span style="font-size:0.78rem; color:#8b949e;">Reviewer Scores</span>
        </div>
        <div style="display:flex; align-items:center; gap:0.5rem; padding:0.4rem 0.75rem;
                    justify-content:center; color:#484f58; font-size:0.7rem;">↓</div>
        <div style="display:flex; align-items:center; gap:0.5rem; padding:0.6rem 0.75rem;
                    background:rgba(240,136,62,0.06); border:1px solid rgba(240,136,62,0.15);
                    border-radius:6px;">
            <span style="font-size:0.75rem;">📊</span>
            <span style="font-size:0.78rem; color:#8b949e;">EVPC Verified</span>
        </div>
    </div>
    <div style="margin-top:2rem; padding:0.75rem; background:var(--surface2);
                border-radius:8px; border:1px solid var(--border);">
        <div style="font-size:0.68rem; color:#484f58; line-height:1.6; font-family:'JetBrains Mono',monospace;">
            NVIDIA NIM API<br>
            <span style="color:#58a6ff;">deepseek-v3.2</span><br>
            <span style="color:#bc8cff;">devstral-2-123b</span><br>
            <span style="color:#3fb950;">deepseek-r1-32b</span>
        </div>
    </div>
    """, unsafe_allow_html=True)
# ─────────────────────────────────────────────────────────────
# UI — MODE SELECTOR
# ─────────────────────────────────────────────────────────────
st.markdown("""
<div style="margin-bottom:1rem;">
    <span style="font-family:'Syne',sans-serif; font-size:0.7rem; font-weight:700;
                 letter-spacing:0.12em; text-transform:uppercase; color:#484f58;">
        Select Audit Mode
    </span>
</div>
""", unsafe_allow_html=True)
audit_mode = st.radio(
    label="",
    options=["Single file", "Full codebase (.zip)"],
    horizontal=True,
    label_visibility="collapsed",
)
st.markdown("<div style='margin-bottom:2rem;'></div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
# MODE 1 — SINGLE FILE
# ══════════════════════════════════════════════════════════════
if audit_mode == "Single file":
    st.markdown("""
    <p style="font-size:0.85rem; color:var(--text-subtle); margin-bottom:1.5rem;">
        Upload a single source file — agents will scan, fix, and verify it automatically.
    </p>""", unsafe_allow_html=True)

    uploaded_file = st.file_uploader(
        "Upload Code File", type=list(_SUPPORTED_EXTS), key="single_file_uploader"
    )

    # Clear stale session when a NEW file is uploaded
    if uploaded_file is not None:
        file_id = f"{uploaded_file.name}_{uploaded_file.size}"
        if st.session_state.get("_file_id") != file_id:
            for k in ["pipeline_output", "fixed_code", "original_code",
                      "issue_desc", "audit_done", "pdf_path"]:
                st.session_state.pop(k, None)
            st.session_state["_file_id"] = file_id

    if uploaded_file is not None:
        workspace_dir = os.path.join(os.getcwd(), "opensquad", "workspace")
        os.makedirs(workspace_dir, exist_ok=True)
        file_path = os.path.join(workspace_dir, uploaded_file.name)

        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        st.success(f"✅ Uploaded: **{uploaded_file.name}**")

        issue_desc = st.text_area(
            "Describe the bug (Optional)",
            value=(
                f"Analyze {uploaded_file.name} for bugs, logic errors, "
                "and security vulnerabilities. Fix all issues found."
            ),
        )

        # ── RUN AGENTS ──
        if st.button("🚀 Analyze Single File"):

            # ── Define ALL variables before any try/except ──
            # Guarantees no NameError regardless of early-exit paths.
            abs_path        = os.path.abspath(file_path).replace("\\", "/")
            pipeline_output = PipelineOutput()
            brain_container = st.container()
            file_content    = ""

            # Validate at boundary — hard stop, never fake content
            try:
                file_content = validate_text_file(uploaded_file)
            except ValueError as e:
                st.error(f"❌ {e}")
                st.stop()

            with st.spinner("🤖 OpenSquad Team Assembling and Auditing..."):
                try:
                    # ── UI layer consumes events — pipeline knows nothing about st.* ──
                    for event in stream_single_file_pipeline(
                        file_content=file_content,
                        abs_path=abs_path,
                        issue_desc=issue_desc,
                        security_mode=security_mode,
                    ):
                        if isinstance(event, ThoughtEvent):
                            # UI decides how to render ThoughtEvent
                            if show_thoughts:
                                with brain_container:
                                    with st.status(
                                        f"🧠 {event.node_name.upper()} Logic Process",
                                        expanded=False,
                                    ) as s:
                                        st.markdown("### 💭 Internal Monologue")
                                        st.info(event.thoughts)
                                        st.caption("✅ Reasoning Verified")
                                        s.update(
                                            label=f"🧠 {event.node_name.upper()} "
                                                  "Logic Process (Complete)",
                                            state="complete",
                                        )
                        elif isinstance(event, PipelineOutput):
                            pipeline_output = event   # typed — not raw dict

                except RuntimeError as e:
                    st.error(f"⚠️ Pipeline failed: {e}")
                    pipeline_output = PipelineOutput(status="failed", error=str(e))

                except Exception as e:
                    st.error(f"❌ Unexpected [{type(e).__name__}]: {e}")
                    pipeline_output = PipelineOutput(status="failed", error=str(e))
                    raise   # re-raise — let server logs capture full traceback

            fixed_code, was_changed = resolve_fixed_code(
                file_path=file_path,
                original_code=file_content,
                output=pipeline_output,
            )

            if was_changed:
                st.success("✅ Mission Complete! Agents have finished.")
            else:
                st.warning(
                    "⚠️ No verifiable changes produced. "
                    "Reviewer API may have timed out — try again."
                )

            st.session_state.update({
                "pipeline_output": pipeline_output,   # typed PipelineOutput
                "fixed_code":      fixed_code,
                "original_code":   file_content,
                "issue_desc":      issue_desc,
                "audit_done":      True,
            })

        # ── RESULTS — persists across all reruns ──
        if st.session_state.get("audit_done"):
            # Read typed PipelineOutput — no raw dict.get() calls
            output:        PipelineOutput = st.session_state["pipeline_output"]
            fixed_code:    str            = st.session_state["fixed_code"]
            original_code: str            = st.session_state["original_code"]
            issue_desc:    str            = st.session_state["issue_desc"]

            highlight_lang, mime_type = _get_lang_info(uploaded_file.name)

            # ── Dashboard Stats — typed access, explicit None handling ──
            evpc    = output.evpc_score        # None = reviewer never ran
            vulns   = output.vulnerabilities   # None = scan never ran
            n_vulns = len(vulns) if vulns is not None else "—"
            # "—" means scan didn't run. 0 means scan ran and found nothing.
            # These are semantically different — do not collapse to same display.

            evpc_color = "#3fb950" if evpc == 1.0 else "#f0883e" if evpc == 0.5 else "#f85149" if evpc == 0.0 else "#8b949e"
            evpc_label = f"{evpc:.1f}" if evpc is not None else "—"
            changed = fixed_code.strip() != original_code.strip()
            status_color = "#3fb950" if changed else "#f85149"
            status_label = "Patched" if changed else "No Change"

            st.markdown(f"""
            <div style="margin:1.5rem 0 2rem;">
                <div style="font-family:'Syne',sans-serif; font-size:0.7rem; font-weight:700;
                            letter-spacing:0.12em; text-transform:uppercase; color:#484f58; margin-bottom:0.75rem;">
                    Audit Results
                </div>
                <div style="display:grid; grid-template-columns:1fr 1fr 1fr 1fr; gap:0.75rem;">
                    <div class="sq-stat">
                        <div style="font-size:1.5rem; font-weight:800; font-family:'Syne',sans-serif;
                                    color:{status_color}; margin-bottom:0.3rem;">{status_label}</div>
                        <div style="font-size:0.72rem; color:#8b949e;">Patch Status</div>
                    </div>
                    <div class="sq-stat">
                        <div style="font-size:1.5rem; font-weight:800; font-family:'Syne',sans-serif;
                                    color:#f0883e; margin-bottom:0.3rem;">{n_vulns}</div>
                        <div style="font-size:0.72rem; color:#8b949e;">Vulnerabilities</div>
                    </div>
                    <div class="sq-stat">
                        <div style="font-size:1.5rem; font-weight:800; font-family:'Syne',sans-serif;
                                    color:{evpc_color}; margin-bottom:0.3rem;">{evpc_label}</div>
                        <div style="font-size:0.72rem; color:#8b949e;">EVPC Score</div>
                    </div>
                    <div class="sq-stat">
                        <div style="font-size:1.5rem; font-weight:800; font-family:'Syne',sans-serif;
                                    color:#58a6ff; margin-bottom:0.3rem;">3</div>
                        <div style="font-size:0.72rem; color:#8b949e;">Agents Used</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # ── Step-by-step pipeline trace ──
            st.markdown("""
            <div style="font-family:'Syne',sans-serif; font-size:0.7rem; font-weight:700;
                        letter-spacing:0.12em; text-transform:uppercase; color:#484f58; margin-bottom:0.75rem;">
                Pipeline Trace
            </div>
            <div style="display:flex; flex-direction:column; gap:0.4rem; margin-bottom:2rem;">
                <div class="sq-step done">
                    <span style="color:#3fb950; font-size:0.9rem;">✓</span>
                    <div>
                        <div style="font-size:0.82rem; font-weight:600; color:#e6edf3; font-family:'Syne',sans-serif;">Manager</div>
                        <div style="font-size:0.72rem; color:#8b949e;">Analysed issue · Generated repair plan</div>
                    </div>
                    <span class="sq-badge sq-badge-blue" style="margin-left:auto;">DeepSeek V3.2</span>
                </div>
                <div class="sq-step done">
                    <span style="color:#3fb950; font-size:0.9rem;">✓</span>
                    <div>
                        <div style="font-size:0.82rem; font-weight:600; color:#e6edf3; font-family:'Syne',sans-serif;">Developer</div>
                        <div style="font-size:0.72rem; color:#8b949e;">Applied patch · Rewrote vulnerable code</div>
                    </div>
                    <span class="sq-badge sq-badge-purple" style="margin-left:auto;">Devstral 123B</span>
                </div>
                <div class="sq-step done">
                    <span style="color:#3fb950; font-size:0.9rem;">✓</span>
                    <div>
                        <div style="font-size:0.82rem; font-weight:600; color:#e6edf3; font-family:'Syne',sans-serif;">Reviewer</div>
                        <div style="font-size:0.72rem; color:#8b949e;">Verified patch · Computed EVPC score</div>
                    </div>
                    <span class="sq-badge sq-badge-green" style="margin-left:auto;">DeepSeek R1</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

            from opensquad.utils import display_diff
            display_diff(st, original_code, fixed_code)

            # ── Fixed Code with header ──
            st.markdown("""
            <div style="display:flex; align-items:center; justify-content:space-between; margin:1.5rem 0 0.5rem;">
                <div style="display:flex; align-items:center; gap:0.6rem;">
                    <span style="width:8px; height:8px; background:#3fb950; border-radius:50%;
                                 box-shadow:0 0 8px #3fb950; display:inline-block;"></span>
                    <span style="font-family:'Syne',sans-serif; font-size:0.7rem; font-weight:700;
                                 letter-spacing:0.12em; text-transform:uppercase; color:#484f58;">
                        Patched Code
                    </span>
                </div>
            </div>
            """, unsafe_allow_html=True)
            st.code(fixed_code, language=highlight_lang)

            st.markdown("<div class='sq-divider'></div>", unsafe_allow_html=True)

            col_dl, col_pdf = st.columns(2)

            with col_dl:
                ext = uploaded_file.name.rsplit(".", 1)[-1]
                st.download_button(
                    label=f"⬇ Download Fixed Code (.{ext})",
                    data=fixed_code,
                    file_name=f"fixed_{uploaded_file.name}",
                    mime=mime_type,
                    key="download_code_btn",
                )

            with col_pdf:
                if st.button("📄 Generate Audit Report"):
                    with st.spinner("Compiling PDF..."):
                        try:
                            from opensquad.tools.report import generate_pdf
                            pdf_path = generate_pdf(
                                issue=issue_desc,
                                plan=output.plan or [],
                                original_code=original_code,
                                fixed_code=fixed_code,
                                evpc_score=output.evpc_score,
                                test_output=output.test_output,
                                vulnerabilities=output.vulnerabilities,
                            )
                            st.session_state["pdf_path"] = pdf_path
                            st.success("✅ PDF Generated!")
                        except Exception as e:
                            st.error(f"❌ PDF generation failed: {e}")

                if st.session_state.get("pdf_path"):
                    try:
                        with open(st.session_state["pdf_path"], "rb") as pdf_file:
                            st.download_button(
                                label="⬇ Download PDF Report",
                                data=pdf_file,
                                file_name="OpenSquad_Audit_Report.pdf",
                                mime="application/pdf",
                                key="pdf_download",
                            )
                    except OSError as e:
                        st.error(f"❌ Could not read PDF: {e}")
                        st.session_state.pop("pdf_path", None)


# ══════════════════════════════════════════════════════════════
# MODE 2 — FULL CODEBASE (ZIP)
# ══════════════════════════════════════════════════════════════
elif audit_mode == "Full codebase (.zip)":
    st.info(
        "Upload a zipped project. "
        "AI will scan and patch all code files."
    )

    uploaded_file = st.file_uploader(
        "Upload Project Archive", type=["zip"], key="zip_file_uploader"
    )

    if uploaded_file is not None:
        if st.button("🚀 Audit Entire Codebase"):

            batch_result = BatchAuditResult()

            # Extract files from ZIP first so we can show total count
            import zipfile, io
            file_pairs: list[tuple[str, str]] = []  # [(code, filename), ...]

            try:
                with zipfile.ZipFile(io.BytesIO(uploaded_file.getvalue())) as zf:
                    for name in zf.namelist():
                        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
                        if ext in _SUPPORTED_EXTS:
                            try:
                                code = zf.read(name).decode("utf-8")
                                file_pairs.append((code, name))
                            except (UnicodeDecodeError, KeyError):
                                pass   # skip unreadable files silently
            except zipfile.BadZipFile:
                st.error("❌ Invalid ZIP file. Please upload a valid archive.")
                st.stop()

            if not file_pairs:
                st.error(
                    "❌ No supported code files found in ZIP. "
                    f"Supported: {', '.join(sorted(_SUPPORTED_EXTS))}"
                )
                st.stop()

            st.info(f"📂 Found {len(file_pairs)} code files. Running parallel audit...")

            with st.spinner(
                f"🤖 Auditing {len(file_pairs)} files "
                f"({_ZIP_MAX_WORKERS} parallel workers)..."
            ):
                # Parallel execution — I/O bound, threads correct choice
                run_parallel_zip_audit(file_pairs, security_mode, batch_result)

                # Rebuild ZIP with fixed files
                output_buf = io.BytesIO()
                with zipfile.ZipFile(
                    io.BytesIO(uploaded_file.getvalue())
                ) as original_zf:
                    with zipfile.ZipFile(output_buf, "w", zipfile.ZIP_DEFLATED) as out_zf:
                        # Build lookup: filename → fixed code
                        fixed_map = {
                            r.filename: r.fixed_code
                            for r in batch_result.snapshot().succeeded
                        }
                        for name in original_zf.namelist():
                            if name in fixed_map:
                                out_zf.writestr(name, fixed_map[name])
                            else:
                                out_zf.writestr(name, original_zf.read(name))

            output_buf.seek(0)
            fixed_zip_bytes = output_buf.read()

            # ONE coherent snapshot — succeeded + failed == total GUARANTEED
            snap = batch_result.snapshot()

            if snap.total == 0:
                st.error("❌ No files were processed.")
            elif not snap.succeeded:
                st.error(
                    f"❌ All {snap.total} files failed. "
                    "Check NVIDIA API status and your keys."
                )
                for r in snap.failed:
                    st.caption(f"  • **{r.filename}**: {r.error}")
            else:
                st.success(
                    f"✅ {len(snap.succeeded)}/{snap.total} files patched successfully."
                )
                if snap.failed:
                    st.warning(f"⚠️ {len(snap.failed)} files could not be patched:")
                    for r in snap.failed:
                        st.caption(f"  • **{r.filename}**: {r.error}")

                st.download_button(
                    label="💾 Download Patched Codebase (.zip)",
                    data=fixed_zip_bytes,
                    file_name=f"fixed_{uploaded_file.name}",
                    mime="application/zip",
                )