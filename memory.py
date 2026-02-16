"""
Simple memory store for the scratch agent.
Facts, observations, and tool results are stored here and injected into the decision step.
"""

from typing import List, Optional


class AgentMemory:
    """
    In-memory store of facts and observations.
    The agent loop reads from this when building context for Reason/Decide
    and updates it after each Act/Observe so memory influences decisions.
    """

    def __init__(self, max_items: int = 100) -> None:
        self._items: List[str] = []
        self._max_items = max_items

    def add(self, entry: str) -> None:
        """Append one observation or fact. Used after each tool result or key finding."""
        self._items.append(entry)
        if len(self._items) > self._max_items:
            self._items = self._items[-self._max_items :]

    def get_recent(self, k: int = 10) -> List[str]:
        """Return the last k entries for inclusion in the prompt."""
        return self._items[-k:] if self._items else []

    def get_summary(self, max_chars: int = 2000) -> str:
        """Return a single string of recent memory for context (e.g. last entries joined)."""
        recent = self.get_recent(50)
        lines = "\n".join(recent)
        if len(lines) > max_chars:
            lines = "..." + lines[-max_chars:]
        return lines if lines else "(no memory yet)"

    def clear(self) -> None:
        """Reset memory (e.g. for a new task)."""
        self._items.clear()
