"""
Tool registry and implementations for the scratch agent.
Tools are chosen by the model in the Decide step; the loop runs registry[tool_id].fn(**tool_input).
"""

from typing import Any, Callable, Dict, List, Optional

# Tool shape: id, description, parameters (schema), fn
ToolSpec = Dict[str, Any]

# Mock data for demo; model-driven tool use does not depend on this content
MOCK_SEARCH_RESULTS: Dict[str, List[Dict[str, Any]]] = {
    "acme": [
        {"company": "Acme Corp", "industry": "Manufacturing", "revenue": "10M"},
        {"company": "Acme Labs", "industry": "Tech", "revenue": "2M"},
    ],
    "tech": [
        {"company": "TechStart Inc", "industry": "SaaS", "revenue": "5M"},
    ],
}

MOCK_CONTACTS: Dict[str, Dict[str, Any]] = {
    "acme": {"name": "Jane Doe", "role": "VP Sales", "email": "jane@acme.com"},
    "techstart": {"name": "John Smith", "role": "CEO", "email": "john@techstart.com"},
}


def _search(query: str) -> str:
    """Search for companies by keyword. Returns mock results."""
    key = query.lower().strip() if query else ""
    results = MOCK_SEARCH_RESULTS.get(key, MOCK_SEARCH_RESULTS.get("acme", []))
    if not results:
        return "No results found."
    lines = [f"- {r.get('company', '?')} ({r.get('industry', '?')}, {r.get('revenue', '?')})" for r in results]
    return "\n".join(lines)


def _get_contact(company_key: str) -> str:
    """Get contact info for a company by key (e.g. acme, techstart)."""
    key = (company_key or "").lower().strip()
    contact = MOCK_CONTACTS.get(key)
    if not contact:
        return f"No contact found for '{company_key}'. Known keys: {list(MOCK_CONTACTS.keys())}"
    return f"Name: {contact['name']}, Role: {contact['role']}, Email: {contact['email']}"


def _safe_call(fn: Callable[..., Any], **kwargs: Any) -> Any:
    """Run tool fn with kwargs; let caller handle exceptions for visibility."""
    return fn(**kwargs)


def get_tool_registry() -> Dict[str, ToolSpec]:
    """
    Registry of tools the model can choose from.
    Each tool has id, description, parameters, and fn. No fixed order of execution.
    """
    return {
        "search": {
            "id": "search",
            "description": "Search for companies by keyword (e.g. acme, tech). Returns company name, industry, revenue.",
            "parameters": {"query": "string search term"},
            "fn": _search,
        },
        "get_contact": {
            "id": "get_contact",
            "description": "Get contact details for a company by key (e.g. acme, techstart).",
            "parameters": {"company_key": "string company identifier"},
            "fn": _get_contact,
        },
    }


def run_tool(registry: Dict[str, ToolSpec], tool_id: str, tool_input: Dict[str, Any]) -> Any:
    """
    Execute the tool selected by the model. Called from the agent loop after Decide.
    Raises on unknown tool_id; caller catches and passes error into Observe/memory.
    """
    if tool_id not in registry:
        raise ValueError(f"Unknown tool: {tool_id}. Available: {list(registry.keys())}")
    spec = registry[tool_id]
    fn = spec["fn"]
    return _safe_call(fn, **tool_input)
