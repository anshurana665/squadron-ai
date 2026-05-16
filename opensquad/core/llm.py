"""
opensquad/core/llm.py

OpenRouter Gemma 3 27B Client for Manager, Developer, and Reviewer.
Endpoint: https://openrouter.ai/api/v1  (OpenAI-compatible)
Model:    google/gemma-3-27b-it
"""

import re
import time
import logging
import httpx
import json

logger = logging.getLogger("opensquad.llm")
from openai import OpenAI, RateLimitError, AuthenticationError, APIError
from opensquad.config import Config


# ═══════════════════════════════════════════════════════════════════════
# GROQ CLIENT — 500+ tok/sec hardware inference for Developer + Reviewer
# ═══════════════════════════════════════════════════════════════════════

class GroqClient:
    """Uses Groq's hardware-accelerated API for 5-10x faster inference."""
    GROQ_BASE_URL = "https://api.groq.com/openai/v1"
    _NETWORK_ERRORS = (httpx.RemoteProtocolError, httpx.ReadError,
                      httpx.TimeoutException, httpx.ConnectError, ConnectionError)

    def __init__(self, model: str, params: dict):
        self.model = model
        # Strip params not supported by Groq
        self.params = {k: v for k, v in params.items() if k in ("temperature", "max_tokens", "top_p")}
        self.client = OpenAI(
            base_url=self.GROQ_BASE_URL,
            api_key=Config.GROQ_API_KEY,
            timeout=45.0,
        )

    def generate(self, messages: list[dict], return_thinking: bool = False) -> str:
        for attempt in range(3):
            try:
                completion = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    stream=True,
                    **self.params,
                )
                buf = []
                for chunk in completion:
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if delta and getattr(delta, 'content', None):
                        buf.append(delta.content)
                return "".join(buf)
            except RateLimitError:
                logger.warning(f"Groq rate limit hit, retry {attempt+1}/3")
                time.sleep(2 ** attempt)
            except self._NETWORK_ERRORS as e:
                logger.warning(f"Groq network error: {e}, retry {attempt+1}")
                time.sleep(1)
            except Exception as e:
                logger.error(f"Groq generate failed: {e}")
                break
        return ""

# ═══════════════════════════════════════════════════════════════════════
# OPENROUTER CLIENT
# ═══════════════════════════════════════════════════════════════════════

class OpenRouterClient:
    """
    Client for OpenRouter running google/gemma-3-27b-it.
    Uses stream=True for responsive output.
    """
    _last_call_time: float = 0.0

    _NETWORK_ERRORS = (
        httpx.RemoteProtocolError,
        httpx.ReadError,
        httpx.TimeoutException,
        httpx.ConnectError,
        httpx.WriteError,
        ConnectionError,
        ConnectionResetError,
    )

    def __init__(self, api_key: str, model: str, params: dict):
        self.api_key = api_key
        self.client = self._make_client(api_key)
        self.model = model
        self.params = params

    @staticmethod
    def _make_client(api_key: str) -> OpenAI:
        return OpenAI(
            base_url=Config.OPENROUTER_BASE_URL,
            api_key=api_key,
            timeout=180.0,
            default_headers={
                "HTTP-Referer": "https://squadron.ai",
                "X-Title": "OpenSquad AI",
            },
        )

    def _throttle(self):
        elapsed = time.time() - OpenRouterClient._last_call_time
        wait = Config.MIN_SECONDS_BETWEEN_CALLS - elapsed
        if wait > 0:
            time.sleep(wait)
        OpenRouterClient._last_call_time = time.time()

    def generate(self, messages: list[dict], return_thinking: bool = False) -> str | tuple[str, str]:
        for attempt in range(Config.MAX_RETRIES + 1):
            try:
                self._throttle()

                completion = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    stream=True,
                    **self.params,
                )

                thinking_buf = []
                answer_buf = []

                for chunk in completion:
                    if not getattr(chunk, "choices", None):
                        continue
                    if len(chunk.choices) == 0 or getattr(chunk.choices[0], "delta", None) is None:
                        continue

                    delta = chunk.choices[0].delta

                    # Extract reasoning/thinking tokens if model provides them
                    reasoning = getattr(delta, "reasoning_content", None)
                    if reasoning:
                        thinking_buf.append(reasoning)

                    # Extract normal content tokens
                    content = getattr(delta, "content", None)
                    if content:
                        answer_buf.append(content)

                thinking = "".join(thinking_buf)
                answer = "".join(answer_buf)

                if return_thinking:
                    return thinking, answer
                return answer

            except RateLimitError:
                wait = min(2 ** attempt, 30)
                if attempt < Config.MAX_RETRIES:
                    logger.warning(f"OpenRouter rate limit hit -- retrying in {wait}s")
                    time.sleep(wait)
                else:
                    raise
            except AuthenticationError:
                raise RuntimeError(
                    "OpenRouter API key invalid. Check OPENROUTER_API_KEY in your .env file."
                )
            except APIError as e:
                wait = min(2 ** attempt, 30)
                if attempt < Config.MAX_RETRIES:
                    logger.warning(f"OpenRouter API error ({e}) -- retrying in {wait}s")
                    time.sleep(wait)
                else:
                    raise RuntimeError(f"OpenRouter API error: {e}") from e
            except self._NETWORK_ERRORS as e:
                wait = min(2 ** attempt, 30)
                if attempt < Config.MAX_RETRIES:
                    self.client = self._make_client(self.api_key)
                    logger.warning(f"OpenRouter connection issue ({type(e).__name__}) -- retrying in {wait}s")
                    time.sleep(wait)
                else:
                    raise RuntimeError(f"OpenRouter network failure: {e}") from e
            except Exception as e:
                wait = min(2 ** attempt, 30)
                if attempt < Config.MAX_RETRIES:
                    self.client = self._make_client(self.api_key)
                    logger.warning(f"Unexpected error ({type(e).__name__}) -- retrying in {wait}s")
                    time.sleep(wait)
                else:
                    raise RuntimeError(f"OpenRouter API failure: {e}") from e

        if return_thinking:
            return "", ""
        return ""


