"""
opensquad/core/llm.py

3 dedicated OpenAI-compatible NVIDIA NIM clients:
  - ManagerLLM   → nemotron-super-49b   (reasoning ON, agentic)
  - DeveloperLLM → deepseek-v3.1        (fast code generation)
  - ReviewerLLM  → deepseek-r1-qwen-32b (critical QA)

ROOT FIX: Non-streaming mode by default. Streaming is only used for
Manager's thinking tokens, with automatic non-streaming fallback.
"""

import re
import time
import logging
import httpx

logger = logging.getLogger("opensquad.llm")
from openai import OpenAI, RateLimitError, AuthenticationError, APIError
from opensquad.config import Config


# ═══════════════════════════════════════════════════════════════════════
# BASE CLIENT — Shared retry + throttle logic
# ═══════════════════════════════════════════════════════════════════════

class _BaseNvidiaClient:
    """
    Base class with:
      - Proactive throttling (MIN_SECONDS_BETWEEN_CALLS)
      - Exponential backoff on 429 RateLimitError
      - NON-STREAMING by default (reliable single request/response)
      - Streaming ONLY for thinking-token extraction (Manager)
    """
    _last_call_time: float = 0.0   # shared across all instances

    # All network exceptions we should retry on
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
        self.model  = model
        self.params = params

    @staticmethod
    def _make_client(api_key: str) -> OpenAI:
        """Create a fresh OpenAI client (new httpx transport)."""
        return OpenAI(
            base_url=Config.NVIDIA_BASE_URL,
            api_key=api_key,
            timeout=300.0,  # 5 minutes
        )

    # ── Throttle ────────────────────────────────────────────────────
    def _throttle(self):
        elapsed = time.time() - _BaseNvidiaClient._last_call_time
        wait    = Config.MIN_SECONDS_BETWEEN_CALLS - elapsed
        if wait > 0:
            time.sleep(wait)
        _BaseNvidiaClient._last_call_time = time.time()

    # ── NON-STREAMING generate (reliable, default) ──────────────────
    def generate(
        self,
        prompt:      str,
        system:      str  = "",
        return_thinking: bool = False,
    ) -> str | tuple[str, str]:
        """
        NON-STREAMING generate — single request/response.
        Much more reliable than streaming on NVIDIA free tier.

        Args:
            prompt          : User message
            system          : System prompt (optional)
            return_thinking : If True, try streaming for thinking tokens,
                              fallback to non-streaming if it fails.

        Returns:
            str   — just the answer (default)
            tuple — (thinking, answer) when return_thinking=True
        """
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        # If we need thinking tokens, try streaming first (with fallback)
        if return_thinking:
            result = self._generate_streaming(messages)
            if result is not None:
                return result
            # Streaming failed — fallback to non-streaming
            logger.info("💡 Switching to non-streaming mode for reliability...")

        # Non-streaming call (default path — much more reliable)
        return self._generate_non_streaming(messages, return_thinking)

    # ── Non-streaming implementation ─────────────────────────────────
    def _generate_non_streaming(
        self,
        messages: list[dict],
        return_thinking: bool = False,
    ) -> str | tuple[str, str]:
        """
        Single request/response — no long-lived TCP connection.
        This is the ROOT FIX for RemoteProtocolError.
        """
        # Strip streaming-incompatible params
        params = {k: v for k, v in self.params.items()}

        for attempt in range(Config.MAX_RETRIES + 1):
            try:
                self._throttle()

                response = self.client.chat.completions.create(
                    model    = self.model,
                    messages = messages,
                    stream   = False,
                    **params,
                )

                answer = response.choices[0].message.content or ""

                # Try to extract reasoning from non-streaming response
                thinking = ""
                if return_thinking:
                    msg = response.choices[0].message
                    thinking = getattr(msg, "reasoning_content", "") or ""

                if return_thinking:
                    return thinking, answer
                return answer

            except RateLimitError:
                wait = min(2 ** attempt, 30)
                if attempt < Config.MAX_RETRIES:
                    logger.warning(
                        f"⚠️ NVIDIA rate limit hit — retrying in {wait}s "
                        f"(attempt {attempt + 1}/{Config.MAX_RETRIES})"
                    )
                    time.sleep(wait)
                else:
                    raise

            except AuthenticationError:
                raise RuntimeError(
                    f"❌ NVIDIA API key invalid for model `{self.model}`. "
                    "Check your .env file."
                )

            except APIError as e:
                wait = min(2 ** attempt, 30)
                if attempt < Config.MAX_RETRIES:
                    logger.warning(
                        f"⚠️ NVIDIA API error — retrying in {wait}s "
                        f"(attempt {attempt + 1}/{Config.MAX_RETRIES})"
                    )
                    time.sleep(wait)
                else:
                    raise RuntimeError(f"NVIDIA API error: {e}") from e

            except self._NETWORK_ERRORS as e:
                wait = min(2 ** attempt, 30)
                if attempt < Config.MAX_RETRIES:
                    # Recreate client to get a fresh TCP connection
                    self.client = self._make_client(self.api_key)
                    logger.warning(
                        f"⚠️ NVIDIA connection issue ({type(e).__name__}) — "
                        f"retrying in {wait}s (attempt {attempt + 1}/{Config.MAX_RETRIES})"
                    )
                    time.sleep(wait)
                else:
                    raise RuntimeError(
                        f"NVIDIA API network failure after {Config.MAX_RETRIES} retries: "
                        f"{type(e).__name__}: {e}"
                    ) from e

            except Exception as e:
                # Catch-all for any unexpected errors
                wait = min(2 ** attempt, 30)
                if attempt < Config.MAX_RETRIES:
                    self.client = self._make_client(self.api_key)
                    logger.warning(
                        f"⚠️ Unexpected error ({type(e).__name__}) — "
                        f"retrying in {wait}s (attempt {attempt + 1}/{Config.MAX_RETRIES})"
                    )
                    time.sleep(wait)
                else:
                    raise RuntimeError(
                        f"NVIDIA API failure after {Config.MAX_RETRIES} retries: {e}"
                    ) from e

        # Should never reach here, but safety net
        if return_thinking:
            return "", ""
        return ""

    # ── Streaming implementation (Manager only, for thinking tokens) ──
    def _generate_streaming(self, messages: list[dict]) -> tuple[str, str] | None:
        """
        Streaming mode — ONLY used for Manager's thinking token extraction.
        Returns (thinking, answer) or None if streaming fails.
        
        This method tries ONCE with streaming. If it fails, returns None
        so the caller can fallback to non-streaming.
        """
        try:
            self._throttle()

            stream = self.client.chat.completions.create(
                model    = self.model,
                messages = messages,
                stream   = True,
                **self.params,
            )

            thinking_buf = []
            answer_buf   = []

            for chunk in stream:
                if not getattr(chunk, "choices", None):
                    continue
                delta = chunk.choices[0].delta

                # Capture reasoning / thinking tokens
                reasoning = getattr(delta, "reasoning_content", None)
                if reasoning:
                    thinking_buf.append(reasoning)

                # Capture normal answer tokens
                if delta.content:
                    answer_buf.append(delta.content)

            thinking = "".join(thinking_buf)
            answer   = "".join(answer_buf)
            return thinking, answer

        except Exception as e:
            # Streaming failed — rebuild client and let caller fallback
            logger.warning(
                f"⚠️ Streaming failed ({type(e).__name__}) — falling back to standard mode..."
            )
            self.client = self._make_client(self.api_key)
            return None


