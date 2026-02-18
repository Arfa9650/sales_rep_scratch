---
name: Sales rep flow and real tools
overview: Replace mock tools with one real tool (extract_insights from profile via LLM), add a sales-rep flow that takes company name, industry, and profile text and outputs value hypothesis, messaging angle, and supporting evidence; update agent_loop, tools, and README accordingly.
todos: []
isProject: false
---

# Sales Rep Agent Flow and Real Tools

## Goal

- **Purpose of the agent**: Given **Company name**, **Industry**, and **Public website or short profile text**, the agent uses the loop and (optionally) one real tool to propose:
  1. **Value hypothesis**
  2. **Suggested messaging angle**
  3. **Supporting evidence or assumptions**
- **No mock data**: Remove all mock search/contact data. Use one real tool that operates on the provided profile (LLM-based extraction). The agent makes real decisions over real context.
- **Flow**: Single entry point that accepts the three inputs and returns a structured result with the three outputs; other scripts are updated so the loop and tools support this flow.

---

## 1. Tools: remove mock, add one real tool

**File**: [tools.py](tools.py)

- **Remove**: `MOCK_SEARCH_RESULTS`, `MOCK_CONTACTS`, `_search`, `_get_contact`, and the `search` / `get_contact` registry entries.
- **Add one tool**: `**extract_insights**`
  - **Behavior**: Takes the **company profile text** (or a chunk of it) and calls the same LLM via `local_llm.complete()` with a prompt like: “From this company profile, extract key facts, pain points, opportunities, and differentiators. Return a concise bullet list.” Returns the model’s text. No mock data; the only input is the user-provided profile.
  - **Registry**: Expose a single tool so the Decide step can choose “use extract_insights” when it wants structured insights from the profile before synthesizing the three deliverables.
- **Profile in scope**: The profile text can be long. Two options:
  - **A (recommended)**: Registry is built per run with the profile in scope: `get_tool_registry(profile_text: Optional[str] = None)` returns a dict. When `profile_text` is provided (sales-rep flow), `extract_insights` is implemented as a function that closes over that `profile_text` and ignores or lightly uses `tool_input` (so the model can call it with empty or minimal args). When `profile_text` is None (generic `run_agent`), you can either leave the registry empty or still offer `extract_insights` with a note in the description that “profile is in the task context.”
  - **B**: Store “current profile” in a module-level or thread-local variable set by the sales-rep flow before calling `run_agent`; `extract_insights` reads from that when `tool_input` is empty.
- **Tool spec**: `id`: `"extract_insights"`, `description`: e.g. “Extract key facts, pain points, and opportunities from the company profile text. Use this to structure the profile before proposing value hypothesis and messaging.” `parameters`: e.g. `{"profile_text": "optional; the profile is in the task context"}`, `fn`: the callable that runs the LLM extraction (over the in-scope profile).
- **Circular import**: `tools.py` will call `local_llm.complete()`. That’s fine: `agent_loop` already imports both `tools` and `local_llm`; avoid `agent_loop` importing from `tools` in a way that forces `tools` to import `agent_loop`.

---

## 2. Agent loop: sales-rep flow and structured output

**File**: [agent_loop.py](agent_loop.py)

- `**run_agent(task, max_steps=None, tool_registry=None)**`: Add an optional argument `**tool_registry**`. If provided, use it instead of `get_tool_registry()`. This allows the sales-rep flow to pass a registry built with `get_tool_registry(profile_text)` so the single tool has access to the profile. If `tool_registry` is None, call `get_tool_registry()` with no args (or with None) for backward compatibility.
- `**run_sales_rep_flow(company_name, industry, profile_text)**` (new):
  - Build **task** string that includes:
    - Company name, industry, and the full profile/website text.
    - Explicit goal: “Propose (1) a value hypothesis, (2) a suggested messaging angle, (3) supporting evidence or assumptions. You may use the extract_insights tool on the profile to get structured insights first, then synthesize your answer.”
  - Build registry: `get_tool_registry(profile_text)`.
  - Call `**run_agent(task, tool_registry=registry)**`.
  - **Parse** the returned `final_response` into three fields:
    - **Preferred**: If the model was prompted to end with clear section headers (e.g. “VALUE HYPOTHESIS: …”, “MESSAGING ANGLE: …”, “SUPPORTING EVIDENCE: …”), parse with regex and return `{"value_hypothesis": ..., "messaging_angle": ..., "supporting_evidence": ...}`.
    - **Fallback**: If parsing fails or is ambiguous, make one more LLM call (e.g. `complete_structured` or `complete` with “output JSON”) to turn the final response into that structure; then return the dict.
  - Return type: **dict** with keys `value_hypothesis`, `messaging_angle`, `supporting_evidence` (all strings). If the agent hits max steps without a clear answer, still return a dict with placeholder or truncated content for each key so callers always get the same shape.