# ═══════════════════════════════════════════════════════════════════════
# 3 DEDICATED AGENT CLIENTS
# ═══════════════════════════════════════════════════════════════════════

class ManagerLLM(OpenRouterClient):
    def __init__(self):
        super().__init__(
            api_key=Config.OPENROUTER_API_KEY,
            model=Config.REASONING_MODEL,
            params=Config.MANAGER_PARAMS,
        )

    def plan(self, file_content: str, issue: str, security_mode: bool) -> tuple[str, str]:
        security_note = (
            "SECURITY MODE IS ON. Focus on OWASP Top 10. "
            "Tag each vulnerability with its CWE ID (e.g., CWE-89 for SQL Injection)."
            if security_mode else
            "Focus on bugs, logic errors, and code quality."
        )

        system = """You are the Lead Security Architect and Engineering Manager for OpenSquad. 
Your job is to analyze the user's issue and output a strict, step-by-step JSON remediation plan for the Developer Agent.

**CRITICAL RULES:**
1. **DO NOT GUESS OR HALLUCINATE.** You cannot see the codebase automatically.
2. You MUST use the `search_codebase` tool to find where the bug or vulnerability might live.
3. Once you identify a suspicious file, you MUST use the `read_file` tool to inspect its exact contents before writing your plan.
4. If you are in "Security Mode", prioritize hunting for OWASP Top 10 vulnerabilities (SQLi, XSS, Deadlocks).

**PLANNING FORMAT:**
Your final output must be a valid JSON object detailing exactly which files to patch and the logical steps to fix them. Do not write the code yourself; write the blueprint."""

        prompt = f"""ISSUE REPORTED: {issue}

CODE TO ANALYZE:
```
{file_content}
```

Produce the repair plan now."""

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        return self.generate(messages, return_thinking=True)


