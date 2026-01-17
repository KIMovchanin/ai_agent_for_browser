from __future__ import annotations

import logging
import re
from urllib.parse import quote
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field, replace
from pathlib import Path
from queue import Queue
from typing import Any, Callable, Deque, Dict, Optional

from agent.browser.controller import BrowserController
from agent.config import Settings
from agent.llm import create_llm
from agent.llm.base import LLMError
from agent.loop import AgentSession
from agent.agents.utils import extract_goal_query


@dataclass
class Task:
    task_id: str
    prompt: str
    status: str
    session: Optional[AgentSession]
    events: Queue
    mode: str = "agent"
    browser_only: bool = True
    search_engine: str = "google"
    model: Optional[str] = None
    provider: Optional[str] = None
    safe_mode: bool = True
    result: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    event_history: Deque[Dict[str, Any]] = field(default_factory=lambda: deque(maxlen=200))


class TaskManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.tasks: Dict[str, Task] = {}
        self.lock = threading.Lock()
        self.worker_queue: Queue[str] = Queue()
        self.worker_thread: Optional[threading.Thread] = None
        self.worker_controller: Optional[BrowserController] = None
        self.worker_profile_dir: Optional[Path] = None
        self.logger = logging.getLogger("app.task_manager")

    def create_task(
        self,
        prompt: str,
        browser_only: bool = True,
        search_engine: Optional[str] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        safe_mode: bool = True,
    ) -> Task:
        with self.lock:
            if any(
                task.status in {"queued", "running", "waiting_confirm", "waiting_user"}
                for task in self.tasks.values()
            ):
                raise RuntimeError("Only one active task is supported with a shared browser profile.")
            task_id = uuid.uuid4().hex
            mode = "agent"
            if not browser_only and self._force_direct(prompt):
                mode = "direct"
            elif not browser_only and not self._is_browser_task(prompt):
                mode = "direct"
            self.logger.info(
                "Create task id=%s mode=%s browser_only=%s search_engine=%s provider=%s model=%s safe_mode=%s prompt=%s",
                task_id,
                mode,
                browser_only,
                search_engine or "default",
                provider or "-",
                model or "-",
                safe_mode,
                self._compact(prompt),
            )

            events: Queue = Queue()
            task = Task(
                task_id=task_id,
                prompt=prompt,
                status="queued",
                session=None,
                events=events,
                mode=mode,
                browser_only=browser_only,
                search_engine=(search_engine or "google"),
                model=model,
                provider=provider,
                safe_mode=safe_mode,
            )
            self.tasks[task_id] = task

        self._emit(task, "status", {"status": task.status})
        self._enqueue(task)
        return task

    def get_task(self, task_id: str) -> Task:
        task = self.tasks.get(task_id)
        if not task:
            raise KeyError("Task not found")
        return task

    def confirm_task(self, task_id: str, response: Optional[str] = None) -> Task:
        task = self.get_task(task_id)
        if task.session:
            self.logger.info("Confirm task id=%s status=%s", task.task_id, task.status)
            if response:
                task.session.provide_user_input(response)
            task.session.confirm()
            self._enqueue(task)
        return task

    def stop_task(self, task_id: str) -> Task:
        task = self.get_task(task_id)
        if task.session:
            self.logger.info("Stop task id=%s status=%s", task.task_id, task.status)
            task.session.request_stop()
            self._enqueue(task)
        else:
            task.status = "stopped"
            self._emit(task, "status", {"status": task.status})
        return task

    def _ensure_worker(self) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            return
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()
        self.logger.info("Worker thread started")

    def _enqueue(self, task: Task) -> None:
        self._ensure_worker()
        self.worker_queue.put(task.task_id)

    def _worker_loop(self) -> None:
        while True:
            task_id = self.worker_queue.get()
            task = self.tasks.get(task_id)
            if task:
                self._process_task(task)
            self.worker_queue.task_done()

    def _process_task(self, task: Task) -> None:
        try:
            task.status = "running"
            task.updated_at = time.time()
            self.logger.info(
                "Task start id=%s mode=%s browser_only=%s search_engine=%s provider=%s model=%s safe_mode=%s",
                task.task_id,
                task.mode,
                task.browser_only,
                task.search_engine,
                task.provider or "-",
                task.model or "-",
                task.safe_mode,
            )
            if task.mode == "direct":
                self._run_direct(task)
            elif task.mode == "agent":
                if not task.session:
                    try:
                        search_url = self._resolve_search_engine(task.search_engine)
                        start_url = self._extract_start_url(task.prompt)
                        settings = self._settings_for_task(task)
                        controller = self._get_worker_controller(settings)
                        task.session = AgentSession(
                            goal=task.prompt,
                            settings=settings,
                            emit=None,
                            browser_only=task.browser_only,
                            search_engine_url=search_url,
                            create_window=False,
                            controller=controller,
                            close_controller=False,
                            start_url=start_url,
                        )
                        task.session.emit = self._build_emitter(task)
                    except (LLMError, ValueError) as exc:
                        task.status = "error"
                        self._emit(task, "error", {"error": str(exc)})
                        self._emit(task, "status", {"status": task.status})
                        return
                task.session.run()
                task.updated_at = time.time()

                if task.session.done:
                    task.status = "done"
                    task.result = task.session.result
                elif task.session.waiting_confirm:
                    task.status = "waiting_confirm"
                elif task.session.waiting_user:
                    task.status = "waiting_user"
                elif task.session.stop_requested:
                    task.status = "stopped"
                else:
                    task.status = "running"
            else:
                task.status = "error"
                self._emit(task, "error", {"error": "Missing agent session."})
        except Exception as exc:  # pylint: disable=broad-except
            task.status = "error"
            self._emit(task, "error", {"error": str(exc)})

        self._emit(task, "status", {"status": task.status})

    def _run_direct(self, task: Task) -> None:
        try:
            llm = create_llm(self._settings_for_task(task))
            reason = "Browser-only disabled and task is not explicit."
            self.logger.info("Direct mode id=%s reason=%s", task.task_id, reason)
            response = llm.complete(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Answer the user directly without browser actions. "
                            "Be concise and factual. If unsure, say so."
                        ),
                    },
                    {"role": "user", "content": task.prompt},
                ],
                tools=None,
            )
            text = (response.content or "").strip()
            task.result = text
            task.status = "done"
            self._emit(
                task,
                "log",
                {"step": 1, "tool": "direct_answer", "reason": reason, "status": "ok"},
            )
            self._emit(task, "result", {"result": text})
        except LLMError as exc:
            task.status = "error"
            self._emit(task, "error", {"error": str(exc)})

    @staticmethod
    def _force_direct(prompt: str) -> bool:
        text = prompt.lower()
        markers = [
            "failed to start",
            "event stream error",
            "traceback",
            "stack trace",
            "exception",
            "error:",
            "\u043e\u0448\u0438\u0431\u043a",
            "\u0438\u0441\u043a\u043b\u044e\u0447\u0435\u043d",
            "\u0442\u0440\u0435\u0439\u0441\u0431\u0435\u043a",
            "\u0441\u0442\u0435\u043a\u0442\u0440\u0435\u0439\u0441",
            "\u0447\u0442\u043e \u0437\u0430 \u043e\u0448\u0438\u0431\u043a",
            "\u043f\u043e\u0447\u0435\u043c\u0443 \u043e\u0448\u0438\u0431\u043a",
            "\u043e\u0431\u044a\u044f\u0441\u043d\u0438 \u043e\u0448\u0438\u0431\u043a",
            "\u043d\u0435 \u043e\u0442\u043a\u0440\u044b\u0432\u0430\u0439",
            "\u043d\u0435 \u043e\u0442\u043a\u0440\u044b\u0432\u0430\u0439 \u043e\u043a\u043d\u0430",
            "\u043d\u0435 \u043e\u0442\u043a\u0440\u044b\u0432\u0430\u0439 \u0431\u0440\u0430\u0443\u0437\u0435\u0440",
            "\u0431\u0435\u0437 \u0431\u0440\u0430\u0443\u0437\u0435\u0440",
            "\u0431\u0435\u0437 \u043e\u043a\u043d",
            "no browser",
            "without browser",
            "do not open",
            "don't open",
        ]
        return any(marker in text for marker in markers)

    @staticmethod
    def _is_browser_task(prompt: str) -> bool:
        text = prompt.lower()
        if re.search(r"https?://|www\\.", text):
            return True
        if re.search(r"\\b([a-z0-9-]+\\.)+[a-z]{2,10}\\b", text, re.IGNORECASE):
            return True
        actions = [
            "open",
            "go to",
            "navigate",
            "search",
            "find",
            "click",
            "login",
            "log in",
            "sign in",
            "register",
            "checkout",
            "buy",
            "order",
            "pay",
            "submit",
            "fill",
            "apply",
            "respond",
            "delete",
            "remove",
            "download",
            "upload",
            "book",
            "reserve",
            "\u043e\u0442\u043a\u0440\u043e\u0439",
            "\u043f\u0435\u0440\u0435\u0439\u0434\u0438",
            "\u0437\u0430\u0439\u0434\u0438",
            "\u043d\u0430\u0439\u0434\u0438",
            "\u043f\u043e\u0438\u0441\u043a",
            "\u043d\u0430\u0436\u043c\u0438",
            "\u043a\u043b\u0438\u043a\u043d\u0438",
            "\u0432\u0432\u0435\u0434\u0438",
            "\u0437\u0430\u043f\u043e\u043b\u043d\u0438",
            "\u0443\u0434\u0430\u043b\u0438",
            "\u043a\u0443\u043f\u0438\u0442\u044c",
            "\u0437\u0430\u043a\u0430\u0436",
            "\u043e\u043f\u043b\u0430\u0442",
            "\u043e\u0442\u043f\u0440\u0430\u0432",
            "\u043e\u0442\u043a\u043b\u0438\u043a",
            "\u0441\u043a\u0430\u0447",
            "\u0437\u0430\u0433\u0440\u0443\u0437",
        ]
        return any(token in text for token in actions)

    def _build_emitter(self, task: Task) -> Callable[[str, Dict[str, Any]], None]:
        def emit(event_type: str, data: Dict[str, Any]) -> None:
            self._emit(task, event_type, data)

        return emit

    def _emit(self, task: Task, event_type: str, data: Dict[str, Any]) -> None:
        event = {
            "type": event_type,
            "data": data,
            "timestamp": time.time(),
        }
        task.events.put(event)
        task.event_history.append(event)
        self._log_event(task, event_type, data)

    def _log_event(self, task: Task, event_type: str, data: Dict[str, Any]) -> None:
        if event_type == "log":
            self.logger.info(
                "Event log id=%s step=%s tool=%s status=%s reason=%s url=%s title=%s error=%s",
                task.task_id,
                data.get("step"),
                data.get("tool"),
                data.get("status"),
                self._compact(data.get("reason")),
                self._compact(data.get("url")),
                self._compact(data.get("title")),
                self._compact(data.get("error")),
            )
            return
        if event_type == "status":
            self.logger.info("Event status id=%s status=%s", task.task_id, data.get("status"))
            return
        if event_type == "needs_confirmation":
            self.logger.info(
                "Event confirm id=%s tool=%s summary=%s",
                task.task_id,
                data.get("tool"),
                self._compact(data.get("summary")),
            )
            return
        if event_type == "needs_user_input":
            self.logger.info(
                "Event user_input id=%s question=%s",
                task.task_id,
                self._compact(data.get("question")),
            )
            return
        if event_type == "result":
            self.logger.info("Event result id=%s result=%s", task.task_id, self._compact(data.get("result")))
            return
        if event_type == "error":
            self.logger.info("Event error id=%s error=%s", task.task_id, self._compact(data.get("error")))

    @staticmethod
    def _compact(value: Optional[str], limit: int = 200) -> str:
        if value is None:
            return ""
        text = " ".join(str(value).split())
        if len(text) > limit:
            return text[:limit] + "..."
        return text

    def _get_worker_controller(self, settings: Settings) -> BrowserController:
        desired_profile = settings.browser_user_data_dir
        if self.worker_controller and self.worker_profile_dir == desired_profile:
            try:
                self.worker_controller.select_page(start_new_window=False)
                return self.worker_controller
            except Exception:
                try:
                    self.worker_controller.close()
                except Exception:
                    pass
                self.worker_controller = None
                self.worker_profile_dir = None

        if self.worker_controller and self.worker_profile_dir != desired_profile:
            try:
                self.worker_controller.close()
            except Exception:
                pass
            self.worker_controller = None
            self.worker_profile_dir = None

        self.worker_controller = BrowserController(settings, start_new_window=False)
        self.worker_profile_dir = desired_profile
        self.logger.info("Created worker controller profile=%s", desired_profile)
        return self.worker_controller

    def _settings_for_task(self, task: Task) -> Settings:
        settings = self.settings
        provider = (task.provider or settings.llm_provider).strip().lower()
        if provider not in {"openai", "anthropic", "gemini", "google", "ollama"}:
            raise ValueError(f"Unsupported provider: {provider}")

        settings = replace(settings, llm_provider=provider)
        if provider in {"gemini", "google"}:
            if not settings.google_api_key:
                raise ValueError("Missing GOOGLE_API_KEY for Gemini provider.")
            if task.model:
                settings = replace(settings, gemini_model=task.model)
        elif provider == "openai":
            if not settings.openai_api_key:
                raise ValueError("Missing OPENAI_API_KEY for OpenAI provider.")
            if task.model:
                settings = replace(settings, openai_model=task.model)
        elif provider == "ollama":
            if not settings.ollama_model and not task.model:
                raise ValueError("Missing OLLAMA_MODEL for Ollama provider.")
            if task.model:
                settings = replace(settings, ollama_model=task.model)
        elif provider == "anthropic":
            if not settings.anthropic_api_key:
                raise ValueError("Missing ANTHROPIC_API_KEY for Anthropic provider.")
            if task.model:
                settings = replace(settings, anthropic_model=task.model)
        if not task.safe_mode:
            unsafe_dir = settings.unsafe_browser_user_data_dir
            if not unsafe_dir:
                raise ValueError("Unsafe mode requires UNSAFE_BROWSER_USER_DATA_DIR in .env.")
            if not unsafe_dir.exists() or not unsafe_dir.is_dir():
                raise ValueError(f"Unsafe profile path not found: {unsafe_dir}")
            settings = replace(settings, browser_user_data_dir=unsafe_dir)
        return settings

    @staticmethod
    def _extract_start_url(prompt: str) -> str:
        lowered = prompt.lower()
        if "wikipedia" in lowered or "\u0432\u0438\u043a\u0438\u043f\u0435\u0434" in lowered:
            query = extract_goal_query(prompt)
            if query:
                base = "https://en.wikipedia.org"
                if "ru.wikipedia.org" in lowered or re.search(r"[\u0400-\u04FF]", prompt):
                    base = "https://ru.wikipedia.org"
                elif re.search(r"[\u0400-\u04FF]", query):
                    base = "https://ru.wikipedia.org"
                return f"{base}/w/index.php?search={quote(query)}"
            return "https://www.wikipedia.org"
        url_match = re.search(r"https?://\\S+", prompt)
        if url_match:
            return url_match.group(0).rstrip(").,;")
        www_match = re.search(r"\\bwww\\.[^\\s]+", prompt)
        if www_match:
            return f"https://{www_match.group(0).rstrip(').,;')}"
        domain_match = re.search(r"\\b([a-z0-9-]+\\.)+[a-z]{2,10}\\b", prompt, re.IGNORECASE)
        if domain_match:
            return f"https://{domain_match.group(0)}"
        return ""

    @staticmethod
    def _resolve_search_engine(value: Optional[str]) -> str:
        options = {
            "google": "https://www.google.com",
            "duckduckgo": "https://duckduckgo.com",
            "bing": "https://www.bing.com",
            "yandex": "https://yandex.ru",
        }
        if not value:
            return options["google"]
        return options.get(value.lower(), options["google"])
