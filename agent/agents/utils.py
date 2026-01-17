from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from ..llm.base import BaseLLM, ToolCall
from ..memory.state import MemoryState


def build_context(
    goal: str,
    memory: MemoryState,
    snapshot: Dict[str, Any],
    browser_only: bool = False,
    has_browser_action: bool = False,
    goal_urls: Optional[List[str]] = None,
    visited_goal_urls: Optional[List[str]] = None,
) -> Dict[str, Any]:
    goal_urls = goal_urls or extract_goal_urls(goal)
    visited_goal_urls = visited_goal_urls or []
    return {
        "goal": goal,
        "goal_url": extract_goal_url(goal),
        "goal_query": extract_goal_query(goal),
        "goal_urls": goal_urls,
        "visited_goal_urls": visited_goal_urls,
        "next_goal_url": select_next_goal_url(goal_urls, visited_goal_urls),
        "goal_url_ordered": should_enforce_goal_order(goal) if goal_urls else False,
        "memory_summary": memory.summary,
        "facts": memory.facts[-20:],
        "recent_steps": memory.recent_steps(limit=20),
        "snapshot": _compact_snapshot(snapshot),
        "browser_only": browser_only,
        "has_browser_action": has_browser_action,
    }


def extract_goal_url(goal: str) -> str:
    url_match = re.search(r"https?://\\S+", goal)
    if url_match:
        return url_match.group(0).rstrip(").,;")
    www_match = re.search(r"\\bwww\\.[^\\s]+", goal)
    if www_match:
        return f"https://{www_match.group(0).rstrip(').,;')}"
    domain_match = re.search(r"\\b([a-z0-9-]+\\.)+[a-z]{2,10}\\b", goal, re.IGNORECASE)
    if domain_match:
        return f"https://{domain_match.group(0)}"
    return ""


def extract_goal_urls(goal: str) -> List[str]:
    urls: List[str] = []
    for match in re.finditer(r"https?://\\S+", goal):
        urls.append(match.group(0).rstrip(").,;"))
    for match in re.finditer(r"\\bwww\\.[^\\s]+", goal):
        urls.append(f"https://{match.group(0).rstrip(').,;')}")
    seen: set[str] = set()
    ordered: List[str] = []
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        ordered.append(url)
    return ordered


def select_next_goal_url(goal_urls: List[str], visited_goal_urls: List[str]) -> str:
    visited = set(visited_goal_urls)
    for url in goal_urls:
        if url not in visited:
            return url
    return ""


def should_enforce_goal_order(goal: str) -> bool:
    if not goal:
        return False
    cues = [
        r"\bafter\b",
        r"\bthen\b",
        r"\bпосле\b",
        r"\bзатем\b",
        r"\bкак\s+(?:ознакомишься|изучишь|прочитаешь|посмотришь)\b",
        r"\bсначала\b",
    ]
    return any(re.search(pattern, goal, re.IGNORECASE) for pattern in cues)


