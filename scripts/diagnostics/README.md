# Squadron.AI Diagnostic & Smoke-Test Utilities

This directory contains standalone diagnostic scripts for checking model routing, inspecting live LLM API responses, and smoke-testing agent orchestration.

> [!NOTE]
> These scripts perform live API requests and are not executed during automated CI unit test runs.

## Tools

- **`check_model_routing.py`**: Validates whether the configured LLM provider accepts requests and routes between coding and reasoning models.
- **`debug_agent.py`**: Isolates direct OpenAI-compatible endpoint calls with microsecond latency logging.
- **`test_each_agent.py`**: Step-by-step diagnostic evaluating Manager, Developer, and Reviewer isolated nodes.
- **`smoke_test_pipeline.py`**: Verifies full graph streaming across Manager -> Red-Team -> Developer -> Reviewer nodes on a minimal SQL injection snippet.
