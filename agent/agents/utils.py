from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from ..llm.base import BaseLLM, ToolCall
from ..memory.state import MemoryState


def build_context(
    goal: str,
    memory: MemoryState,
    snapshot: Dict[str, Any],
    browser_only: bool = False,
    has_browser_action: bool = False,
) -> Dict[str, Any]:
    return {
        "goal": goal,
        "memory_summary": memory.summary,
        "facts": memory.facts,
        "recent_steps": memory.recent_steps(),
        "snapshot": snapshot,
        "browser_only": browser_only,
        "has_browser_action": has_browser_action,
    }


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


def request_tool_call(
    llm: BaseLLM,
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
) -> Tuple[Optional[ToolCall], str]:
    if llm.supports_tools:
        response = llm.complete(messages=messages, tools=tools)
        reason = response.content or ""
        if response.tool_calls:
            return response.tool_calls[0], reason
        return None, reason

    tool_list = [tool["function"]["name"] for tool in tools]
    tool_doc = {
        "instructions": "Respond with JSON only.",
        "format": {"tool": "name", "args": {"key": "value"}, "reason": "short"},
        "tools": tool_list,
    }
    messages = list(messages)
    messages.append({"role": "system", "content": f"Tool spec: {json.dumps(tool_doc)}"})
    response = llm.complete(messages=messages, tools=None)
    payload = _extract_json(response.content or "")
    if not payload:
        return None, response.content or ""
    tool_name = payload.get("tool")
    args = payload.get("args") or {}
    reason = payload.get("reason") or ""
    if tool_name:
        return ToolCall(name=str(tool_name), arguments=args), reason
    return None, reason
