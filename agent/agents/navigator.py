from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

from ..llm.base import BaseLLM, ToolCall
from ..memory.state import MemoryState
from ..tools.registry import tool_definitions
from .prompts import BASE_AGENT_PROMPT
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
                "you have used browser tools to access information. If no URL is given, "
                "navigate to a relevant site or a search engine first."
            )
        system_prompt = (
            f"{BASE_AGENT_PROMPT} "
            "You are the Navigator sub-agent. Your job is to move through the website and "
            "reach the right page or UI state. Use only one tool call. "
            "Output tool calls only; do not answer in prose. "
            "If the goal includes a URL or domain name, navigate to it directly (do not search for it). "
            "If you type into a search box, prefer setting press_enter=true to submit. "
            "If a search results page is visible, click the most relevant result link to reach the target site. "
            "Preserve the user's product terms and do not substitute them. Use goal_query if provided. "
            "Avoid destructive actions. Use ask_user only if login, 2FA, or captcha is needed, "
            "or if you are truly blocked. Avoid repeated questions; reuse prior user choices. "
            "If you use ask_user, include 2-3 short numbered options the user can reply with. "
            "Prefer click/type on elements from snapshot by element_id. "
            "Never open About/Privacy/Terms pages unless explicitly requested. "
            "Always include element_id or click_strategy for click/type, and include url for navigate."
            + browser_note
        )
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(context, ensure_ascii=True)},
        ]

        tools = tool_definitions()
        tool_call, reason = request_tool_call(self.llm, messages, tools)
        if tool_call:
            return tool_call, reason
        fallback_call, fallback_reason = self._fallback_tool(context, snapshot)
        return fallback_call, fallback_reason or reason

    @staticmethod
    def _fallback_tool(
        context: Dict[str, Any],
        snapshot: Dict[str, Any],
    ) -> Tuple[Optional[ToolCall], str]:
        next_goal_url = (context.get("next_goal_url") or "").strip()
        if next_goal_url:
            current_url = (snapshot.get("url") or "").strip()
            if next_goal_url not in current_url:
                return (
                    ToolCall(name="navigate", arguments={"url": next_goal_url}),
                    "Fallback: navigate to the next goal URL.",
                )
        goal_url = (context.get("goal_url") or "").strip()
        if goal_url:
            current_url = (snapshot.get("url") or "").strip()
            if goal_url not in current_url:
                return ToolCall(name="navigate", arguments={"url": goal_url}), "Fallback: navigate to goal URL."

        goal_text = (context.get("goal") or "").strip()
        goal_query = (context.get("goal_query") or goal_text).strip()
        if goal_text and ("wikipedia" in goal_text.lower() or "википед" in goal_text.lower()):
            query = goal_query.strip()
            if query:
                base = "https://en.wikipedia.org"
                if Navigator._contains_cyrillic(query) or Navigator._contains_cyrillic(goal_text):
                    base = "https://ru.wikipedia.org"
                url = f"{base}/w/index.php?search={quote(query)}"
                current_url = (snapshot.get("url") or "").strip()
                if base not in current_url:
                    return ToolCall(
                        name="navigate",
                        arguments={"url": url},
                    ), "Fallback: open Wikipedia search."
        if not goal_query:
            return None, ""

        if not Navigator._is_search_context(snapshot, goal_text):
            return None, ""

        current_url = (snapshot.get("url") or "").lower()
        if any(token in current_url for token in ["search=", "q=", "query="]):
            element = Navigator._find_element_by_query(snapshot, goal_query)
            if element and element.get("id"):
                return (
                    ToolCall(
                        name="click",
                        arguments={"element_id": element["id"]},
                    ),
                    "Fallback: click a result matching the query.",
                )
            element = Navigator._pick_result_link(snapshot, exclude_id=None)
            if element and element.get("id"):
                return (
                    ToolCall(
                        name="click",
                        arguments={"element_id": element["id"]},
                    ),
                    "Fallback: click a top search result.",
                )

        element = Navigator._pick_search_input(snapshot)
        if element and element.get("id"):
            return (
                ToolCall(
                    name="type",
                    arguments={
                        "element_id": element["id"],
                        "text": goal_query,
                        "press_enter": True,
                    },
                ),
                "Fallback: type search query into search field.",
            )
        return None, ""

    @staticmethod
    def _find_element_by_query(snapshot: Dict[str, Any], query: str) -> Optional[Dict[str, Any]]:
        if not query:
            return None
        elements = snapshot.get("interactive_elements", []) or []
        query_lower = query.lower()
        tokens = [t for t in re.split(r"\s+", query_lower) if len(t) > 2]
        for element in elements:
            role = (element.get("role") or "").lower()
            if role not in {"link", "button"}:
                continue
            text = " ".join(
                [
                    element.get("name") or "",
                    element.get("aria_label") or "",
                    element.get("text") or "",
                ]
            ).lower()
            if query_lower in text:
                return element
            if tokens and all(token in text for token in tokens):
                return element
        return None

    @staticmethod
    def _pick_search_input(snapshot: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        elements = snapshot.get("interactive_elements", []) or []
        keywords = (
            "search",
            "find",
            "looking for",
            "\u043f\u043e\u0438\u0441\u043a",
            "\u0438\u0441\u043a\u0430\u0442\u044c",
            "\u043d\u0430\u0439\u0442\u0438",
            "\u0432\u0432\u0435\u0434\u0438\u0442\u0435",
        )
        roles = {"input", "textbox", "searchbox", "combobox"}

        for element in elements:
            role = (element.get("role") or "").lower()
            if role not in roles:
                continue
            label = " ".join(
                [
                    element.get("name") or "",
                    element.get("aria_label") or "",
                    element.get("text") or "",
                ]
            ).lower()
            if any(keyword in label for keyword in keywords):
                return element
        return None

    @staticmethod
    def _pick_result_link(
        snapshot: Dict[str, Any],
        exclude_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        elements = snapshot.get("interactive_elements", []) or []
        banned = (
            "images",
            "videos",
            "news",
            "maps",
            "settings",
            "tools",
            "translate",
            "about",
            "privacy",
            "terms",
            "cache",
            "google",
            "duckduckgo",
            "bing",
            "\u043a\u0430\u0440\u0442\u0438\u043d",
            "\u0432\u0438\u0434\u0435\u043e",
            "\u043d\u043e\u0432\u043e\u0441\u0442",
            "\u043a\u0430\u0440\u0442\u044b",
            "\u043d\u0430\u0441\u0442\u0440\u043e\u0439\u043a",
            "\u0438\u043d\u0441\u0442\u0440\u0443\u043c\u0435\u043d\u0442",
            "\u043e \u043d\u0430\u0441",
            "\u043f\u043e\u043b\u0438\u0442\u0438\u043a",
            "\u0432\u043e\u0439\u0442\u0438",
        )
        candidates = []
        for element in elements:
            if exclude_id and str(element.get("id")) == str(exclude_id):
                continue
            role = (element.get("role") or "").lower()
            if role not in {"link", "button"}:
                continue
            text = " ".join(
                [
                    element.get("name") or "",
                    element.get("aria_label") or "",
                    element.get("text") or "",
                ]
            ).strip()
            if len(text) < 4:
                continue
            lowered = text.lower()
            if any(word in lowered for word in banned):
                continue
            bbox = element.get("bbox") or {}
            y = int(bbox.get("y", 0))
            if y < 120:
                continue
            candidates.append((y, -len(text), element))
        if not candidates:
            return None
        candidates.sort(key=lambda item: (item[0], item[1]))
        return candidates[0][2]

    @staticmethod
    def _is_search_context(snapshot: Dict[str, Any], goal_text: str) -> bool:
        current_url = (snapshot.get("url") or "").lower()
        if any(host in current_url for host in ["duckduckgo.com", "google.com", "bing.com", "yandex."]):
            return True
        if re.search(r"\b(find|search|look for|searching|найди|поиск|искать|ищи|найти)\b", goal_text, re.IGNORECASE):
            return True
        return False

    @staticmethod
    def _contains_cyrillic(text: str) -> bool:
        return re.search(r"[\u0400-\u04FF]", text) is not None
