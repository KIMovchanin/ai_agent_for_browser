from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..llm.base import BaseLLM, LLMResponse, ToolCall
from ..memory.state import MemoryState
from ..tools.registry import tool_definitions
from .prompts import BASE_AGENT_PROMPT
from .utils import build_context, request_tool_call


class Extractor:
    def __init__(self, llm: BaseLLM) -> None:
        self.llm = llm

    def decide(
        self,
        goal: str,
        memory: MemoryState,
        snapshot: Dict[str, Any],
        browser_only: bool = False,
        has_browser_action: bool = False,
        goal_urls: Optional[List[str]] = None,
        visited_goal_urls: Optional[List[str]] = None,
    ) -> tuple[Optional[ToolCall], str]:
        context = build_context(
            goal,
            memory,
            snapshot,
            browser_only,
            has_browser_action,
            goal_urls,
            visited_goal_urls,
        )
        browser_note = ""
        if browser_only:
            browser_note = (
                " Browser-only mode is ON. Do not answer directly or call finish until "
                "you have used browser tools to access information."
            )
        system_prompt = (
            f"{BASE_AGENT_PROMPT} "
            "You are the Extractor sub-agent. Your job is to extract structured data or "
            "summaries that satisfy the goal. Prefer the extract tool with a concise schema. "
            "If the page is not ready, use navigation tools to reach the right content."
            " Preserve the user's product terms and do not substitute them."
            " Use ask_user only if login, 2FA, or captcha is needed, or if blocked. "
            "Avoid repeated questions; reuse prior user choices. "
            "If you use ask_user, include 2-3 short numbered options the user can reply with."
            " Output tool calls only; do not answer in prose."
            + browser_note
        )
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(context, ensure_ascii=True)},
        ]

        tools = tool_definitions()
        tool_call, reason = request_tool_call(self.llm, messages, tools)
        return tool_call, reason

    def extract_with_schema(self, schema: str, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        prompt = (
            "Extract structured data from the snapshot. "
            "Return JSON that matches the provided schema. "
            f"Schema: {schema}\nSnapshot:\n{json.dumps(snapshot, ensure_ascii=True)}"
        )
        response: LLMResponse = self.llm.complete(
            messages=[
                {"role": "system", "content": "You are a precise extractor."},
                {"role": "user", "content": prompt},
            ],
            tools=None,
        )
        try:
            return json.loads(response.content or "{}")
        except json.JSONDecodeError:
            return {"error": "extract_failed", "raw": response.content}