class DeveloperLLM:
    def __init__(self):
        if Config.GROQ_API_KEY:
            logger.info("Developer using Groq (fast path)")
            self._client = GroqClient(
                model="llama-3.3-70b-versatile",
                params={"temperature": 0.15, "max_tokens": 8192, "top_p": 0.95},
            )
        else:
            logger.info("Developer using OpenRouter (fallback)")
            self._client = OpenRouterClient(
                api_key=Config.OPENROUTER_API_KEY,
                model=Config.CODING_MODEL,
                params=Config.DEVELOPER_PARAMS,
            )

    def generate(self, messages: list[dict], return_thinking: bool = False) -> str:
        return self._client.generate(messages, return_thinking=return_thinking)

    def patch(self, file_content: str, plan: list[str], error_feedback: str = "") -> str:
        plan_text = "\n".join(f"  {i+1}. {step}" for i, step in enumerate(plan))

        retry_note = (
            f"\n\nPREVIOUS PATCH FAILED WITH THIS ERROR -- FIX IT:\n{error_feedback}"
            if error_feedback else ""
        )

        system = """<system_identity>
You are the Principal Staff Software Engineer for OpenSquad AI (Internal Designation: L8_EXECUTIONER). Your objective is to ingest the Architect's JSON remediation plan and output flawless, production-ready, secure, and highly optimized code. 
</system_identity>

<enterprise_coding_standards>
You are bound by the following immutable laws. Violation of any law will result in immediate termination of the execution thread.

LAW 1: ANTI-LAZINESS PROTOCOL (CRITICAL)
- You MUST output the ENTIRE, complete, and fully functional file.
- You are strictly forbidden from using placeholders such as `# ... rest of code remains the same`, `// TODO`, or `pass` unless explicitly required by the logic.
- If a file is 500 lines long and you modify line 50, you must output all 500 lines.

LAW 2: STATE MUTATION & MEMORY SAFETY
- NEVER use mutable objects (`[]`, `{}`, `set()`) as default arguments in Python function or method signatures. 
- You must use `None` and initialize the mutable object inside the function scope.

LAW 3: CONCURRENCY & LOCK ACQUISITION
- NEVER use a single global `threading.Lock()` to wrap an entire class or block of network/DB operations. This destroys system throughput.
- You MUST use granular locks. When acquiring multiple locks, you MUST implement Lock Ordering (e.g., sorting objects by a unique ID before acquiring) to mathematically guarantee the prevention of deadlocks.

LAW 4: ERROR SEMANTICS
- NEVER use a bare `except:` or blanket `except Exception as e:` block.
- You must catch specific exceptions (e.g., `ValueError`, `KeyError`, `sqlite3.IntegrityError`).
- Exceptions must be logged using `logging.error` or `logging.exception`. Do not use `print()`.

LAW 5: DATA SANITIZATION
- All database queries MUST be parameterized. String formatting (f-strings, `.format()`, `%s`) inside SQL statements is strictly forbidden.
- All JSON parsing must be wrapped in `try...except json.JSONDecodeError`.
</enterprise_coding_standards>

<cognitive_workflow>
You must process the task using the following sequential XML tags.

1. <plan_ingestion>
   - Summarize the Architect's JSON plan. What files are you modifying? What is the goal?
</plan_ingestion>

2. <code_scratchpad>
   - Write out the exact modifications you are going to make.
   - Cross-reference your planned modifications against the 5 LAWS in the <enterprise_coding_standards>. 
   - Explicitly confirm in writing: "I have checked for mutable defaults. I have checked for lock ordering. I have checked for bare exceptions."
</code_scratchpad>

3. <final_executable_code>
   - Output the complete code inside a standard markdown code block.
   - Example:
   ```python
   # FULL CODE HERE
   ```
</final_executable_code>
</cognitive_workflow>"""

        prompt = f"""REPAIR PLAN FROM MANAGER:
{plan_text}
{retry_note}

ORIGINAL CODE TO FIX:
{file_content}

Output the complete patched file now:"""

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        return self.generate(messages, return_thinking=False)


