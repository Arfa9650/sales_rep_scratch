"""
Scratch agent: explicit control loop from first principles.
No agent framework. Loop: Reason -> Decide -> Act -> Observe -> Update -> Reflect.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from config import (
    DECIDE_PARSE_RETRIES,
    MAX_STEPS,
    MEMORY_RECENT_K,
    MODEL_ERROR_RETRIES,
)
from decisions import Decision, parse_decision, parse_reflection
from local_llm import complete, complete_structured
from memory import AgentMemory
from tools import get_tool_registry, run_tool

logger = logging.getLogger("scratch_agent")
logger.setLevel(logging.INFO)
if not logger.handlers:
    h = logging.StreamHandler()
    h.setLevel(logging.INFO)
    logger.addHandler(h)


def _build_context(task: str, memory: AgentMemory, turn_history: List[Dict[str, Any]]) -> str:
    """Build context string for Reason/Decide: task + memory + last N turns."""
    mem_summary = memory.get_summary()
    history_str = "\n".join(
        f"Turn {i+1}: {t.get('action', '')} -> {t.get('observation', '')[:200]}"
        for i, t in enumerate(turn_history[-5:])
    ) or "(no turns yet)"
    return f"Task: {task}\n\nMemory (prior findings):\n{mem_summary}\n\nRecent turns:\n{history_str}"


def _call_model(prompt: str, step_name: str) -> str:
    """Call local LLM with retries on connection/API errors."""
    last_err: Optional[Exception] = None
    for attempt in range(MODEL_ERROR_RETRIES + 1):
        try:
            return complete(prompt) or ""
        except Exception as e:
            last_err = e
            logger.warning("Model error (%s) attempt %s: %s", step_name, attempt + 1, e)
            if attempt == MODEL_ERROR_RETRIES:
                raise
    raise last_err or RuntimeError(f"{step_name} failed after retries")


def _reason(context: str) -> str:
    """Reason step: call local LLM with situation; what do we know, what is missing?"""
    prompt = (
        f"{context}\n\n"
        "As the agent, briefly state: what do you know so far and what is still missing? One short paragraph."
    )
    try:
        out = _call_model(prompt, "reason")
        logger.info("Reasoning: %s", (out or "")[:500])
        return out or ""
    except Exception as e:
        logger.error("Reason step failed: %s", e)
        return f"(Reasoning failed: {e})"


def _decide(context: str, reason_text: str, tool_descriptions: str) -> Decision:
    """
    Decide step: model outputs what to do next (action, tool?, args, confidence, stop?, revise?).
    This is the single place where the agent decides what to do next.
    """
    prompt = (
        f"{context}\n\n"
        f"Your reasoning so far: {reason_text[:300]}\n\n"
        f"Available tools:\n{tool_descriptions}\n\n"
        "Decide: What should I do next? Do I need a tool (if so, which id and what arguments)? "
        "Is my information sufficient? How confident am I (0-1)? Should I revise my approach? Should I stop and respond to the user? "
        "Respond with a short reasoning and, if possible, a JSON object with: next_action, tool_id, tool_input (dict), confidence, should_stop, should_revise, reasoning."
    )
    last_error: Optional[Exception] = None
    for attempt in range(DECIDE_PARSE_RETRIES + 1):
        try:
            raw = _call_model(prompt, "decide")
            structured = complete_structured(prompt)  # placeholder returns dict; real LLM may only return raw
            decision = parse_decision(raw, structured_fallback=structured)
            logger.info(
                "Decision: next_action=%s tool_id=%s should_stop=%s should_revise=%s confidence=%s reason=%s",
                decision.next_action,
                decision.tool_id or "(none)",
                decision.should_stop,
                decision.should_revise,
                decision.confidence,
                (decision.reasoning or "")[:200],
            )
            return decision
        except Exception as e:
            last_error = e
            logger.warning("Parse decision attempt %s failed: %s", attempt + 1, e)
            if attempt < DECIDE_PARSE_RETRIES:
                prompt = (
                    "Your previous response was invalid. Please respond with a JSON object containing exactly: "
                    "next_action, tool_id, tool_input (object), confidence (0-1), should_stop (bool), should_revise (bool), reasoning (string)."
                )
    raise last_error or RuntimeError("Decide step failed after retries")


def _act(registry: Dict[str, Any], decision: Decision) -> Tuple[Any, Optional[str]]:
    """
    Act step: if tool_id set, run the tool; otherwise no-op.
    Returns (result, error_message). Error message is set on exception.
    """
    if not decision.tool_id:
        return None, None
    try:
        result = run_tool(registry, decision.tool_id, decision.tool_input)
        logger.info("Tool chosen: %s (reason: %s) -> result: %s", decision.tool_id, decision.reasoning[:100], str(result)[:200])
        return result, None
    except Exception as e:
        err_msg = str(e)
        logger.warning("Tool error: %s -> %s", decision.tool_id, err_msg)
        return None, err_msg


def _observe(tool_result: Any, tool_error: Optional[str], tool_id: str) -> str:
    """Observe step: record tool result or error for memory and history."""
    if tool_error:
        obs = f"Tool {tool_id} failed: {tool_error}"
    elif tool_id:
        obs = f"Tool {tool_id} result: {tool_result}"
    else:
        obs = "No tool used."
    logger.info("Observation: %s", obs[:300])
    return obs


def _reflect(context: str, observation: str, decision: Decision) -> Dict[str, Any]:
    """
    Reflect step: self-critique. Should we revise or stop?
    Visible in flow: output is logged and used to set should_revise / should_stop.
    """
    prompt = (
        f"{context}\n\n"
        f"Last observation: {observation}\n\n"
        "Evaluate: What assumptions are you making? Is your information sufficient? "
        "How confident are you (0-1)? Should you revise your approach or stop and answer the user?"
    )
    try:
        raw = _call_model(prompt, "reflect")
        parsed = parse_reflection(raw)
        logger.info("Reflection: %s | confidence=%s should_revise=%s", raw[:300], parsed.get("confidence"), parsed.get("should_revise"))
        return parsed
    except Exception as e:
        logger.warning("Reflect step failed: %s", e)
        return {"confidence": decision.confidence, "should_revise": False, "critique": str(e)}


def run_agent(task: str, max_steps: Optional[int] = None) -> str:
    """
    Run the scratch agent loop until done or max_steps.
    Returns the final response to the user.
    """
    max_steps = max_steps or MAX_STEPS
    memory = AgentMemory()
    turn_history: List[Dict[str, Any]] = []
    registry = get_tool_registry()
    tool_descriptions = "\n".join(
        f"- {tid}: {spec.get('description', '')} (params: {spec.get('parameters', {})})"
        for tid, spec in registry.items()
    )

    done = False
    step = 0
    final_response = ""

    while not done and step < max_steps:
        step += 1
        logger.info("--- Step %s ---", step)
        context = _build_context(task, memory, turn_history)

        # 1. Reason
        reason_text = _reason(context)

        # 2. Decide (single place where the agent decides what to do next)
        decision = _decide(context, reason_text, tool_descriptions)

        # 3. Act
        tool_result, tool_error = _act(registry, decision)

        # 4. Observe
        observation = _observe(tool_result, tool_error, decision.tool_id or "")

        # 5. Update: append to memory and turn history so memory influences future decisions
        memory.add(f"Step {step}: decision={decision.next_action} tool={decision.tool_id or 'none'}; observation: {observation[:150]}")
        turn_history.append({
            "action": f"tool={decision.tool_id}" if decision.tool_id else decision.next_action,
            "observation": observation,
        })

        # 6. Reflect
        reflection = _reflect(context, observation, decision)
        should_revise = decision.should_revise or reflection.get("should_revise", False)
        if should_revise:
            logger.info("Revising: looping again without advancing to final answer.")
            continue
        if decision.should_stop:
            done = True
            final_response = decision.reasoning or observation or "Task completed."
            logger.info("Stopping. Final response: %s", final_response[:300])
            break

    if not final_response and step >= max_steps:
        final_response = "Max steps reached; no final answer yet."
        logger.info("Max steps reached.")

    return final_response


if __name__ == "__main__":
    # Example: run with a task so the loop, tool path, memory, and reflection are visible
    result = run_agent("Find contact info for Acme Corp.")
    print("Final response:", result)
