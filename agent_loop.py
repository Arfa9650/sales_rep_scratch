"""
Scratch agent: explicit control loop from first principles.
No agent framework. Loop: Reason -> Decide -> Act -> Observe -> Update -> Reflect.
Sales-rep assistant: you represent a company (who you're selling for); prospect is the company you're exploring/contacting.
"""

import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from config import (
    DECIDE_PARSE_RETRIES,
    MAX_STEPS,
    MEMORY_RECENT_K,
    MIN_CONFIDENCE_TO_STOP,
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
        f"Your reasoning so far: {reason_text[:500]}\n\n"
        f"Available tools:\n{tool_descriptions}\n\n"
        "Decide: What should I do next? "
        "If you lack company/industry details or the profile is thin: set should_stop to false and use a tool. "
        "Use search_web with a concrete query (e.g. company name, industry trends) or extract_insights on the profile. "
        "Only set should_stop to true when you have enough to write concrete VALUE HYPOTHESIS, MESSAGING ANGLE, and SUPPORTING EVIDENCE. "
        "Do not stop with 'insufficient information'—use search_web first to gather more, then stop only when confident. "
        "After search_web or extract_insights, use save_note to store key facts (content: string) so they appear in the next step and you avoid hallucination. "
        "Respond with reasoning and a JSON object: next_action, tool_id (e.g. 'search_web', 'extract_insights', or 'save_note'), tool_input (e.g. {\"query\": \"...\"} or {\"content\": \"...\"}), confidence (0-1), should_stop, should_revise, reasoning."
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
        "Evaluate: What assumptions are you making? Is your information sufficient to write VALUE HYPOTHESIS, MESSAGING ANGLE, and SUPPORTING EVIDENCE? "
        "How confident are you (0-1)? If information is still insufficient, recommend continuing and using a tool (e.g. search_web) next step. Should you revise or stop and answer?"
    )
    try:
        raw = _call_model(prompt, "reflect")
        parsed = parse_reflection(raw)
        logger.info("Reflection: %s | confidence=%s should_revise=%s", raw[:300], parsed.get("confidence"), parsed.get("should_revise"))
        return parsed
    except Exception as e:
        logger.warning("Reflect step failed: %s", e)
        return {"confidence": decision.confidence, "should_revise": False, "critique": str(e)}


def _parse_sales_rep_output(final_response: str) -> Dict[str, str]:
    """
    Parse final response into value_hypothesis, messaging_angle, supporting_evidence.
    Prefer section headers (VALUE HYPOTHESIS:, etc.); fallback to LLM extraction.
    """
    out: Dict[str, str] = {
        "value_hypothesis": "",
        "messaging_angle": "",
        "supporting_evidence": "",
    }
    text = (final_response or "").strip()
    # Section headers (case-insensitive, allow variations)
    patterns = [
        (r"VALUE\s*HYPOTHESIS\s*[:\-]\s*(.+?)(?=MESSAGING|SUPPORTING|$)", "value_hypothesis"),
        (r"MESSAGING\s*(?:ANGLE)?\s*[:\-]\s*(.+?)(?=VALUE|SUPPORTING|$)", "messaging_angle"),
        (r"SUPPORTING\s*EVIDENCE(?:\s*OR\s*ASSUMPTIONS)?\s*[:\-]\s*(.+?)(?=VALUE|MESSAGING|$)", "supporting_evidence"),
    ]
    for pattern, key in patterns:
        m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if m:
            out[key] = m.group(1).strip()
    if any(out.values()):
        return out
    # Fallback: one LLM call to structure the response, then parse once
    try:
        prompt = (
            f"Convert this sales-rep response into exactly three short sections. "
            f"Output only the following format, nothing else:\n"
            f"VALUE HYPOTHESIS: <one or two sentences>\n"
            f"MESSAGING ANGLE: <one or two sentences>\n"
            f"SUPPORTING EVIDENCE: <bullets or short paragraph>\n\n"
            f"Response to convert:\n{text[:4000]}"
        )
        structured = _call_model(prompt, "parse_output")
        for pattern, key in patterns:
            m = re.search(pattern, (structured or "").strip(), re.DOTALL | re.IGNORECASE)
            if m:
                out[key] = m.group(1).strip()
        if any(out.values()):
            return out
    except Exception:
        pass
    out["value_hypothesis"] = text[:1500] or "(No value hypothesis extracted)"
    out["messaging_angle"] = "(No messaging angle extracted)" if not out["messaging_angle"] else out["messaging_angle"]
    out["supporting_evidence"] = "(No supporting evidence extracted)" if not out["supporting_evidence"] else out["supporting_evidence"]
    return out