class ReviewerLLM:
    def __init__(self):
        if Config.GROQ_API_KEY:
            logger.info("Reviewer using Groq (fast path)")
            self._client = GroqClient(
                model="llama-3.1-8b-instant",
                params={"temperature": 0.1, "max_tokens": 2048, "top_p": 0.95},
            )
        else:
            logger.info("Reviewer using OpenRouter (fallback)")
            self._client = OpenRouterClient(
                api_key=Config.OPENROUTER_API_KEY,
                model=Config.REVIEWER_MODEL,
                params=Config.REVIEWER_PARAMS,
            )

    def generate(self, messages: list[dict], return_thinking: bool = False) -> str:
        return self._client.generate(messages, return_thinking=return_thinking)

    def review(
        self,
        original_code: str,
        patched_code: str,
        e2b_stdout: str,
        e2b_exit_code: int,
        plan: list[str],
    ) -> dict:
        system = """<system_identity>
You are the Lead QA Automation Engineer and Security Auditor for OpenSquad AI (Internal Designation: L8_AUDITOR). You are ruthless, unforgiving, and detail-oriented. Your objective is to perform Static Code Analysis on the Developer Agent's output BEFORE it is allowed to be dynamically tested in the Sandbox.
</system_identity>

<audit_checklist>
You must scan the Developer's submitted code line-by-line for the following fatal infractions:

[ ] 1. TRUNCATION: Did the developer use comments like `# ... rest of class` or `# remaining code`? 
[ ] 2. MUTABLE DEFAULTS: Are there lists or dicts in function signatures? (e.g., `def func(val=[])`)
[ ] 3. THREADING BOTTLENECKS: Is there a `with self.lock:` wrapping a massive block or multiple separate objects without Lock Ordering?
[ ] 4. ERROR SWALLOWING: Is there a bare `except:` or `except Exception:`?
[ ] 5. INJECTION VULNERABILITIES: Are f-strings or `.format()` used to build SQL queries or shell commands?
[ ] 6. UNHANDLED JSON: Is `json.loads()` called without catching `json.JSONDecodeError`?
</audit_checklist>

<cognitive_workflow>
You must process the Developer's code using the following XML tags:

1. <line_by_line_audit>
   - Walk through the code. State explicitly if you find any of the 6 infractions from the checklist.
</line_by_line_audit>

2. <final_verdict>
Output a strictly valid JSON object matching this exact schema (do NOT wrap the JSON inside markdown fences, output raw JSON ONLY inside this tag):
{
  "status": "APPROVED" | "REJECTED",
  "fatal_infractions_found": ["List the specific rules broken, or empty if APPROVED"],
  "developer_feedback": "If REJECTED, provide a scathing, precise instruction on exactly which line to fix and why. If APPROVED, output 'Proceed to Sandbox'."
}
</final_verdict>
</cognitive_workflow>"""

        plan_text = chr(10).join(f'  {i+1}. {s}' for i, s in enumerate(plan))
        sandbox_output = e2b_stdout[:1000] if e2b_stdout else "(no output)"

        prompt = f"""ORIGINAL CODE:
{original_code[:2000]}

PATCHED CODE:
{patched_code[:2000]}

PLAN THAT WAS FOLLOWED:
{plan_text}

SANDBOX OUTPUT:
{sandbox_output} (exit code: {e2b_exit_code})

Does the patch correctly fix the vulnerability? Reply in the exact format specified."""

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        # Generate output
        raw = self.generate(messages, return_thinking=False)

        # Parse strict JSON response
        try:
            # 1. Try extracting from <final_verdict> tag
            xml_match = re.search(r'<final_verdict>\s*(\{.*?\})\s*</final_verdict>', raw, re.DOTALL | re.IGNORECASE)
            if xml_match:
                parsed = json.loads(xml_match.group(1))
            else:
                # Fallback to finding any JSON-like block
                match = re.search(r'\{.*\}', raw, re.DOTALL)
                parsed = json.loads(match.group()) if match else {}

            status = "APPROVED" if "APPROV" in str(parsed.get("status", parsed.get("verdict", ""))).upper() else "REJECTED"
            return {
                "status":                  status,
                "developer_feedback":      str(parsed.get("developer_feedback", parsed.get("feedback", parsed.get("reason", "")))),
                "fatal_infractions_found": list(parsed.get("fatal_infractions_found", parsed.get("remaining_issues", []))),
                "evpc_score":              1.0 if status == "APPROVED" else 0.0,
            }
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

        # Fallback if parsing fails
        status = "APPROVED" if e2b_exit_code == 0 else "REJECTED"
        return {
            "status":                  status,
            "developer_feedback":      raw[:500] if raw else "Review failed.",
            "fatal_infractions_found": [],
            "evpc_score":              0.5 if e2b_exit_code == 0 else 0.0,
        }


# ═══════════════════════════════════════════════════════════════════════
# CONVENIENCE FACTORY
# ═══════════════════════════════════════════════════════════════════════

class LLMProvider:
    _manager_instance   = None
    _developer_instance = None
    _reviewer_instance  = None

    @classmethod
    def manager(cls) -> ManagerLLM:
        if cls._manager_instance is None:
            cls._manager_instance = ManagerLLM()
        return cls._manager_instance

    @classmethod
    def developer(cls) -> DeveloperLLM:
        if cls._developer_instance is None:
            cls._developer_instance = DeveloperLLM()
        return cls._developer_instance

    @classmethod
    def reviewer(cls) -> ReviewerLLM:
        if cls._reviewer_instance is None:
            cls._reviewer_instance = ReviewerLLM()
        return cls._reviewer_instance

    def generate(self, prompt: str, model: str = "coding") -> str:
        router = {
            "reasoning": self.manager(),
            "coding":    self.developer(),
            "reviewing": self.reviewer(),
        }
        client = router.get(model, self.developer())
        return client.generate([{"role": "user", "content": prompt}], return_thinking=False)
