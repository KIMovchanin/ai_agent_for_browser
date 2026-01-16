from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..llm.base import BaseLLM, ToolCall
from ..memory.state import MemoryState
from ..tools.registry import tool_definitions
from .utils import build_context, request_tool_call


class Reflector:
    def __init__(self, llm: BaseLLM) -> None:
        self.llm = llm

    def decide(
        self,
        goal: str,
        memory: MemoryState,
        snapshot: Dict[str, Any],
        browser_only: bool = False,
        has_browser_action: bool = False,
    ) -> tuple[Optional[ToolCall], str]:
        context = build_context(goal, memory, snapshot, browser_only, has_browser_action)
        browser_note = ""
        if browser_only:
            browser_note = " Browser-only mode is ON. Prefer browser recovery actions."
        system_prompt = (
            "You are the Reflector sub-agent. Diagnose why progress stalled or actions failed. "
            "Propose a recovery action (scroll, back, alternate click, wait, ask_user). "
            "Use only one tool call."
            + browser_note
        )
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(context, ensure_ascii=True)},
        ]

        tools = tool_definitions()
        tool_call, reason = request_tool_call(self.llm, messages, tools)
        return tool_call, reason
