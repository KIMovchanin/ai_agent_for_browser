from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from .agents.coordinator import Coordinator
from .agents.extractor import Extractor
from .agents.navigator import Navigator
from .agents.reflector import Reflector
from .browser.controller import BrowserController
from .config import Settings
from .llm import create_llm
from .llm.base import ToolCall
from .memory.state import MemoryState, StepRecord
from .memory.summarizer import Summarizer
from .tools.actions import ToolExecutor
from .tools.security import SecurityPolicy

logger = logging.getLogger("agent.loop")


@dataclass
class PendingAction:
    tool_call: ToolCall
    reason: str
    snapshot: Dict[str, Any]


class AgentSession:
    def __init__(
        self,
        goal: str,
        settings: Settings,
        emit: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        browser_only: bool = True,
        search_engine_url: Optional[str] = None,
        create_window: bool = False,
        controller: Optional[BrowserController] = None,
        close_controller: bool = True,
    ) -> None:
        self.goal = goal
        self.settings = settings
        self.emit = emit
        self.browser_only = browser_only
        self.has_browser_action = False
        self.search_engine_url = search_engine_url or settings.search_engine_url
        self.llm = create_llm(settings)
        if controller:
            self.controller = controller
            self.close_controller = close_controller
            self.controller.select_page(create_window)
        else:
            self.controller = BrowserController(settings, start_new_window=create_window)
            self.close_controller = True
        self.memory = MemoryState(max_steps=settings.max_steps)
        self.summarizer = Summarizer(self.llm)

        self.navigator = Navigator(self.llm)
        self.extractor = Extractor(self.llm)
        self.reflector = Reflector(self.llm)
        self.coordinator = Coordinator(self.navigator, self.extractor, self.reflector)
        self.tool_executor = ToolExecutor(self.controller, self.extractor, self.settings)
        self.security = SecurityPolicy()

        self.step = 0
        self.error_count = 0
        self.no_progress_steps = 0
        self.last_url: Optional[str] = None
        self.last_title: Optional[str] = None

        self.pending_action: Optional[PendingAction] = None
        self.waiting_confirm = False
        self.waiting_user = False
        self.confirmed = False
        self.user_question: Optional[str] = None

        self.done = False
        self.result: Optional[str] = None
        self.stop_requested = False

    def _emit(self, event_type: str, data: Dict[str, Any]) -> None:
        if self.emit:
            self.emit(event_type, data)

    def request_stop(self) -> None:
        self.stop_requested = True

    def confirm(self) -> None:
        self.confirmed = True
        self.waiting_confirm = False
        self.waiting_user = False

    def run(self) -> None:
        if self.done or self.stop_requested:
            return

        self._emit("status", {"status": "running"})

        if self.pending_action and self.confirmed:
            self._execute_tool(self.pending_action.tool_call, self.pending_action.reason, self.pending_action.snapshot)
            self.pending_action = None
            self.confirmed = False
        elif self.confirmed:
            self.confirmed = False

        if self.waiting_confirm or self.waiting_user:
            return

        if self.browser_only and not self.has_browser_action and self.step == 0 and not self.pending_action:
            self._bootstrap_browser()
            if self.waiting_user or self.waiting_confirm or self.done:
                return

        while self.step < self.settings.max_steps:
            if self.stop_requested:
                self._emit("status", {"status": "stopped"})
                self._close()
                return

            snapshot = self.controller.snapshot()
            self._update_progress(snapshot)

            if self.no_progress_steps >= self.settings.no_progress_limit:
                agent = self.reflector
            else:
                agent = self.coordinator.select_agent(
                    self.goal,
                    self.memory,
                    snapshot,
                    self.error_count,
                    self.no_progress_steps,
                )

            tool_call, reason = agent.decide(
                self.goal,
                self.memory,
                snapshot,
                self.browser_only,
                self.has_browser_action,
            )
            if not tool_call:
                self.error_count += 1
                self._emit(
                    "log",
                    {
                        "step": self.step,
                        "tool": "none",
                        "reason": reason or "No tool call",
                        "url": snapshot.get("url"),
                        "title": snapshot.get("title"),
                        "status": "error",
                    },
                )
                if self.error_count > self.settings.max_retries:
                    self._pause_for_user("Unable to choose next action. Please assist.")
                    return
                tool_call, reason = self.reflector.decide(
                    self.goal,
                    self.memory,
                    snapshot,
                    self.browser_only,
                    self.has_browser_action,
                )
                if not tool_call:
                    self._pause_for_user("Reflection failed. Please assist.")
                    return

            if tool_call.name == "ask_user":
                question = tool_call.arguments.get("question") or "Need your input to continue."
                self._pause_for_user(question)
                return
            if tool_call.name == "finish":
                result = tool_call.arguments.get("result") or "Task completed."
                self._finish(result)
                return
            if tool_call.name == "stop_task":
                self.request_stop()
                self._emit("status", {"status": "stopped"})
                self._close()
                return

            needs_confirm, target_text = self.security.needs_confirmation(
                tool_call.name, tool_call.arguments, snapshot
            )
            if needs_confirm:
                summary = target_text or tool_call.name
                self.pending_action = PendingAction(tool_call=tool_call, reason=reason, snapshot=snapshot)
                self.waiting_confirm = True
                self._emit(
                    "needs_confirmation",
                    {
                        "step": self.step,
                        "tool": tool_call.name,
                        "summary": summary,
                        "reason": reason,
                        "args": tool_call.arguments,
                    },
                )
                return

            self._execute_tool(tool_call, reason, snapshot)
            if self.done or self.waiting_confirm or self.waiting_user:
                return

        self._finish("Max steps reached without completion.")

    def _execute_tool(self, tool_call: ToolCall, reason: str, snapshot: Dict[str, Any]) -> None:
        self.step += 1
        status = "ok"
        error = None
        result_summary: Optional[str] = None
        output: Optional[Any] = None

        try:
            tool_result = self.tool_executor.execute(tool_call.name, tool_call.arguments or {})
            output = tool_result.output
            self.error_count = 0
            if tool_call.name in {"navigate", "click", "type", "scroll", "back", "forward"}:
                self.has_browser_action = True
            if tool_call.name == "extract" and isinstance(output, dict):
                packed = json.dumps(output, ensure_ascii=True)[:500]
                self.memory.facts.append(packed)
            if tool_call.name == "snapshot":
                snapshot = output if isinstance(output, dict) else snapshot
        except Exception as exc:  # pylint: disable=broad-except
            status = "error"
            error = str(exc)
            self.error_count += 1
            try:
                self.tool_executor.execute("take_screenshot", {"label": "error"})
            except Exception:
                pass

        if output is not None:
            try:
                result_summary = json.dumps(output, ensure_ascii=True)[:300]
            except Exception:
                result_summary = str(output)[:300]

        record = StepRecord(
            step=self.step,
            tool=tool_call.name,
            args=tool_call.arguments or {},
            reason=reason,
            url=snapshot.get("url", ""),
            title=snapshot.get("title", ""),
            status=status,
            error=error,
        )
        self.memory.add_step(record)
        self.summarizer.maybe_summarize(self.memory)

        self._emit(
            "log",
            {
                "step": self.step,
                "tool": tool_call.name,
                "reason": reason,
                "url": snapshot.get("url"),
                "title": snapshot.get("title"),
                "status": status,
                "error": error,
                "output": result_summary,
            },
        )

        if status == "error" and self.error_count > self.settings.max_retries:
            self._pause_for_user("Action failed repeatedly. Please assist.")
        if status == "error":
            logger.warning("Tool error tool=%s error=%s", tool_call.name, error)

    def _update_progress(self, snapshot: Dict[str, Any]) -> None:
        url = snapshot.get("url")
        title = snapshot.get("title")
        if url == self.last_url and title == self.last_title:
            self.no_progress_steps += 1
        else:
            self.no_progress_steps = 0
        self.last_url = url
        self.last_title = title

    def _bootstrap_browser(self) -> None:
        url = self._bootstrap_url(self.goal)
        logger.info("Bootstrap navigate url=%s", url)
        status = "ok"
        error = None
        snapshot: Dict[str, Any] = {}
        self.step += 1
        try:
            self.tool_executor.execute("navigate", {"url": url})
            self.has_browser_action = True
            snapshot = self.controller.snapshot()
        except Exception as exc:  # pylint: disable=broad-except
            try:
                self.controller.select_page(start_new_window=True)
                self.tool_executor.execute("navigate", {"url": url})
                self.has_browser_action = True
                snapshot = self.controller.snapshot()
            except Exception as retry_exc:  # pylint: disable=broad-except
                status = "error"
                error = f"{exc} | retry: {retry_exc}"
                self.error_count += 1
                try:
                    snapshot = self.controller.snapshot()
                except Exception:
                    snapshot = {}
                logger.warning("Bootstrap navigate failed error=%s", error)

        record = StepRecord(
            step=self.step,
            tool="navigate",
            args={"url": url},
            reason="bootstrap",
            url=snapshot.get("url", ""),
            title=snapshot.get("title", ""),
            status=status,
            error=error,
        )
        self.memory.add_step(record)
        self.summarizer.maybe_summarize(self.memory)

        self._emit(
            "log",
            {
                "step": self.step,
                "tool": "navigate",
                "reason": "bootstrap",
                "url": snapshot.get("url"),
                "title": snapshot.get("title"),
                "status": status,
                "error": error,
                "output": json.dumps({"url": url}),
            },
        )

        if status == "error" and self.error_count > self.settings.max_retries:
            self._pause_for_user("Failed to navigate. Please provide a URL or guidance.")

    def _bootstrap_url(self, prompt: str) -> str:
        url_match = re.search(r"https?://\\S+", prompt)
        if url_match:
            return url_match.group(0).rstrip(").,;")
        www_match = re.search(r"\\bwww\\.[^\\s]+", prompt)
        if www_match:
            return f"https://{www_match.group(0).rstrip(').,;')}"
        domain_match = re.search(r"\\b([a-z0-9-]+\\.)+[a-z]{2,10}\\b", prompt, re.IGNORECASE)
        if domain_match:
            return f"https://{domain_match.group(0)}"
        return self.search_engine_url or "https://www.google.com"

    def _pause_for_user(self, question: str) -> None:
        self.waiting_user = True
        self.user_question = question
        logger.info("Pause for user question=%s", question)
        self._emit("needs_user_input", {"question": question})

    def _finish(self, result: str) -> None:
        self.done = True
        self.result = result
        logger.info("Finish result=%s", result)
        self._emit("result", {"result": result})
        self._emit("status", {"status": "done"})
        self._close()

    def _close(self) -> None:
        if not self.close_controller:
            return
        try:
            self.controller.close()
        except Exception:
            pass
