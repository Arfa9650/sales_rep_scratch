---
name: Remote Ollama integration
overview: Replace the placeholder LLM in local_llm.py with real Ollama API calls (configurable base URL for remote GPU), add config for model and URL, and update the README with remote setup, tools, and agent behavior.
todos: []
isProject: false
---

# Use Remote Ollama as the Scratch Agent LLM

## Goal

- Switch from the placeholder in [local_llm.py](local_llm.py) to **Ollama** so the agent uses your GPU server models.
- Support **remote** usage: agent can run on your Windows machine and talk to Ollama on the SSH host (e.g. `k2x-gpu-bb`), or run on the GPU server with `localhost`.
- Update the README with configuration, tool behavior, and agent flow.

---

## 1. Config: base URL and model

**File**: [config.py](config.py)

- Add **OLLAMA_BASE_URL** (default `http://localhost:11434`). When running the agent from Windows against the GPU server, set this to `http://<hostname>:11434` (e.g. `http://k2x-gpu-bb:11434`) or use SSH port forwarding and keep `localhost`.
- Add **OLLAMA_MODEL** (default `qwen2.5:7b`). Allow override so you can use `deepseek-r1:7b`, `deepseek-r1:32b`, or `llama3:latest` without code changes.
- Keep existing `MAX_STEPS`, `MODEL_ERROR_RETRIES`, etc. Remove or repurpose the generic `MODEL_NAME` in favor of `OLLAMA_MODEL` if it’s only used for display.

No changes to [agent_loop.py](agent_loop.py); it keeps calling `complete` and `complete_structured` only.

---

## 2. Implement Ollama in local_llm.py

**File**: [local_llm.py](local_llm.py)

- **Dependency**: Use `urllib.request` (no new dependency) or add `requests` for HTTP. Prefer `urllib.request` to keep “standard library only” unless you prefer `requests` for clarity.
- **complete(prompt, **kwargs)**  
  - POST to `{OLLAMA_BASE_URL}/api/generate`.  
  - Body: `{"model": OLLAMA_MODEL, "prompt": prompt, "stream": false}`.  
  - Optional: pass through `options` (e.g. `temperature`) from kwargs if needed.  
  - On 200, return `response["response"]`; on error, raise with status/body so [agent_loop.py](agent_loop.py) retries (already in place).
- **complete_structured(prompt, schema)**  
  - Same endpoint with `**"format": "json"**` in the body so Ollama returns valid JSON.  
  - In the prompt, ask for a single JSON object with: `next_action`, `tool_id`, `tool_input`, `confidence`, `should_stop`, `should_revise`, `reasoning`.  
  - Parse the response text as JSON; if parsing fails, fall back to `parse_decision(response_text, structured_fallback=None)` so [decisions.py](decisions.py) can still extract fields from plain text.  
  - Return the parsed dict in the shape [decisions.py](decisions.py) expects (see `_decision_from_dict`).

Read `OLLAMA_BASE_URL` and `OLLAMA_MODEL` from [config.py](config.py) (or from `os.environ` with config as fallback) so the same code works locally and remotely.

---

## 3. Remote vs local usage

- **Run on GPU server (SSH session)**: Set `OLLAMA_BASE_URL=http://localhost:11434` (or leave default). Run `python agent_loop.py` there; Ollama is on the same machine.
- **Run on Windows, Ollama on GPU server**: Either  
  - set `OLLAMA_BASE_URL=http://k2x-gpu-bb:11434` (or the host’s IP) and ensure Ollama is listening on 0.0.0.0 (e.g. `OLLAMA_HOST=0.0.0.0` on the server), or  
  - use SSH port forward: `ssh -L 11434:localhost:11434 radio-analyzer@k2x-gpu-bb` and keep `OLLAMA_BASE_URL=http://localhost:11434` on Windows.

Document both options in the README.

---

## 4. README updates

**File**: [README.md](README.md) (project root). If [documentation/README.md](documentation/README.md) exists, apply the same content there or link from it.

- **Tools**: Short section describing the two tools:
  - **search**: Mock company search by keyword (no internet); returns in-memory results. Mention that replacing with a real search API is a one-function change in [tools.py](tools.py).
  - **get_contact**: Mock contact lookup by company key (e.g. `acme`, `techstart`).
- **Agent / LLM**: Replace “placeholder” wording with:
  - Agent uses **Ollama** via [local_llm.py](local_llm.py); config in [config.py](config.py): `OLLAMA_BASE_URL`, `OLLAMA_MODEL`.
  - Available models (from your `ollama list`): `deepseek-r1:7b`, `qwen2.5:7b`, `deepseek-r1:32b`, `llama3:latest`.
  - How to run **on the GPU server** vs **from Windows** (localhost vs remote URL or SSH tunnel), as in section 3 above.
- **Configuration**: Extend the config table/section with `OLLAMA_BASE_URL` and `OLLAMA_MODEL`.
- **Dependencies**: If you use only `urllib`, state “standard library only.” If you add `requests`, add a one-line `pip install` or `requirements.txt` mention.

No code changes to [tools.py](tools.py) or [agent_loop.py](agent_loop.py) beyond what’s already there; only [local_llm.py](local_llm.py) and [config.py](config.py) change, plus README.

---

## 5. Optional: requirements.txt

If you introduce `requests`, add [requirements.txt](requirements.txt) with `requests>=2.28.0` (or similar). If you stick to `urllib.request`, omit or leave a minimal file for future use.

---

## Summary


| Item             | Action                                                                                                                |
| ---------------- | --------------------------------------------------------------------------------------------------------------------- |
| config.py        | Add OLLAMA_BASE_URL, OLLAMA_MODEL; use for LLM client.                                                                |
| local_llm.py     | Implement complete() and complete_structured() via Ollama /api/generate (stream: false; format: json for structured). |
| README           | Document tools (search, get_contact), Ollama config, remote vs local run, and config options.                         |
| requirements.txt | Add only if using requests.                                                                                           |


After this, running `python agent_loop.py` (on the GPU host or from Windows with URL/tunnel set) will use your chosen Ollama model for reasoning, decisions, and reflection.