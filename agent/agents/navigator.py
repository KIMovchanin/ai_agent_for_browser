from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..llm.base import BaseLLM, ToolCall
from ..memory.state import MemoryState
from ..tools.registry import tool_definitions
from .utils import build_context, request_tool_call


class Navigator:
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
            browser_note = (
                " Browser-only mode is ON. Do not answer directly or call finish until "
                "you have used browser tools to access information. If no URL is given, "
                "navigate to a relevant site or a search engine first."
            )
        system_prompt = (
            "You are the Navigator sub-agent. Your job is to move through the website and "
            "reach the right page or UI state. Use only one tool call. "
            "If the goal includes a URL or domain name, navigate to it directly (do not search for it). "
            "If you type into a search box, prefer setting press_enter=true to submit. "
            "If a search results page is visible, click the most relevant result link to reach the target site. "
            "Avoid destructive actions. If login, 2FA, or captcha is needed, use ask_user. "
            "Prefer click/type on elements from snapshot by element_id."
            + browser_note
        )
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(context, ensure_ascii=True)},
        ]

        tools = tool_definitions()
        tool_call, reason = request_tool_call(self.llm, messages, tools)
        return tool_call, reason
