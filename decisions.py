"""
Parse model output into the decision struct.
This is the single place where the model's text is turned into next_action, tool_id, should_stop, etc.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class Decision:
    """Result of the Decide step: what to do next, whether to use a tool, stop, or revise."""
    next_action: str = "continue"
    tool_id: str = ""
    tool_input: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.5
    should_stop: bool = False
    should_revise: bool = False
    reasoning: str = ""


def parse_decision(raw: str, structured_fallback: Optional[Dict[str, Any]] = None) -> Decision:
    """
    Map model output to a Decision. This is where the agent decides what to do next.
    Supports: (1) structured dict from complete_structured, (2) JSON block in text, (3) heuristic parse.
    """
    if structured_fallback is not None and isinstance(structured_fallback, dict):
        return _decision_from_dict(structured_fallback)

    # Try to find a JSON block in the response
    json_match = re.search(r"\{[^{}]*\"(?:tool_id|next_action|should_stop)[^{}]*\}", raw, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group())
            return _decision_from_dict(data)
        except (json.JSONDecodeError, TypeError):
            pass

    # Heuristic: look for explicit phrases
    raw_lower = raw.lower()
    should_stop = "should_stop" in raw_lower or "stop and respond" in raw_lower or "yes" in raw_lower and "stop" in raw_lower
    should_revise = "should_revise" in raw_lower or "revise" in raw_lower
    confidence = 0.5
    conf_match = re.search(r"confidence[:\s]+(\d+\.?\d*)", raw_lower)
    if conf_match:
        try:
            confidence = float(conf_match.group(1))
            if confidence > 1:
                confidence /= 100.0
        except ValueError:
            pass

    return Decision(
        next_action="continue",
        tool_id="",
        tool_input={},
        confidence=confidence,
        should_stop=should_stop,
        should_revise=should_revise,
        reasoning=raw.strip() or "No reasoning provided.",
    )


def _decision_from_dict(data: Dict[str, Any]) -> Decision:
    """Build Decision from a dict (e.g. from complete_structured or parsed JSON)."""
    tool_input = data.get("tool_input") or data.get("tool_args") or {}
    if isinstance(tool_input, str):
        tool_input = {"query": tool_input} if "query" in (data.get("parameters") or "") else {"company_key": tool_input}
    return Decision(
        next_action=str(data.get("next_action", "continue")),
        tool_id=str(data.get("tool_id", "")).strip(),
        tool_input=tool_input if isinstance(tool_input, dict) else {},
        confidence=float(data.get("confidence", 0.5)),
        should_stop=bool(data.get("should_stop", False)),
        should_revise=bool(data.get("should_revise", False)),
        reasoning=str(data.get("reasoning", "")),
    )


def parse_reflection(raw: str) -> Dict[str, Any]:
    """
    Parse reflection/self-critique output: confidence, should_revise, gaps.
    Used after the Reflect step to decide whether to loop again or stop.
    """
    raw_lower = raw.lower()
    should_revise = "revise" in raw_lower or "should_revise" in raw_lower or "not sufficient" in raw_lower
    confidence = 0.5
    conf_match = re.search(r"confidence[:\s]+(\d+\.?\d*)", raw_lower)
    if conf_match:
        try:
            confidence = float(conf_match.group(1))
            if confidence > 1:
                confidence /= 100.0
        except ValueError:
            pass
    return {"confidence": confidence, "should_revise": should_revise, "critique": raw.strip()}