# ═══════════════════════════════════════════════════════════════════════
# 3 DEDICATED AGENT CLIENTS
# ═══════════════════════════════════════════════════════════════════════

class ManagerLLM(_BaseNvidiaClient):
    """
    nvidia/llama-3.3-nemotron-super-49b-v1.5
    49B MoE | Reasoning ON | For: vulnerability analysis + JSON planning
    """
    def __init__(self):
        super().__init__(
            api_key = Config.NVIDIA_KEY_MANAGER,
            model   = Config.REASONING_MODEL,
            params  = Config.MANAGER_PARAMS,
        )

    def plan(self, file_content: str, issue: str, security_mode: bool) -> tuple[str, str]:
        """
        Returns (thinking_text, json_plan_string)
        """
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

        return self.generate(prompt, system=system, return_thinking=True)


class DeveloperLLM(_BaseNvidiaClient):
    """
    deepseek-ai/deepseek-v3.1
    Fast & stable | Low temp (0.15) | For: secure patch generation
    Uses NON-STREAMING mode for reliability.
    """
    def __init__(self):
        super().__init__(
            api_key = Config.NVIDIA_KEY_DEVELOPER,
            model   = Config.CODING_MODEL,
            params  = Config.DEVELOPER_PARAMS,
        )

    def patch(self, file_content: str, plan: list[str], error_feedback: str = "") -> str:
        """
        Returns patched code string (no markdown fences).
        """
        plan_text = "\n".join(f"  {i+1}. {step}" for i, step in enumerate(plan))

        retry_note = (
            f"\n\nPREVIOUS PATCH FAILED WITH THIS ERROR — FIX IT:\n{error_feedback}"
            if error_feedback else ""
        )

        system = """You are the Developer Agent of OpenSquad. You write production-grade, secure code.

ENTERPRISE RULESET — NEVER VIOLATE:
1. NEVER use blanket `except Exception: pass` — handle specific exceptions only.
2. NEVER build SQL queries with string concatenation — always use parameterized queries (? or %s).
3. NEVER hardcode secrets, API keys, or passwords.
4. NEVER use eval() or exec() on user input.
5. ALWAYS validate and sanitize user inputs before use.
6. Output ONLY the complete fixed code. No explanation. No markdown fences. No comments like "# Fixed".
7. Follow the Manager's plan EXACTLY — do not skip any step."""

        prompt = f"""REPAIR PLAN FROM MANAGER:
{plan_text}
{retry_note}

ORIGINAL CODE TO FIX:
{file_content}

Output the complete patched file now:"""

        return self.generate(prompt, system=system)


