"""
Configuration for the scratch agent.
Max steps, model name placeholder, memory size, etc.
"""

import os

MAX_STEPS = 15
MEMORY_RECENT_K = 10
DECIDE_PARSE_RETRIES = 1
MODEL_ERROR_RETRIES = 2

# Ollama configuration (local or remote GPU)
# Defaults assume Ollama is listening on localhost:11434.
# Override via environment variables when running remotely, e.g.:
#   OLLAMA_BASE_URL=http://k2x-gpu-bb:11434
#   OLLAMA_MODEL=qwen2.5:7b
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

# Backwards-compat alias; not used directly elsewhere
MODEL_NAME = OLLAMA_MODEL
