import os
from dotenv import load_dotenv

load_dotenv()

def _require(key: str) -> str:
    """Get env var. Falls back to NVIDIA_API_KEY for agent keys. Raises clearly if missing."""
    val = os.getenv(key)
    if val:
        return val
    # If per-agent key missing, fall back to shared NVIDIA_API_KEY
    if key.startswith("NVIDIA_KEY_"):
        shared = os.getenv("NVIDIA_API_KEY")
        if shared:
            return shared
    raise KeyError(
        f"\n❌ Missing environment variable: '{key}'\n"
        f"   Add it to your .env file and restart.\n"
    )

class Config:
    NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"

    # Uses per-agent key if set, falls back to NVIDIA_API_KEY
    NVIDIA_KEY_MANAGER   = _require("NVIDIA_KEY_MANAGER")
    NVIDIA_KEY_DEVELOPER = _require("NVIDIA_KEY_DEVELOPER")
    NVIDIA_KEY_REVIEWER  = _require("NVIDIA_KEY_REVIEWER")

    # ── Model Routing ───────────────────────────────────────────
    REASONING_MODEL = "nvidia/llama-3.3-nemotron-super-49b-v1.5"
    CODING_MODEL    = "deepseek-ai/deepseek-v3.1"
    REVIEWER_MODEL  = "llama-3.3-70b-versatile"
    REVIEWER_PROVIDER = "groq"

    # ── Model Hyperparameters ──────────────────────────────────
    MANAGER_PARAMS   = {"temperature": 0.6,  "top_p": 0.95, "max_tokens": 8192}
    DEVELOPER_PARAMS = {"temperature": 0.15, "top_p": 0.95, "max_tokens": 8192}
    REVIEWER_PARAMS  = {"temperature": 0.6,  "top_p": 0.7,  "max_tokens": 4096}

    # ── Other Keys ──────────────────────────────────────────────
    GROQ_API_KEY   = os.getenv("GROQ_API_KEY", "")
    GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY", "")
    E2B_API_KEY    = os.getenv("E2B_API_KEY", "")

    # ── Throttling ──────────────────────────────────────────────
    MIN_SECONDS_BETWEEN_CALLS = 3.0
    MAX_RETRIES               = 6

    @classmethod
    def validate(cls):
        """Ensure all required environment variables are present before starting."""
        # Validation is now implicitly handled by _require() at module load
        # But we keep the method for consistency with entry points
        pass