- **Prompting in the task**: In the task text, instruct the model to produce a final answer that either uses the three section headers above or a similar unambiguous format so parsing is reliable.
- `**if __name__ == "__main__"**`: Change to demonstrate the sales-rep flow: e.g. call `run_sales_rep_flow("Acme Corp", "Manufacturing", "<short sample profile>")` and print the structured result (and/or log as today).

---

## 3. Decisions and tool_input

**File**: [decisions.py](decisions.py)

- No change to the **Decision** dataclass or to **parse_decision** logic.
- The only tool is **extract_insights**. The model may send `tool_id: "extract_insights"` and `tool_input: {}` or `{"profile_text": "..."}`. The tool implementation (in [tools.py](tools.py)) will use the in-scope profile when `tool_input` is empty or when it prefers the closed-over profile, so existing decision parsing that passes `tool_input` through to `run_tool` is sufficient.

---

## 4. Config and local_llm

- **config.py**: No change required for this flow (Ollama URL/model stay as in the previous plan).
- **local_llm.py**: No change to the interface. The new tool will call `complete()` only; no new entry points.

---

## 5. README updates

**File**: [README.md](README.md) (and [documentation/README.md](documentation/README.md) if present)

- **Purpose**: State that the agent is a **sales rep** agent: given company name, industry, and profile/website text, it proposes a value hypothesis, a messaging angle, and supporting evidence.
- **Flow**:
  - **Inputs**: Company name, Industry, Public website or short profile text.
  - **Process**: Agent loop (reason → decide → act → observe → update → reflect). The model can call the **extract_insights** tool to get structured insights from the profile, then reason and stop with a final answer.
  - **Outputs**: Structured result with **value_hypothesis**, **suggested_messaging_angle** (or **messaging_angle**), **supporting_evidence** (or **supporting_evidence_or_assumptions**).
- **Tools**: Single tool, **extract_insights** — no mock data; it uses the LLM to extract key facts/pain points/opportunities from the provided profile text. No web search; all reasoning is over the given inputs.
- **How to run**:
  - Sales-rep flow: `run_sales_rep_flow(company_name, industry, profile_text)` returns a dict; or from CLI (e.g. `python agent_loop.py` running the sales-rep demo).
  - Generic loop: `run_agent(task)` still available for custom tasks.
- **Config**: Keep existing config section; mention Ollama (base URL, model) as in the remote-Ollama plan if that’s already integrated.

---

## 6. Summary of file changes


| File                           | Changes                                                                                                                                                                                                                                                                                                               |
| ------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [tools.py](tools.py)           | Remove all mock data and mock tools. Add `extract_insights` (LLM-based, real). Support `get_tool_registry(profile_text)` so the tool has access to the current run’s profile.                                                                                                                                         |
| [agent_loop.py](agent_loop.py) | Add optional `tool_registry` to `run_agent`. Add `run_sales_rep_flow(company_name, industry, profile_text)` that builds task, runs agent with profile-scoped registry, parses final response into `{value_hypothesis, messaging_angle, supporting_evidence}`, returns dict. Update `__main__` to demo sales-rep flow. |
| [decisions.py](decisions.py)   | No code change.                                                                                                                                                                                                                                                                                                       |
| [config.py](config.py)         | No change for this task.                                                                                                                                                                                                                                                                                              |
| [README.md](README.md)         | Document sales-rep purpose, flow (inputs → outputs), single real tool, no mock data; how to run the flow and optional generic `run_agent`.                                                                                                                                                                            |


After this, the agent has a clear purpose (sales-rep proposal from profile-only inputs), uses one real tool (extract_insights), and returns a structured result with value hypothesis, messaging angle, and supporting evidence; all scripts are aligned with this flow.