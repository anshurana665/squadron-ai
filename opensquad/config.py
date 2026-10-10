import os
from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    """Get env var. Raises clearly if missing."""
    val = os.getenv(key)
    if val:
        return val
    raise KeyError(
        f"\n❌ Missing environment variable: '{key}'\n"
        f"   Add it to your .env file and restart.\n"
    )


class Config:
    # ── AgentRouter / OpenRouter API ──────────────────────────────
    OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    OPENROUTER_API_KEY  = os.getenv("OPENROUTER_API_KEY", "")

    # ── Model Routing ─────────────────────────────────────────────
    # Manager (L8_ARCHITECT)
    REASONING_MODEL = os.getenv("REASONING_MODEL", "moonshotai/kimi-k3")
    # Developer (L8_EXECUTIONER)
    CODING_MODEL    = os.getenv("CODING_MODEL", "moonshotai/kimi-k3")
    # Reviewer (L8_AUDITOR)
    REVIEWER_MODEL  = os.getenv("REVIEWER_MODEL", "moonshotai/kimi-k3")

    # ── Model Hyperparameters ─────────────────────────────────────
    MANAGER_PARAMS   = {"temperature": 0.2, "max_tokens": 4096}
    DEVELOPER_PARAMS = {"temperature": 0.1, "max_tokens": 4096}
    REVIEWER_PARAMS  = {"temperature": 0.1, "max_tokens": 2048}

    # ── Other Keys ────────────────────────────────────────────────
    GROQ_API_KEY   = os.getenv("GROQ_API_KEY", "")
    GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY", "")
    E2B_API_KEY    = os.getenv("E2B_API_KEY", "")

    # ── Throttling ────────────────────────────────────────────────
    MIN_SECONDS_BETWEEN_CALLS = 1.0
    MAX_RETRIES               = 4

    @classmethod
    def validate(cls):
        """Ensure critical environment variables are present when running live calls."""
        if not cls.OPENROUTER_API_KEY and not cls.GROQ_API_KEY and not cls.GEMINI_API_KEY:
            raise KeyError(
                "❌ No valid LLM API key detected in environment. "
                "Please configure OPENROUTER_API_KEY, GROQ_API_KEY, or GOOGLE_API_KEY in .env"
            )