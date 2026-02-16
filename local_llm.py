"""
Placeholder local LLM client for the scratch agent.
All planning, reasoning, and tool-selection decisions happen through this interface.
Replace the placeholder implementation with Ollama or LM Studio when ready.
"""

from typing import Any, Optional

# TODO: connect to Ollama / LM Studio
# - Ollama: typically http://localhost:11434/api/generate
# - LM Studio: typically http://localhost:1234/v1/completions or /v1/chat/completions
# Keep this interface unchanged so agent_loop.py does not need to change.


def complete(prompt: str, **kwargs: Any) -> str:
    """
    Send a prompt to the local LLM and return the raw text response.
    This is the single call site for reasoning, decision, and reflection.
    """
    # Placeholder: return fixed string so the rest of the agent runs without a real model.
    # When connecting Ollama/LM Studio:
    # - Build request body (prompt, max_tokens, temperature, etc.)
    # - POST to local endpoint (e.g. requests.post(url, json=body))
    # - Parse response and return content (e.g. response["response"] or response["choices"][0]["text"])
    _ = prompt, kwargs  # use so linters are happy
    return "PLACEHOLDER_RESPONSE"


def complete_structured(prompt: str, schema: Optional[dict] = None) -> dict:
    """
    Optional: request a structured response (e.g. for decision or reflection).
    Placeholder returns a minimal dict that matches typical decision/reflection shape.
    """
    # Placeholder: return minimal struct so decision parsing and reflection logic can run.
    # When connecting Ollama/LM Studio: either ask for JSON in the prompt and parse,
    # or use a tool-calling/structured output API if the local server supports it.
    _ = prompt, schema
    return {
        "next_action": "continue",
        "tool_id": "",
        "tool_input": {},
        "confidence": 0.5,
        "should_stop": False,
        "should_revise": False,
        "reasoning": "PLACEHOLDER_RESPONSE",
    }
