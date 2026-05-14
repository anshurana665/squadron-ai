class OpenSquadError(Exception):
    """Base exception for all OpenSquad errors."""
    pass

class LLMConnectionError(OpenSquadError):
    """Raised when Ollama is unreachable (Network/URL issues)."""
    pass

class LLMGenerationError(OpenSquadError):
    """Raised when Ollama returns an error or invalid JSON."""
    pass

class MemoryError(OpenSquadError):
    """Raised when ChromaDB fails to store or recall data."""
    pass

class ConfigurationError(OpenSquadError):
    """Raised when config values are missing or invalid."""
    pass

# Alias for catching any LLM-related issue
LLMError = (LLMConnectionError, LLMGenerationError)