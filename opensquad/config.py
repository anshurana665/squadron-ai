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
    # ── OpenRouter API ────────────────────────────────────────────
    OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
    OPENROUTER_API_KEY  = _require("OPENROUTER_API_KEY")

    # ── Model Routing (all 3 agents use Gemma 3 27B) ─────────────
    REASONING_MODEL = "google/gemma-3-27b-it"
    CODING_MODEL    = "google/gemma-3-27b-it"
    REVIEWER_MODEL  = "google/gemma-3-27b-it"

    # ── Model Hyperparameters ─────────────────────────────────────
    MANAGER_PARAMS   = {"temperature": 0.7,  "top_p": 0.95, "max_tokens": 16384}
    DEVELOPER_PARAMS = {"temperature": 0.15, "top_p": 0.95, "max_tokens": 16384}
    REVIEWER_PARAMS  = {"temperature": 0.5,  "top_p": 0.95, "max_tokens": 8192}

    # ── Other Keys ────────────────────────────────────────────────
    GROQ_API_KEY   = os.getenv("GROQ_API_KEY", "")
    GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY", "")
    E2B_API_KEY    = os.getenv("E2B_API_KEY", "")

    # ── Throttling ────────────────────────────────────────────────
    MIN_SECONDS_BETWEEN_CALLS = 1.0
    MAX_RETRIES               = 4

    @classmethod
    def validate(cls):
        """Ensure all required environment variables are present before starting."""
        pass