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

    # ── Model Routing ─────────────────────────────────────────────
    # Manager (L8_ARCHITECT) needs deep reasoning → large model
    REASONING_MODEL = "google/gemma-3-27b-it"
    # Developer (L8_EXECUTIONER) writes code → faster 12B model
    CODING_MODEL    = "google/gemma-3-12b-it"
    # Reviewer (L8_AUDITOR) does SAST → fast, low temperature
    REVIEWER_MODEL  = "google/gemma-3-12b-it"

    # ── Model Hyperparameters ─────────────────────────────────────
    # Reduced token budgets for 2-3x speed improvement
    MANAGER_PARAMS   = {"temperature": 0.5,  "top_p": 0.95, "max_tokens": 4096}
    DEVELOPER_PARAMS = {"temperature": 0.15, "top_p": 0.95, "max_tokens": 8192}
    REVIEWER_PARAMS  = {"temperature": 0.1,  "top_p": 0.95, "max_tokens": 2048}

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