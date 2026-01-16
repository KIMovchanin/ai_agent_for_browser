from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from ..browser.controller import BrowserController
from ..config import Settings
from ..agents.extractor import Extractor


@dataclass
class ToolResult:
    name: str
    output: Any = None


def _safe_label(label: Optional[str]) -> str:
    if not label:
        return ""
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", label)
    return safe.strip("_")


def _artifact_path(base: Path, prefix: str, label: Optional[str], ext: str) -> Path:
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_label = _safe_label(label)
    parts = [prefix, stamp]
    if safe_label:
        parts.append(safe_label)
    filename = "_".join(parts) + ext
    return base / filename


class ToolExecutor:
    def __init__(self, controller: BrowserController, extractor: Extractor, settings: Settings) -> None:
        self.controller = controller
        self.extractor = extractor
        self.settings = settings

    @staticmethod
    def _looks_like_search_field(element: Dict[str, Any]) -> bool:
        role = (element.get("role") or "").lower()
        if "search" in role:
            return True
        haystack = " ".join(
            [
                element.get("name") or "",
                element.get("aria_label") or "",
                element.get("text") or "",
            ]
        ).lower()
        search_markers = [
            "search",
            "find",
            "query",
            "\u043f\u043e\u0438\u0441\u043a",
            "\u043d\u0430\u0439\u0442\u0438",
            "\u043f\u043e\u0438\u0441\u043a\u043e\u0432",
        ]
        exclude_markers = [
            "email",
            "e-mail",
            "password",
            "phone",
            "login",
            "username",
            "\u043f\u0430\u0440\u043e\u043b\u044c",
            "\u043f\u043e\u0447\u0442\u0430",
            "\u0442\u0435\u043b\u0435\u0444\u043e\u043d",
            "\u043b\u043e\u0433\u0438\u043d",
            "\u043a\u043e\u0434",
            "2fa",
            "otp",
        ]
        if any(marker in haystack for marker in exclude_markers):
            return False
        return any(marker in haystack for marker in search_markers)

    def execute(self, name: str, args: Dict[str, Any]) -> ToolResult:
        if name == "navigate":
            url = args.get("url", "")
            self.controller.navigate(url)
            return ToolResult(name=name, output={"url": url})
        if name == "snapshot":
            snapshot = self.controller.snapshot()
            return ToolResult(name=name, output=snapshot)
        if name == "click":
            element = self.controller.resolve_element(
                element_id=args.get("element_id"),
                strategy=args.get("click_strategy"),
            )
            self.controller.click(element)
            return ToolResult(name=name, output={"element_id": element.get("id")})
        if name == "type":
            element = self.controller.resolve_element(
                element_id=args.get("element_id"),
                strategy=args.get("click_strategy"),
            )
            text = args.get("text", "")
            press_enter_arg = args.get("press_enter")
            if press_enter_arg is None and self._looks_like_search_field(element):
                press_enter = True
            else:
                press_enter = bool(press_enter_arg)
            self.controller.type(element, text, press_enter=press_enter)
            return ToolResult(name=name, output={"element_id": element.get("id")})
        if name == "scroll":
            direction = args.get("direction", "down")
            amount = int(args.get("amount", 400))
            self.controller.scroll(direction, amount)
            return ToolResult(name=name, output={"direction": direction, "amount": amount})
        if name == "wait":
            ms = int(args.get("ms", 1000))
            self.controller.wait(ms)
            return ToolResult(name=name, output={"ms": ms})
        if name == "wait_for_network_idle":
            self.controller.wait_for_network_idle()
            return ToolResult(name=name, output={"status": "idle"})
        if name == "back":
            self.controller.back()
            return ToolResult(name=name, output={"status": "ok"})
        if name == "forward":
            self.controller.forward()
            return ToolResult(name=name, output={"status": "ok"})
        if name == "extract":
            schema = args.get("schema") or "Return JSON with items and notes."
            snapshot = self.controller.last_snapshot or self.controller.snapshot()
            data = self.extractor.extract_with_schema(schema, snapshot)
            return ToolResult(name=name, output=data)
        if name == "take_screenshot":
            label = args.get("label")
            path = _artifact_path(self.settings.screenshot_dir, "shot", label, ".png")
            self.controller.take_screenshot(str(path))
            return ToolResult(name=name, output={"path": str(path)})
        if name == "save_trace":
            label = args.get("label")
            path = _artifact_path(self.settings.trace_dir, "trace", label, ".zip")
            self.controller.save_trace(str(path))
            return ToolResult(name=name, output={"path": str(path)})

        raise ValueError(f"Unknown tool: {name}")