class ReviewerLLM:
    """
    llama-3.3-70b-versatile via Groq
    Fast, reliable reviewer — no NVIDIA timeout issues.
    """
    def __init__(self):
        from groq import Groq
        self.client = Groq(api_key=Config.GROQ_API_KEY)
        self.model  = Config.REVIEWER_MODEL  # "llama-3.3-70b-versatile"
        self.params = Config.REVIEWER_PARAMS

    def generate(self, prompt: str, system: str = "") -> str:
        """Simple non-streaming generate via Groq."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        for attempt in range(Config.MAX_RETRIES + 1):
            try:
                response = self.client.chat.completions.create(
                    model    = self.model,
                    messages = messages,
                    temperature = self.params.get("temperature", 0.6),
                    top_p       = self.params.get("top_p", 0.7),
                    max_tokens  = self.params.get("max_tokens", 4096),
                )
                return response.choices[0].message.content or ""
            except Exception as e:
                wait = min(2 ** attempt, 30)
                if attempt < Config.MAX_RETRIES:
                    logger.warning(
                        f"⚠️ Groq reviewer error ({type(e).__name__}) — "
                        f"retrying in {wait}s (attempt {attempt + 1}/{Config.MAX_RETRIES})"
                    )
                    time.sleep(wait)
                else:
                    raise RuntimeError(
                        f"Groq reviewer failure after {Config.MAX_RETRIES} retries: {e}"
                    ) from e
        return ""

    def review(
        self,
        original_code:  str,
        patched_code:   str,
        e2b_stdout:     str,
        e2b_exit_code:  int,
        plan:           list[str],
    ) -> dict:
        """
        Returns:
        {
            "verdict":          "APPROVED" | "REJECTED",
            "confidence":       float (0.0–1.0),
            "reason":           str,
            "remaining_issues": list[str],
            "evpc_score":       float (1.0 | 0.5 | 0.0),
            "feedback":         str,
        }
        """
        system = """You are a senior security code reviewer in an autonomous patching pipeline.

Your job is to evaluate whether a patch correctly fixes the reported vulnerability.

## INPUT YOU WILL RECEIVE
- Original vulnerable code
- Patched code  
- Execution sandbox output (stdout + exit code)
- The fix plan that was followed

## YOUR EVALUATION CRITERIA
1. **Correctness** — Does the patch actually fix the vulnerability without breaking logic?
2. **Completeness** — Are ALL instances of the vulnerability addressed?
3. **No Regression** — Did the patch introduce new bugs or vulnerabilities?
4. **Execution Proof** — Does sandbox output confirm the fix works?

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

        raw = self.generate(prompt, system=system)

        # Parse strict JSON response
        import re, json
        try:
            # Extract JSON object from response (handles any stray text)
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                parsed = json.loads(match.group())
                # Normalize verdict
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
    """
    Single entry point — app.py and agents import this.
    Usage:
        llm = LLMProvider()
        answer = llm.generate(prompt, model="coding")
    """
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
        """Generic fallback — routes by role name."""
        router = {
            "reasoning": self.manager(),
            "coding":    self.developer(),
            "reviewing": self.reviewer(),
        }
        client = router.get(model, self.developer())
        return client.generate(prompt)
