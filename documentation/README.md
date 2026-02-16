# Scratch Agent (First Principles)

A small agent built **from first principles**: no agent framework. Control flow, planning, tool use, memory, reflection, retries, and decisions are implemented explicitly so you can see how an LLM agent works internally.

## What This Implements

- **Explicit control loop**: Reason → Decide → Act → Observe → Update → Reflect
- **Model-driven tool use**: The model chooses when and which tool to call (no fixed sequence)
- **Memory**: Prior findings are stored and injected into context so later decisions use them
- **Reflection / self-critique**: A dedicated step evaluates assumptions, confidence, and whether to revise or stop
- **Local model**: Planning and reasoning run via a placeholder client; you plug in Ollama or LM Studio

## Project Layout

| File | Purpose |
|------|--------|
| `local_llm.py` | Placeholder LLM client (`complete`, `complete_structured`). Replace with Ollama/LM Studio here. |
| `agent_loop.py` | Main loop: context build, Reason, Decide, Act, Observe, Update, Reflect, plus logging. |
| `tools.py` | Tool registry and implementations (`search`, `get_contact`). |
| `memory.py` | `AgentMemory`: add, get_recent, get_summary. |
| `decisions.py` | Parse model output into `Decision` and reflection dict. |
| `config.py` | MAX_STEPS, retries, model name placeholder. |

## Run It

From the project root:

```bash
python agent_loop.py
```

Or in code:

```python
from agent_loop import run_agent
result = run_agent("Find contact info for Acme Corp.")
print(result)
```

With the **placeholder** LLM, the model always returns the same response, so the loop runs until `MAX_STEPS` and then returns "Max steps reached; no final answer yet." Once you connect a real local model, it can set `should_stop=True` and use tools.

## Connecting a Real Local Model

The only place the agent talks to an LLM is `local_llm.py`. Keep the same interface and swap the implementation.

1. **Ollama**  
   - Endpoint: `http://localhost:11434/api/generate` (or `/api/chat`).  
   - In `complete()`: build a JSON body with `prompt`, `model`, `stream: false`, etc.; POST and return the generated text.  
   - For `complete_structured()`: either ask for JSON in the prompt and parse it, or call the same endpoint and parse the reply.

2. **LM Studio**  
   - Often `http://localhost:1234/v1/completions` or `/v1/chat/completions`.  
   - Same idea: build the request, POST, parse the response and return the content string or a dict for structured output.

Leave the rest of the code unchanged; the loop, tools, memory, and reflection already work against the current interface.

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

## Dependencies

Standard library only. When you add Ollama/LM Studio in `local_llm.py`, you may need `requests` (or use `urllib.request`) for HTTP.
