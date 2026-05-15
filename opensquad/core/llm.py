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

        system = f"""You are the Manager Agent of OpenSquad, an elite AI security team.
Your ONLY job: analyze code and produce a precise, actionable repair plan.

STRICT OUTPUT RULES:
1. Output ONLY a valid JSON list of strings. Zero markdown. Zero explanation outside JSON.
2. Each item = one specific action for the Developer agent.
3. Maximum 5 steps. Be surgical.
4. {security_note}

EXAMPLE OUTPUT:
["Step 1: Replace string-concatenated SQL query on line 4 with parameterized query (CWE-89).",
 "Step 2: Add input length validation before query execution.",
 "Step 3: Wrap DB call in try/except sqlite3.Error, not bare Exception."]"""

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


class DeveloperLLM(OpenRouterClient):
    def __init__(self):
        super().__init__(
            api_key=Config.OPENROUTER_API_KEY,
            model=Config.CODING_MODEL,
            params=Config.DEVELOPER_PARAMS,
        )

    def patch(self, file_content: str, plan: list[str], error_feedback: str = "") -> str:
        plan_text = "\n".join(f"  {i+1}. {step}" for i, step in enumerate(plan))

        retry_note = (
            f"\n\nPREVIOUS PATCH FAILED WITH THIS ERROR -- FIX IT:\n{error_feedback}"
            if error_feedback else ""
        )

        system = """You are the Developer Agent of OpenSquad. You write production-grade, secure code.

ENTERPRISE RULESET -- NEVER VIOLATE:
1. NEVER use blanket `except Exception: pass` -- handle specific exceptions only.
2. NEVER build SQL queries with string concatenation -- always use parameterized queries (? or %s).
3. NEVER hardcode secrets, API keys, or passwords.
4. NEVER use eval() or exec() on user input.
5. ALWAYS validate and sanitize user inputs before use.
6. Output ONLY the complete fixed code. No explanation. No markdown fences. No comments like "# Fixed".
7. Follow the Manager's plan EXACTLY -- do not skip any step."""

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


class ReviewerLLM(OpenRouterClient):
    def __init__(self):
        super().__init__(
            api_key=Config.OPENROUTER_API_KEY,
            model=Config.REVIEWER_MODEL,
            params=Config.REVIEWER_PARAMS,
        )

    def review(
        self,
        original_code: str,
        patched_code: str,
        e2b_stdout: str,
        e2b_exit_code: int,
        plan: list[str],
    ) -> dict:
        system = """You are a senior security code reviewer in an autonomous patching pipeline.

Your job is to evaluate whether a patch correctly fixes the reported vulnerability.

## INPUT YOU WILL RECEIVE
- Original vulnerable code
- Patched code  
- Execution sandbox output (stdout + exit code)
- The fix plan that was followed

## YOUR EVALUATION CRITERIA
1. **Correctness** -- Does the patch actually fix the vulnerability without breaking logic?
2. **Completeness** -- Are ALL instances of the vulnerability addressed?
3. **No Regression** -- Did the patch introduce new bugs or vulnerabilities?
4. **Execution Proof** -- Does sandbox output confirm the fix works?

## OUTPUT FORMAT (strict JSON, nothing else)
{
  "verdict": "APPROVED" | "REJECTED",
  "confidence": 0.0-1.0,
  "reason": "one clear sentence explaining your decision",
  "remaining_issues": ["list any unresolved issues, or empty list if none"],
  "evpc_score": 1.0 | 0.5 | 0.0
}

## EVPC SCORING RULES
- 1.0 = patch is correct AND sandbox execution confirmed it
- 0.5 = patch is logically correct BUT sandbox was unavailable or inconclusive  
- 0.0 = patch is wrong, incomplete, or introduced new vulnerabilities

## STRICT RULES
- Output ONLY the JSON object. No markdown, no explanation outside JSON.
- Be decisive. Never output null for evpc_score.
- If sandbox shows a crash or error, that is strong evidence for REJECTED."""

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
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                parsed = json.loads(match.group())
                verdict = "APPROVED" if "APPROV" in str(parsed.get("verdict", "")).upper() else "REJECTED"
                return {
                    "verdict":          verdict,
                    "confidence":       float(parsed.get("confidence", 0.5)),
                    "reason":           str(parsed.get("reason", "")),
                    "remaining_issues": list(parsed.get("remaining_issues", [])),
                    "evpc_score":       float(parsed.get("evpc_score", 0.5)),
                    "feedback":         str(parsed.get("reason", "")) if verdict == "REJECTED" else "",
                }
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

        # Fallback if JSON parse fails
        verdict = "APPROVED" if e2b_exit_code == 0 else "REJECTED"
        return {
            "verdict":          verdict,
            "confidence":       0.3,
            "reason":           raw[:300] if raw else "No response from reviewer.",
            "remaining_issues": [],
            "evpc_score":       0.5,
            "feedback":         "" if verdict == "APPROVED" else (raw[:300] if raw else ""),
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
