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
    Saved notes are explicit facts the model chose to save for the next step (reduces hallucination).
    """

    def __init__(self, max_items: int = 100, max_saved_notes: int = 50) -> None:
        self._items: List[str] = []
        self._max_items = max_items
        self._saved_notes: List[str] = []
        self._max_saved_notes = max_saved_notes

    def add(self, entry: str) -> None:
        """Append one observation or fact. Used after each tool result or key finding."""
        self._items.append(entry)
        if len(self._items) > self._max_items:
            self._items = self._items[-self._max_items :]

    def add_saved_note(self, note: str) -> None:
        """Save a note the model explicitly chose to keep for later steps. Shown in context."""
        note = (note or "").strip()
        if not note:
            return
        self._saved_notes.append(note)
        if len(self._saved_notes) > self._max_saved_notes:
            self._saved_notes = self._saved_notes[-self._max_saved_notes :]

    def get_recent(self, k: int = 10) -> List[str]:
        """Return the last k entries for inclusion in the prompt."""
        return self._items[-k:] if self._items else []

    def get_summary(self, max_chars: int = 2000) -> str:
        """Return a single string of recent memory for context (e.g. last entries joined)."""
        parts = []
        if self._saved_notes:
            notes_str = "\n".join(f"- {n}" for n in self._saved_notes[-20:])
            parts.append("Saved notes (use these; do not re-invent):\n" + notes_str)
        recent = self.get_recent(50)
        if recent:
            parts.append("Step log:\n" + "\n".join(recent))
        lines = "\n\n".join(parts)
        if len(lines) > max_chars:
            lines = "..." + lines[-max_chars:]
        return lines if lines else "(no memory yet)"

    def clear(self) -> None:
        """Reset memory (e.g. for a new task)."""
        self._items.clear()
        self._saved_notes.clear()