def extract_goal_query(goal: str) -> str:
    goal = goal.strip()
    if not goal:
        return ""
    url_match = re.search(
        r"(?:url|link|website|site|\u0441\u0441\u044b\u043b\u043a\u0430|\u0430\u0434\u0440\u0435\u0441|\u0434\u043e\u043c\u0435\u043d)\s+(?:na|for|to|\u043d\u0430|\u0434\u043b\u044f)?\s*([^\n\.,;!?]+)",
        goal,
        re.IGNORECASE,
    )
    if url_match:
        return _clean_query(url_match.group(1))
    explicit_match = re.search(r"\b(?:про|about)\b\s+([^\n\.,;!?]+)", goal, re.IGNORECASE)
    if explicit_match:
        return _clean_query(explicit_match.group(1))
    explicit_match = re.search(r"\b(?:о|об)\b\s+([^\n\.,;!?]+)", goal, re.IGNORECASE)
    if explicit_match:
        return _clean_query(explicit_match.group(1))
    patterns = [
        r"(?:find|search for|look for|search|open)\\s+(.+)",
        r"(?:найди|найти|ищи|поиск|искать|открой)\\s+(.+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, goal, re.IGNORECASE)
        if not match:
            continue
        fragment = match.group(1).strip()
        stop = re.split(
            r"\\s+(?:and|then|,|;|\\.|\\?|!|и|затем)\\s+"
            r"(?:add|put|buy|order|checkout|pay|open|go|navigate|click|select|choose|"
            r"\u043f\u043e\u043b\u043e\u0436\u0438|\u0434\u043e\u0431\u0430\u0432\u044c|"
            r"\u043a\u0443\u043f\u0438|\u0437\u0430\u043a\u0430\u0436\u0438|"
            r"\u043e\u0444\u043e\u0440\u043c\u0438|\u043e\u043f\u043b\u0430\u0442\u0438|"
            r"\u043f\u0435\u0440\u0435\u0439\u0434\u0438|\u043e\u0442\u043a\u0440\u043e\u0439)",
            fragment,
            maxsplit=1,
            flags=re.IGNORECASE,
        )
        return _clean_query(stop[0])
    return ""


def _clean_query(value: str) -> str:
    cleaned = re.sub(r"[\"'«»]", "", value)
    cleaned = _strip_site_terms(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _strip_site_terms(text: str) -> str:
    text = re.sub(r"^(?:про|about)\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(
        r"\b(на|в)\s+(википедии|wikipedia|wiki)\b.*$",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\b(википедия|wikipedia|wiki)\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(статья|статью|статьи|article|page)\b", "", text, flags=re.IGNORECASE)
    return text


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


def _compact_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    if not snapshot:
        return {}
    visible_text = snapshot.get("visible_text_summary") or ""
    if isinstance(visible_text, str) and len(visible_text) > 2000:
        visible_text = visible_text[:2000] + "..."
    elements = snapshot.get("interactive_elements") or []
    compact_elements = []
    url = (snapshot.get("url") or "").lower()
    limit = 80 if any(token in url for token in ["mail.", "inbox", "mail/"]) else 35
    for element in elements[:limit]:
        compact_elements.append(
            {
                "id": element.get("id"),
                "role": element.get("role"),
                "name": (element.get("name") or "")[:120],
                "text": (element.get("text") or "")[:120],
                "aria_label": (element.get("aria_label") or "")[:120],
                "bbox": element.get("bbox"),
            }
        )
    compact = {
        "url": snapshot.get("url"),
        "title": snapshot.get("title"),
        "visible_text_summary": visible_text,
        "interactive_elements": compact_elements,
    }
    warnings = snapshot.get("warnings") or []
    if warnings:
        compact["warnings"] = warnings
    popups = snapshot.get("possible_popups") or []
    if popups:
        compact["possible_popups"] = popups[:3]
    return compact


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
        payload = _extract_json(response.content or "")
        if payload:
            tool_name = payload.get("tool")
            args = payload.get("args") or {}
            reason = payload.get("reason") or reason
            if tool_name:
                return ToolCall(name=str(tool_name), arguments=args), reason
        tool_list = [tool["function"]["name"] for tool in tools]
        tool_doc = {
            "instructions": "Respond with JSON only.",
            "format": {"tool": "name", "args": {"key": "value"}, "reason": "short"},
            "tools": tool_list,
        }
        fallback_messages = list(messages)
        fallback_messages.append(
            {"role": "system", "content": f"Tool spec: {json.dumps(tool_doc)}"}
        )
        fallback_response = llm.complete(messages=fallback_messages, tools=None)
        payload = _extract_json(fallback_response.content or "")
        if payload:
            tool_name = payload.get("tool")
            args = payload.get("args") or {}
            reason = payload.get("reason") or (fallback_response.content or reason)
            if tool_name:
                return ToolCall(name=str(tool_name), arguments=args), reason
        return None, fallback_response.content or reason

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