def run_agent(
    task: str,
    max_steps: Optional[int] = None,
    tool_registry: Optional[Dict[str, Any]] = None,
    profile_text: Optional[str] = None,
) -> str:
    """
    Run the scratch agent loop until done or max_steps.
    Returns the final response to the user.
    If tool_registry is provided, use it. Otherwise use get_tool_registry(profile_text=..., memory=memory)
    so that save_note is available (memory is created here).
    """
    max_steps = max_steps or MAX_STEPS
    memory = AgentMemory()
    turn_history: List[Dict[str, Any]] = []
    if tool_registry is not None:
        registry = tool_registry
    else:
        registry = get_tool_registry(profile_text=profile_text, memory=memory)
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
        # Only accept stop if confidence is high enough (so model iterates with tools until satisfied)
        confidence_ok = decision.confidence >= MIN_CONFIDENCE_TO_STOP
        # Reject stop when model said "insufficient" / "need more" but didn't use a tool this step
        insufficient_but_no_tool = (
            decision.should_stop
            and not decision.tool_id
            and any(
                phrase in (decision.reasoning or "").lower()
                for phrase in ("insufficient", "need more", "need additional", "lack ", "not enough")
            )
        )
        if decision.should_stop and (insufficient_but_no_tool or not confidence_ok):
            if insufficient_but_no_tool:
                logger.info("Rejecting stop: model said information insufficient but did not use a tool; continuing.")
            else:
                logger.info("Rejecting stop: confidence %.2f < %.2f; continuing.", decision.confidence, MIN_CONFIDENCE_TO_STOP)
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


SALES_REP_TASK_TEMPLATE = """You are a sales rep assistant.

Who you represent (your company / who you are selling for):
{my_company_description}

Prospect (the company you are exploring or contacting):
Company: {company_name}
Industry: {industry}
Public website or profile text:
{profile_text}

Your goal: Propose (1) a value hypothesis, (2) a suggested messaging angle, (3) supporting evidence or assumptions.
You must use tools when information is thin: use search_web to look up the company and industry, and extract_insights on the profile. After getting results, use save_note to store key facts so they are available in the next step (reduces hallucination). Do not stop with "insufficient information"—iterate: search, save key findings, then synthesize. Only stop when you have enough to write concrete VALUE HYPOTHESIS, MESSAGING ANGLE, and SUPPORTING EVIDENCE.

When you stop and respond, format your final answer with these exact section headers so it can be parsed:
VALUE HYPOTHESIS: <your value hypothesis>
MESSAGING ANGLE: <your suggested messaging angle>
SUPPORTING EVIDENCE: <supporting evidence or assumptions>"""


def run_sales_rep_flow(
    my_company_description: str,
    prospect_company_name: str,
    prospect_industry: str,
    prospect_profile_text: str,
    max_steps: Optional[int] = None,
) -> Dict[str, str]:
    """
    Sales-rep flow: you represent my_company_description; the prospect is the company you're contacting.
    Returns structured value_hypothesis, messaging_angle, supporting_evidence.
    Logs are written to the logs/ directory at the end of the run.
    """
    log_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    try:
        task = SALES_REP_TASK_TEMPLATE.format(
            my_company_description=(my_company_description or "").strip(),
            company_name=prospect_company_name,
            industry=prospect_industry,
            profile_text=(prospect_profile_text or "").strip(),
        )
        final_response = run_agent(
            task, max_steps=max_steps, profile_text=(prospect_profile_text or "").strip()
        )
        parsed = _parse_sales_rep_output(final_response)
        return parsed
    finally:
        logger.removeHandler(file_handler)
        file_handler.close()


if __name__ == "__main__":
    # Who you represent (your company)
    my_company = "K2X Technologies: We provide AI-driven software solutions for industrial companies to improve operational efficiency and reduce downtime."
    # Prospect you are exploring/contacting
    prospect_name = "Antonx"
    prospect_industry = "Software Solutions"
    prospect_profile = "antonx.com"

    result = run_sales_rep_flow(my_company, prospect_name, prospect_industry, prospect_profile)
    print("Value hypothesis:", result["value_hypothesis"])
    print("Messaging angle:", result["messaging_angle"])
    print("Supporting evidence:", result["supporting_evidence"])
