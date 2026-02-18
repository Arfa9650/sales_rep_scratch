# Scratch Agent (First Principles)

A small agent built **from first principles**: no agent framework. Control flow, planning, tool use, memory, reflection, retries, and decisions are implemented explicitly so you can see how an LLM agent works internally.

## Purpose: Sales Rep Agent

The agent is a **sales rep** agent. Given:

- **Company name**
- **Industry**
- **Public website or short profile text**

it uses the agent loop (and optionally one real tool) to propose:

1. **Value hypothesis**
2. **Suggested messaging angle**
3. **Supporting evidence or assumptions**

No mock data: the only tool uses the LLM to extract insights from the profile you provide. All reasoning is over the given inputs (no web search).

## What This Implements

- **Explicit control loop**: Reason → Decide → Act → Observe → Update → Reflect
- **Model-driven tool use**: The model chooses when to call the single tool (no fixed sequence)
- **Memory**: Prior findings are stored and injected into context so later decisions use them
- **Reflection / self-critique**: A dedicated step evaluates assumptions, confidence, and whether to revise or stop
- **Local model**: Planning and reasoning run via a placeholder client; you plug in Ollama or LM Studio

## Flow

- **Inputs**: Company name, Industry, Public website or short profile text.
- **Process**: Agent loop (reason → decide → act → observe → update → reflect). The model can call the **extract_insights** tool to get structured insights from the profile, then reason and stop with a final answer.
- **Outputs**: A dict with **value_hypothesis**, **messaging_angle**, **supporting_evidence** (all strings).

## Tools

- **extract_insights** (single tool, no mock data): Uses the LLM to extract key facts, pain points, and opportunities from the provided company profile text. The model can call it to structure the profile before proposing value hypothesis and messaging. No web search; all reasoning is over the given inputs.

## Project Layout

| File | Purpose |
|------|--------|
| `local_llm.py` | Placeholder LLM client (`complete`, `complete_structured`). Replace with Ollama/LM Studio here. |
| `agent_loop.py` | Main loop; `run_agent(task, tool_registry=...)` and `run_sales_rep_flow(company_name, industry, profile_text)`. |
| `tools.py` | Tool registry: `get_tool_registry(profile_text)`. Single tool: `extract_insights`. |
| `memory.py` | `AgentMemory`: add, get_recent, get_summary. |
| `decisions.py` | Parse model output into `Decision` and reflection dict. |
| `config.py` | MAX_STEPS, retries, model name placeholder. |

## Run It

**Sales-rep flow** (recommended): from the project root:

```bash
python agent_loop.py
```

This runs `run_sales_rep_flow("Acme Corp", "Manufacturing", sample_profile)` and prints the structured result.

In code:

```python
from agent_loop import run_sales_rep_flow

result = run_sales_rep_flow("Acme Corp", "Manufacturing", "Company profile or website text here...")
print(result["value_hypothesis"])
print(result["messaging_angle"])
print(result["supporting_evidence"])
```

**Generic loop** (custom task):

```python
from agent_loop import run_agent
result = run_agent("Your custom task here.")
print(result)
```

With the **placeholder** LLM, the model always returns the same response, so the loop runs until `MAX_STEPS` and then returns a parsed dict (or "Max steps reached" placeholders). Once you connect a real local model, it can set `should_stop=True` and use the extract_insights tool.

## Connecting a Real Local Model (Ollama)

The only place the agent talks to an LLM is `local_llm.py`. The implementation there now uses **Ollama** via the `/api/generate` endpoint.

- **Config in `config.py`**  
  - `OLLAMA_BASE_URL`: base URL for Ollama (default `http://localhost:11434`).  
  - `OLLAMA_MODEL`: model name to use (default `qwen2.5:7b`; you can set `deepseek-r1:7b`, `deepseek-r1:32b`, `llama3:latest`, etc.).  
  - You can override both with environment variables:
    - `OLLAMA_BASE_URL=http://k2x-gpu-bb:11434`
    - `OLLAMA_MODEL=deepseek-r1:7b`

- **How the client calls Ollama**  
  - `complete(prompt, **kwargs)`:  
    - POST to `OLLAMA_BASE_URL + '/api/generate'` with body `{ \"model\": OLLAMA_MODEL, \"prompt\": prompt, \"stream\": false, \"options\": {...} }`.  
    - Returns `response["response"]` from the JSON response.  
  - `complete_structured(prompt, schema=None)`:  
    - Same endpoint with `\"format\": \"json\"` in the body so Ollama validates JSON.  
    - Expects a JSON object in `response`; attempts `json.loads` and returns a dict (or `{}` on failure).  
    - The Decide step then uses this dict as a structured hint, falling back to text parsing when empty.

- **Remote vs local usage**
  - **Run on GPU server (SSH session)**:  
    - On the server, start Ollama (as you already have).  
    - Run the agent there (`python agent_loop.py`) with `OLLAMA_BASE_URL=http://localhost:11434`.
  - **Run on Windows, Ollama on GPU server** (e.g. host `k2x-gpu-bb`):  
    - Option A: expose Ollama on the network (`OLLAMA_HOST=0.0.0.0` on the server) and set `OLLAMA_BASE_URL=http://k2x-gpu-bb:11434` on Windows.  
    - Option B: use SSH port forwarding:
      - `ssh -L 11434:localhost:11434 radio-analyzer@k2x-gpu-bb`  
      - Then keep `OLLAMA_BASE_URL=http://localhost:11434` on Windows.

No other files need to know about Ollama directly; everything goes through `local_llm.complete` / `complete_structured`.

## What You See in Logs

- **Reasoning**: Output of the Reason step each iteration.
- **Decision**: `next_action`, `tool_id`, `should_stop`, `should_revise`, `confidence`, and short reason.
- **Tool chosen**: Which tool ran and why (from the decision reason).
- **Observation**: Tool result or error.
- **Reflection**: Self-critique and parsed `confidence` / `should_revise`.

So you can see why actions were taken, why tools were chosen, and how confidence/reflection affect the loop.

## Configuration

Edit `config.py` to change:

- `MAX_STEPS` – cap on loop iterations  
- `MEMORY_RECENT_K` – how many recent memory items to consider  
- `DECIDE_PARSE_RETRIES` – retries when parsing the decision fails  
- `MODEL_ERROR_RETRIES` – retries when the local LLM call fails  
- `OLLAMA_BASE_URL` – where the Ollama server is listening  
- `OLLAMA_MODEL` – which Ollama model to use (e.g. `qwen2.5:7b`, `deepseek-r1:7b`, `deepseek-r1:32b`, `llama3:latest`)

## Dependencies

Standard library only. When you add Ollama/LM Studio in `local_llm.py`, you may need `requests` (or use `urllib.request`) for HTTP.
