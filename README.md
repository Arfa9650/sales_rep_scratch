# Scratch Agent (First Principles)

A small agent built **from first principles**: no agent framework. Control flow, planning, tool use, memory, reflection, retries, and decisions are implemented explicitly so you can see how an LLM agent works internally.

## Purpose: Sales Rep Assistant

The agent is a **sales rep assistant**. You give it:

- **Who you represent**: Your company description (who you are selling for).
- **Prospect**: The company you are exploring or contacting — company name, industry, and public website or short profile text.

It uses the agent loop and tools to propose:

1. **Value hypothesis**
2. **Suggested messaging angle**
3. **Supporting evidence or assumptions**

The model can search the web (DuckDuckGo), extract insights from the prospect profile, and save key facts for the next step to reduce hallucination.

## What This Implements

- **Explicit control loop**: Reason → Decide → Act → Observe → Update → Reflect
- **Model-driven tool use**: The model chooses when to call tools (no fixed sequence)
- **Memory**: Prior findings and **saved notes** are stored and injected into context so later decisions use them
- **Reflection / self-critique**: A dedicated step evaluates assumptions, confidence, and whether to revise or stop
- **Stop rules**: Stops only when confidence ≥ `MIN_CONFIDENCE_TO_STOP`; rejects stop when the model says "insufficient information" but did not use a tool
- **Local model**: Reasoning runs via Ollama (configurable in `config.py` and `local_llm.py`)

## Flow

- **Inputs**: `my_company_description`, `prospect_company_name`, `prospect_industry`, `prospect_profile_text`.
- **Process**: Agent loop. The model can call **search_web** (DuckDuckGo) for company/industry info, **extract_insights** on the prospect profile, and **save_note** to persist key facts for the next step. It iterates until confident or `MAX_STEPS`.
- **Outputs**: A dict with **value_hypothesis**, **messaging_angle**, **supporting_evidence** (all strings). Run logs are written to **logs/run_YYYYMMDD_HHMMSS.txt**.

## Tools

| Tool | Purpose |
|------|--------|
| **extract_insights** | Uses the LLM to extract key facts, pain points, and opportunities from the prospect profile. Params: optional `profile_text` (in sales-rep flow the profile is in scope). |
| **search_web** | Searches the web via DuckDuckGo (free, no API key). Params: `query` (required), optional `max_results` (default 5). Use for company info, industry trends, or supporting evidence not in the profile. |
| **save_note** | Saves a fact or finding for the next step. Params: `content` (string to save). Saved notes appear in "Memory (prior findings)" on subsequent steps so the model does not re-invent or hallucinate. |

## Project Layout

| File | Purpose |
|------|--------|
| `local_llm.py` | Ollama client: `complete`, `complete_structured`. |
| `agent_loop.py` | Main loop: `run_agent(task, ...)` and `run_sales_rep_flow(my_company_description, prospect_company_name, prospect_industry, prospect_profile_text)`. Task template and log file handler. |
| `tools.py` | Tool registry: `get_tool_registry(profile_text, memory)`. Tools: `extract_insights`, `search_web`, `save_note`. |
| `memory.py` | `AgentMemory`: `add`, `add_saved_note`, `get_recent`, `get_summary`. |
| `decisions.py` | Parse model output into `Decision` and reflection dict. |
| `config.py` | `MAX_STEPS`, `MIN_CONFIDENCE_TO_STOP`, retries, Ollama URL/model. |

## Run It

**Sales-rep flow** (recommended): from the project root:

```bash
python agent_loop.py
```

This runs `run_sales_rep_flow(my_company, prospect_name, prospect_industry, prospect_profile)` and prints the structured result. Logs are written to **logs/**.

In code:

```python
from agent_loop import run_sales_rep_flow

result = run_sales_rep_flow(
    my_company_description="Acme Solutions: we provide enterprise software for mid-market firms.",
    prospect_company_name="K2X Technologies",
    prospect_industry="Software Solutions",
    prospect_profile_text="k2x.tech",
)
print(result["value_hypothesis"])
print(result["messaging_angle"])
print(result["supporting_evidence"])
```

**Generic loop** (custom task, no save_note):

```python
from agent_loop import run_agent
result = run_agent("Your custom task here.", profile_text="optional for extract_insights")
print(result)
```

## Connecting Ollama

The agent talks to the LLM only in `local_llm.py`, which uses Ollama's `/api/generate` endpoint.

- **Config in `config.py`**
  - `OLLAMA_BASE_URL`: default `http://localhost:11434`
  - `OLLAMA_MODEL`: default `deepseek-r1:8b` (or `qwen3:8b`, `llama3:latest`, etc.)
  - Override with env: `OLLAMA_BASE_URL`, `OLLAMA_MODEL`

- **Calls**
  - `complete(prompt)`: POST to `/api/generate`, returns `response["response"]`
  - `complete_structured(prompt)`: same with `format: "json"`, returns parsed dict

- **Remote**: Set `OLLAMA_BASE_URL` to the server, or use SSH port forwarding (e.g. `ssh -L 11434:localhost:11434 user@host`).

## What You See in Logs

- **Reasoning**: Output of the Reason step each iteration
- **Decision**: `next_action`, `tool_id`, `should_stop`, `should_revise`, `confidence`, reasoning
- **Tool chosen**: Which tool ran and a short result
- **Observation**: Tool result or error
- **Reflection**: Self-critique and parsed confidence / should_revise
- **Rejecting stop**: When confidence is too low or the model said "insufficient" but did not use a tool

Run logs are also written to **logs/run_YYYYMMDD_HHMMSS.txt**.

## Configuration

In `config.py`:

- `MAX_STEPS` – cap on loop iterations (default 15)
- `MIN_CONFIDENCE_TO_STOP` – only stop when confidence ≥ this (default 0.6)
- `MEMORY_RECENT_K` – how many recent memory items to consider
- `DECIDE_PARSE_RETRIES`, `MODEL_ERROR_RETRIES`
- `OLLAMA_BASE_URL`, `OLLAMA_MODEL`

## Dependencies

- **ddgs** – DuckDuckGo search for the `search_web` tool. Install: `pip install ddgs` (or `pip install -r requirements.txt`).

Standard library is used for HTTP (Ollama) via `urllib.request` in `local_llm.py`.
