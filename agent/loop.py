from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from .agents.coordinator import Coordinator
from .agents.extractor import Extractor
from .agents.navigator import Navigator
from .agents.reflector import Reflector
from .agents.utils import build_context, extract_goal_urls, should_enforce_goal_order
from .browser.controller import BrowserController
from .config import Settings
from .llm import create_llm
from .llm.base import MeteredLLM, ToolCall
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
        start_url: Optional[str] = None,
    ) -> None:
        self.goal = goal
        self.settings = settings
        self.emit = emit
        self.browser_only = browser_only
        self.has_browser_action = False
        self.search_engine_url = search_engine_url or settings.search_engine_url
        self.start_url = start_url or ""
        self.goal_urls = extract_goal_urls(goal)
        self.visited_goal_urls: set[str] = set()
        self.goal_url_ordered = should_enforce_goal_order(goal) and len(self.goal_urls) > 1
        self.llm_calls = 0
        self.token_usage = {"prompt": 0, "completion": 0, "total": 0}
        self.next_usage_log = 5000
        self.next_call_log = 10
        self.llm = create_llm(settings)
        self.llm = MeteredLLM(self.llm, self._record_llm_usage)
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
        self.last_access_issue: Optional[str] = None
        self.last_access_url: Optional[str] = None

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

    def provide_user_input(self, text: str) -> None:
        cleaned = (text or "").strip()
        if not cleaned:
            return
        record = StepRecord(
            step=self.step,
            tool="user_input",
            args={"text": cleaned},
            reason="user_reply",
            url=self.last_url or "",
            title=self.last_title or "",
            status="ok",
            error=None,
        )
        self.memory.add_step(record)
        self.memory.facts.append(f"User input: {cleaned}")
        self._emit(
            "log",
            {
                "step": self.step,
                "tool": "user_input",
                "reason": "User reply received.",
                "url": self.last_url,
                "title": self.last_title,
                "status": "ok",
                "output": cleaned[:160],
            },
        )

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
            self._maybe_mark_goal_url(snapshot.get("url") or "")
            if self._maybe_report_access_issue(snapshot):
                return

            forced_call = self._maybe_force_goal_url(snapshot)
            if forced_call:
                if forced_call.name == "ask_user":
                    question = forced_call.arguments.get("question") or "Need your input to continue."
                    self._pause_for_user(question)
                    return
                self._execute_tool(forced_call, "Goal order enforcement.", snapshot)
                if self.done or self.waiting_confirm or self.waiting_user:
                    return
                continue

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

            decision_start = time.perf_counter()
            tool_call, reason = agent.decide(
                self.goal,
                self.memory,
                snapshot,
                self.browser_only,
                self.has_browser_action,
                self.goal_urls,
                list(self.visited_goal_urls),
            )
            decision_ms = int((time.perf_counter() - decision_start) * 1000)
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
                        "duration_ms": decision_ms,
                    },
                )
                if self.error_count > self.settings.max_retries:
                    self._pause_for_user("Unable to choose next action. Please assist.")
                    return
                context = build_context(
                    self.goal,
                    self.memory,
                    snapshot,
                    self.browser_only,
                    self.has_browser_action,
                    self.goal_urls,
                    list(self.visited_goal_urls),
                )
                fallback_call, fallback_reason = self.navigator._fallback_tool(context, snapshot)
                if fallback_call:
                    tool_call, reason = fallback_call, fallback_reason
                else:
                    tool_call, reason = self.reflector.decide(
                        self.goal,
                        self.memory,
                        snapshot,
                        self.browser_only,
                        self.has_browser_action,
                        self.goal_urls,
                        list(self.visited_goal_urls),
                    )
                    if not tool_call:
                        self._pause_for_user("Reflection failed. Please assist.")
                        return

            guarded = self._guard_tool_call(tool_call, snapshot)
            if guarded:
                tool_call, reason = guarded

            loop_reason = self._detect_loop(tool_call, snapshot)
            if loop_reason:
                self._emit(
                    "log",
                    {
                        "step": self.step,
                        "tool": "loop_guard",
                        "reason": loop_reason,
                        "url": snapshot.get("url"),
                        "title": snapshot.get("title"),
                        "status": "warning",
                    },
                )
                self._pause_for_user(loop_reason)
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
        started_at = time.perf_counter()

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

        duration_ms = int((time.perf_counter() - started_at) * 1000)
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
                "duration_ms": duration_ms,
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

    def _maybe_report_access_issue(self, snapshot: Dict[str, Any]) -> bool:
        issue = self._detect_access_issue(snapshot)
        if not issue:
            return False
        url = snapshot.get("url") or ""
        if issue == self.last_access_issue and url == self.last_access_url:
            return False
        self.last_access_issue = issue
        self.last_access_url = url
        self._emit(
            "log",
            {
                "step": self.step,
                "tool": "access",
                "reason": issue,
                "url": snapshot.get("url"),
                "title": snapshot.get("title"),
                "status": "warning",
            },
        )
        self._pause_for_user(issue)
        return True

    @staticmethod
    def _detect_access_issue(snapshot: Dict[str, Any]) -> Optional[str]:
        title = (snapshot.get("title") or "").lower()
        text = (snapshot.get("visible_text_summary") or "").lower()
        corpus = f"{title} {text}"
        patterns = [
            (r"access denied|forbidden|not authorized|permission denied|\\b403\\b", "Access denied or forbidden."),
            (
                r"captcha|verify you are human|are you human|robot check|\\bnot a robot\\b",
                "Captcha or bot check detected.",
            ),
            (
                r"browser or app may not be secure|unsafe browser|"
                r"\u0431\u0440\u0430\u0443\u0437\u0435\u0440 \u0438\u043b\u0438 \u043f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u0435 \u043d\u0435\u0431\u0435\u0437\u043e\u043f\u0430\u0441\u043d",
                "Service blocked this login as unsafe. Use a normal browser login or official API.",
            ),
            (
                r"(your|this) ip address .*blocked|ip address .*blocked|blocked proxy|"
                r"this ip address is currently blocked|your ip address has been blocked|"
                r"\u0432\u0430\u0448 ip-\u0430\u0434\u0440\u0435\u0441 .* \u0437\u0430\u0431\u043b\u043e\u043a\u0438\u0440\u043e\u0432\u0430\u043d|"
                r"\u044d\u0442\u043e\u0442 ip-\u0430\u0434\u0440\u0435\u0441 .* \u0437\u0430\u0431\u043b\u043e\u043a\u0438\u0440\u043e\u0432\u0430\u043d|"
                r"\u0437\u0430\u0431\u043b\u043e\u043a\u0438\u0440\u043e\u0432\u0430\u043d \u043a\u0430\u043a \u043f\u0440\u043e\u043a\u0441\u0438|"
                r"\u0437\u0430\u0431\u043b\u043e\u043a\u0438\u0440\u043e\u0432\u0430\u043d\u043d\u044b\u0439 \u043f\u0440\u043e\u043a\u0441\u0438|"
                r"\u0431\u043b\u043e\u043a\u0438\u0440\u043e\u0432\u043a\u0430 \u0438\u043f-\u0430\u0434\u0440\u0435\u0441\u0430",
                "IP appears blocked by this site (proxy/abuse block). Try a different network or disable VPN/proxy.",
            ),
            (
                r"sign in to continue|log in to continue|login required|authentication required",
                "Login required to continue.",
            ),
            (
                r"\u0432\u043e\u0439\u0434\u0438\u0442\u0435 \u0447\u0442\u043e\u0431\u044b|"
                r"\u043d\u0435\u043e\u0431\u0445\u043e\u0434\u0438\u043c\u043e \u0432\u043e\u0439\u0442\u0438|"
                r"\u0442\u0440\u0435\u0431\u0443\u0435\u0442\u0441\u044f \u0430\u0432\u0442\u043e\u0440\u0438\u0437\u0430\u0446\u0438\u044f|"
                r"\u0430\u0432\u0442\u043e\u0440\u0438\u0437\u0443\u0439\u0442\u0435\u0441\u044c",
                "\u0422\u0440\u0435\u0431\u0443\u0435\u0442\u0441\u044f \u0432\u0445\u043e\u0434 \u0432 \u0430\u043a\u043a\u0430\u0443\u043d\u0442.",
            ),
            (
                r"\u043a\u0430\u043f\u0447\u0430|"
                r"\u043d\u0435 \u0440\u043e\u0431\u043e\u0442|"
                r"\u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0434\u0438\u0442\u0435 \u0447\u0442\u043e \u0432\u044b \u0447\u0435\u043b\u043e\u0432\u0435\u043a",
                "\u041e\u0431\u043d\u0430\u0440\u0443\u0436\u0435\u043d\u0430 \u043a\u0430\u043f\u0447\u0430/\u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0430.",
            ),
            (
                r"2fa|two-factor|verification code|one-time code|sms code|"
                r"\u043a\u043e\u0434 \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0435\u043d\u0438\u044f|"
                r"\u0434\u0432\u0443\u0445\u0444\u0430\u043a\u0442\u043e\u0440",
                "2FA/verification required.",
            ),
        ]
        for pattern, message in patterns:
            if re.search(pattern, corpus):
                return message
        return None

    def _detect_loop(self, tool_call: ToolCall, snapshot: Dict[str, Any]) -> Optional[str]:
        if tool_call.name != "navigate":
            return None
        target = (tool_call.arguments.get("url") or "").strip()
        if not target:
            return None
        target_norm = self._normalize_url(target)
        current_url = (snapshot.get("url") or "").strip()
        if not current_url:
            return None
        recent = list(self.memory.steps)[-3:]
        same_count = 0
        for record in reversed(recent):
            if record.tool != "navigate":
                break
            record_url = (record.url or "").strip()
            if record_url == current_url:
                same_count += 1
            else:
                break
        if same_count >= 2 and current_url == target_norm:
            return "Stuck repeating navigation to the same URL."
        return None

    @staticmethod
    def _normalize_url(url: str) -> str:
        url = (url or "").strip()
        if not url:
            return ""
        if url.startswith(("http://", "https://")):
            return url
        if url.startswith("www."):
            return f"https://{url}"
        if re.match(r"^[a-z0-9-]+(\\.[a-z0-9-]+)+$", url, re.IGNORECASE):
            return f"https://{url}"
        return url

    def _maybe_mark_goal_url(self, url: str) -> None:
        if not url or not self.goal_urls:
            return
        if not self._has_non_nav_action_on_url(url):
            return
        for goal_url in self.goal_urls:
            if self._url_matches_goal(url, goal_url):
                if goal_url not in self.visited_goal_urls:
                    self.visited_goal_urls.add(goal_url)
                return

    def _has_non_nav_action_on_url(self, url: str) -> bool:
        target = self._normalize_match_url(url)
        for record in self.memory.steps:
            if self._normalize_match_url(record.url) != target:
                continue
            if record.tool not in {"navigate", "back", "forward"}:
                return True
        return False

    @staticmethod
    def _normalize_match_url(url: str) -> str:
        if not url:
            return ""
        stripped = re.split(r"[?#]", url)[0].strip().lower()
        return stripped.rstrip("/")

    def _url_matches_goal(self, url: str, goal_url: str) -> bool:
        if not url or not goal_url:
            return False
        return self._normalize_match_url(url).startswith(self._normalize_match_url(goal_url))

    def _maybe_force_goal_url(self, snapshot: Dict[str, Any]) -> Optional[ToolCall]:
        if not self.goal_url_ordered or not self.goal_urls:
            return None
        next_goal_url = ""
        for url in self.goal_urls:
            if url not in self.visited_goal_urls:
                next_goal_url = url
                break
        if not next_goal_url:
            return None
        current_url = snapshot.get("url") or ""
        if self._url_matches_goal(current_url, next_goal_url):
            return None
        last_record = self.memory.steps[-1] if self.memory.steps else None
        if last_record and last_record.tool == "navigate":
            last_url = str((last_record.args or {}).get("url") or "")
            if self._url_matches_goal(last_url, next_goal_url) and self.no_progress_steps >= self.settings.no_progress_limit:
                return ToolCall(
                    name="ask_user",
                    arguments={"question": "Unable to reach the required URL. Please check access or provide guidance."},
                )
        return ToolCall(name="navigate", arguments={"url": next_goal_url})

    def _bootstrap_browser(self) -> None:
        url = self.start_url or self._bootstrap_url(self.goal)
        logger.info("Bootstrap navigate url=%s", url)
        status = "ok"
        error = None
        snapshot: Dict[str, Any] = {}
        self.step += 1
        started_at = time.perf_counter()
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

        duration_ms = int((time.perf_counter() - started_at) * 1000)
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
                "duration_ms": duration_ms,
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
        question = self._format_user_question(question)
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

    def _record_llm_usage(self, response: Any) -> None:
        self.llm_calls += 1
        raw = getattr(response, "raw", None) or {}
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0

        usage = raw.get("usage") if isinstance(raw, dict) else None
        if isinstance(usage, dict):
            prompt_tokens = usage.get("prompt_tokens", 0) or 0
            completion_tokens = usage.get("completion_tokens", 0) or 0
            total_tokens = usage.get("total_tokens", 0) or 0
            if not total_tokens:
                total_tokens = prompt_tokens + completion_tokens

        meta = raw.get("usageMetadata") if isinstance(raw, dict) else None
        if isinstance(meta, dict):
            prompt_tokens = meta.get("promptTokenCount", prompt_tokens) or prompt_tokens
            completion_tokens = meta.get("candidatesTokenCount", completion_tokens) or completion_tokens
            total_tokens = meta.get("totalTokenCount", total_tokens) or total_tokens
            if not total_tokens:
                total_tokens = prompt_tokens + completion_tokens

        if isinstance(usage, dict) and "input_tokens" in usage:
            prompt_tokens = usage.get("input_tokens", prompt_tokens) or prompt_tokens
            completion_tokens = usage.get("output_tokens", completion_tokens) or completion_tokens
            total_tokens = usage.get("total_tokens", total_tokens) or total_tokens
            if not total_tokens:
                total_tokens = prompt_tokens + completion_tokens

        if total_tokens:
            self.token_usage["prompt"] += int(prompt_tokens)
            self.token_usage["completion"] += int(completion_tokens)
            self.token_usage["total"] += int(total_tokens)
            if self.token_usage["total"] >= self.next_usage_log:
                self._emit(
                    "log",
                    {
                        "step": self.step,
                        "tool": "tokens",
                        "reason": f"LLM tokens used ~{self.token_usage['total']}",
                        "url": self.last_url,
                        "title": self.last_title,
                        "status": "info",
                    },
                )
                self.next_usage_log += 5000
        else:
            if self.llm_calls >= self.next_call_log:
                self._emit(
                    "log",
                    {
                        "step": self.step,
                        "tool": "tokens",
                        "reason": f"LLM calls: {self.llm_calls}",
                        "url": self.last_url,
                        "title": self.last_title,
                        "status": "info",
                    },
                )
                self.next_call_log += 10

    def _format_user_question(self, question: str) -> str:
        base = (question or "").strip() or "Need your input to continue."
        has_options = re.search(r"\b1[\).\]]", base) is not None
        page_info = self._current_page_info()
        if page_info and page_info not in base:
            base = f"{base}\n\n{page_info}"
        if self._is_russian(base) or self._is_russian(self.goal):
            if not has_options:
                base = (
                    f"{base}\n\n\u0412\u0430\u0440\u0438\u0430\u043d\u0442\u044b:\n"
                    "1) \u041f\u0440\u043e\u0434\u043e\u043b\u0436\u0438\u0442\u044c\n"
                    "2) \u041e\u0441\u0442\u0430\u043d\u043e\u0432\u0438\u0442\u044c \u0437\u0430\u0434\u0430\u0447\u0443"
                )
            instruction = (
                "\u041e\u0442\u0432\u0435\u0442\u044c\u0442\u0435 \u0432 \u043f\u043e\u043b\u0435 "
                "\"\u041e\u0442\u0432\u0435\u0442 \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044e\" "
                "\u043d\u0438\u0436\u0435 \u0438 \u043d\u0430\u0436\u043c\u0438\u0442\u0435 "
                "\"Confirm / Continue\"."
            )
        else:
            if not has_options:
                base = (
                    f"{base}\n\nOptions:\n"
                    "1) Continue\n"
                    "2) Stop the task"
                )
            instruction = (
                "Type your reply in the \"User reply\" field below and click "
                "\"Confirm / Continue\"."
            )
        if instruction in base:
            return base
        return f"{base}\n\n{instruction}"

    @staticmethod
    def _is_russian(text: str) -> bool:
        return re.search(r"[\u0400-\u04FF]", text or "") is not None

    def _current_page_info(self) -> str:
        if not self.last_url:
            return ""
        title = self.last_title or ""
        return f"Current page: {title} ({self.last_url})" if title else f"Current page: {self.last_url}"

    def _guard_tool_call(
        self,
        tool_call: ToolCall,
        snapshot: Dict[str, Any],
    ) -> Optional[tuple[ToolCall, str]]:
        current_url = (snapshot.get("url") or "").strip()
        if self.no_progress_steps >= self.settings.no_progress_limit and tool_call.name in {"scroll", "click", "type"}:
            last_record = self.memory.steps[-1] if self.memory.steps else None
            if (
                last_record
                and last_record.tool == tool_call.name
                and (last_record.args or {}) == (tool_call.arguments or {})
            ):
                return (
                    ToolCall(
                        name="ask_user",
                        arguments={"question": "Stuck repeating the same action. Please advise."},
                    ),
                    "Progress guard: repeated identical action.",
                )
            context = build_context(
                self.goal,
                self.memory,
                snapshot,
                self.browser_only,
                self.has_browser_action,
                self.goal_urls,
                list(self.visited_goal_urls),
            )
            fallback_call, fallback_reason = self.navigator._fallback_tool(context, snapshot)
            if fallback_call:
                if (
                    last_record
                    and last_record.tool == fallback_call.name
                    and (last_record.args or {}) == (fallback_call.arguments or {})
                ):
                    return (
                        ToolCall(
                            name="ask_user",
                            arguments={"question": "Still stuck repeating actions. Please advise."},
                        ),
                        "Progress guard: fallback would repeat the same action.",
                    )
                self._emit(
                    "log",
                    {
                        "step": self.step,
                        "tool": "guard",
                        "reason": "No progress detected; switching strategy.",
                        "url": snapshot.get("url"),
                        "title": snapshot.get("title"),
                        "status": "warning",
                    },
                )
                return fallback_call, fallback_reason
            return (
                ToolCall(name="ask_user", arguments={"question": "No visible progress. Please advise."}),
                "Progress guard: need user guidance.",
            )
        if tool_call.name == "click" and self._is_search_home(current_url):
            context = build_context(
                self.goal,
                self.memory,
                snapshot,
                self.browser_only,
                self.has_browser_action,
                self.goal_urls,
                list(self.visited_goal_urls),
            )
            fallback_call, fallback_reason = self.navigator._fallback_tool(context, snapshot)
            if fallback_call and fallback_call.name == "type":
                self._emit(
                    "log",
                    {
                        "step": self.step,
                        "tool": "guard",
                        "reason": "Search home detected; typing query instead of clicking.",
                        "url": snapshot.get("url"),
                        "title": snapshot.get("title"),
                        "status": "warning",
                    },
                )
                return fallback_call, fallback_reason
        if tool_call.name not in {"navigate", "click"}:
            return None
        goal_text = (self.goal or "").lower()
        if any(token in goal_text for token in ["about", "privacy", "terms", "cookies", "о нас", "политик"]):
            return None

        target_text = ""
        if tool_call.name == "navigate":
            target_text = str(tool_call.arguments.get("url") or "")
        else:
            try:
                element = self.controller.resolve_element(
                    element_id=tool_call.arguments.get("element_id"),
                    strategy=tool_call.arguments.get("click_strategy"),
                )
                target_text = " ".join(
                    [
                        element.get("name") or "",
                        element.get("aria_label") or "",
                        element.get("text") or "",
                    ]
                )
            except Exception:
                target_text = ""

        if not target_text:
            return None
        target_text = target_text.lower()
        if re.search(r"\babout\b|privacy|terms|cookies|about us|\u043e \u043d\u0430\u0441|\u043f\u043e\u043b\u0438\u0442\u0438\u043a", target_text):
            context = build_context(
                self.goal,
                self.memory,
                snapshot,
                self.browser_only,
                self.has_browser_action,
                self.goal_urls,
                list(self.visited_goal_urls),
            )
            fallback_call, fallback_reason = self.navigator._fallback_tool(context, snapshot)
            if fallback_call:
                self._emit(
                    "log",
                    {
                        "step": self.step,
                        "tool": "guard",
                        "reason": "Blocked non-task navigation; using fallback.",
                        "url": snapshot.get("url"),
                        "title": snapshot.get("title"),
                        "status": "warning",
                    },
                )
                return fallback_call, fallback_reason
        return None

    @staticmethod
    def _is_search_home(url: str) -> bool:
        if not url:
            return False
        lowered = url.lower()
        search_hosts = ("duckduckgo.com", "google.com", "bing.com", "yandex.")
        if not any(host in lowered for host in search_hosts):
            return False
        return "q=" not in lowered and "search" not in lowered and "query" not in lowered
