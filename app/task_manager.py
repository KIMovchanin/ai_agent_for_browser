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
from agent.config import Settings, _resolve_unsafe_user_data_dir
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
    unsafe_profile_dir: Optional[str] = None
    browser_engine: Optional[str] = None
    browser_channel: Optional[str] = None
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
        unsafe_profile_dir: Optional[str] = None,
        browser_engine: Optional[str] = None,
        browser_channel: Optional[str] = None,
    ) -> Task:
        with self.lock:
            for task in self.tasks.values():
                if task.session and task.session.stop_requested and task.status in {
                    "queued",
                    "running",
                    "waiting_confirm",
                    "waiting_user",
                }:
                    task.status = "stopped"
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
                "Create task id=%s mode=%s browser_only=%s search_engine=%s provider=%s model=%s safe_mode=%s browser_engine=%s browser_channel=%s prompt=%s",
                task_id,
                mode,
                browser_only,
                search_engine or "default",
                provider or "-",
                model or "-",
                safe_mode,
                browser_engine or "-",
                browser_channel or "-",
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
                unsafe_profile_dir=unsafe_profile_dir,
                browser_engine=browser_engine,
                browser_channel=browser_channel,
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
            if task.session.stop_requested:
                task.session.force_stop("User selected stop option.")
                task.status = "stopped"
                self._emit(task, "status", {"status": task.status})
                return task
            task.session.confirm()
            self._enqueue(task)
        return task

    def stop_task(self, task_id: str) -> Task:
        task = self.get_task(task_id)
        if task.session:
            self.logger.info("Stop task id=%s status=%s", task.task_id, task.status)
            task.session.force_stop("Stop button pressed.")
            task.status = "stopped"
            self._emit(task, "status", {"status": task.status})
            return task
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
            if task.status == "stopped":
                self._emit(task, "status", {"status": task.status})
                return
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
                        self._emit_rate_limit_if_needed(task, str(exc))
                        self._emit(task, "error", {"error": str(exc)})
                        self._emit(task, "status", {"status": task.status})
                        return
                task.session.run()
                task.updated_at = time.time()

                if task.session.stop_requested:
                    task.status = "stopped"
                elif task.session.done:
                    task.status = "done"
                    task.result = task.session.result
                elif task.session.waiting_confirm:
                    task.status = "waiting_confirm"
                elif task.session.waiting_user:
                    task.status = "waiting_user"
                else:
                    task.status = "running"
            else:
                task.status = "error"
                self._emit(task, "error", {"error": "Missing agent session."})
        except Exception as exc:  # pylint: disable=broad-except
            task.status = "error"
            self._emit_rate_limit_if_needed(task, str(exc))
            self._emit(task, "error", {"error": str(exc)})

        self._emit(task, "status", {"status": task.status})

    def _run_direct(self, task: Task) -> None:
        try:
            canned = self._maybe_direct_capabilities_answer(task.prompt)
            if canned:
                task.result = canned
                task.status = "done"
                self._emit(
                    task,
                    "log",
                    {"step": 1, "tool": "direct_answer", "reason": "Capability response.", "status": "ok"},
                )
                self._emit(task, "result", {"result": canned})
                return
            llm = create_llm(self._settings_for_task(task))
            reason = "Browser-only disabled and task is not explicit."
            self.logger.info("Direct mode id=%s reason=%s", task.task_id, reason)
            response = llm.complete(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an AI browser automation agent controlling a real, visible browser via tools. "
                            "Direct mode means you cannot use browser tools for this request. "
                            "Respond in the user's language. Be concise and factual. "
                            "Do not claim you browsed or performed actions. "
                            "If the user asks what you can do, describe your browser-agent capabilities and ask "
                            "for a concrete task. If the request requires browsing, suggest enabling browser-only."
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
            self._emit_rate_limit_if_needed(task, str(exc))
            self._emit(task, "error", {"error": str(exc)})

    @staticmethod
    def _has_cyrillic(text: str) -> bool:
        return bool(re.search(r"[А-Яа-яЁё]", text or ""))

    def _emit_rate_limit_if_needed(self, task: Task, error_text: str) -> None:
        message = self._rate_limit_message(error_text)
        if not message:
            return
        self._emit(
            task,
            "log",
            {
                "step": 0,
                "tool": "rate_limit",
                "status": "warning",
                "reason": message,
                "error": self._compact(error_text, limit=240),
            },
        )

    @staticmethod
    def _rate_limit_message(error_text: str) -> Optional[str]:
        if not error_text:
            return None
        lowered = error_text.lower()
        markers = [
            "429",
            "too many requests",
            "rate limit",
            "tpm",
            "rpm",
            "quota",
        ]
        if not any(marker in lowered for marker in markers):
            return None
        if "tpm" in lowered or "tokens per min" in lowered:
            return "Rate limit reached (TPM). Wait a bit or reduce request size."
        if "rpm" in lowered or "requests per min" in lowered:
            return "Rate limit reached (RPM). Wait a bit before retrying."
        return "Rate limit reached. Please wait and try again."

    @staticmethod
    def _maybe_direct_capabilities_answer(prompt: str) -> Optional[str]:
        if not prompt:
            return None
        text = prompt.strip().lower()
        patterns = [
            r"\bчто ты умеешь\b",
            r"\bчто ты можешь\b",
            r"\bтвои возможности\b",
            r"\bwhat can you do\b",
            r"\bwhat do you do\b",
            r"\byour capabilities\b",
        ]
        if not any(re.search(pattern, text) for pattern in patterns):
            return None
        if TaskManager._has_cyrillic(prompt):
            return (
                "Я браузерный агент: могу переходить по сайтам, искать информацию, заполнять формы, "
                "собирать данные и подготавливать действия в браузере. "
                "В режиме «Только браузер» работаю автономно, а перед опасными действиями прошу подтверждение. "
                "Сформулируйте конкретную задачу (сайт и цель) или включите «Только браузер»."
            )
        return (
            "I am a browser automation agent: I can navigate sites, search, fill forms, gather data, "
            "and prepare actions in the browser. "
            "In Browser-only mode I work autonomously and ask for confirmation before risky actions. "
            "Give me a concrete task (site + goal) or enable Browser-only."
        )

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
            "url",
            "link",
            "website",
            "site",
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
            "\u0441\u0441\u044b\u043b\u043a",
            "\u0430\u0434\u0440\u0435\u0441",
            "\u0441\u0430\u0439\u0442",
            "\u0434\u043e\u043c\u0435\u043d",
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

    def shutdown(self) -> None:
        with self.lock:
            for task in self.tasks.values():
                if task.session:
                    try:
                        task.session.force_stop("Server shutdown.")
                    except Exception:
                        pass
            if self.worker_controller:
                try:
                    self.worker_controller.close()
                except Exception:
                    pass
                self.worker_controller = None
                self.worker_profile_dir = None

    def _settings_for_task(self, task: Task) -> Settings:
        settings = self.settings
        provider = (task.provider or settings.llm_provider).strip().lower()
        if provider not in {"openai", "anthropic", "gemini", "google", "ollama"}:
            raise ValueError(f"Unsupported provider: {provider}")

        browser_engine = (task.browser_engine or settings.browser_engine).strip().lower()
        browser_channel = task.browser_channel or settings.browser_channel
        unsafe_channel_hint = browser_channel or ""
        if browser_engine == "firefox":
            unsafe_channel_hint = "firefox"
        settings = replace(
            settings,
            llm_provider=provider,
            browser_engine=browser_engine,
            browser_channel=browser_channel,
        )
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
            unsafe_value = _normalize_profile_value(task.unsafe_profile_dir)
            if unsafe_value is None and settings.unsafe_browser_user_data_dir:
                unsafe_value = str(settings.unsafe_browser_user_data_dir)
            unsafe_dir = _resolve_unsafe_user_data_dir(unsafe_value, unsafe_channel_hint)
            if not unsafe_dir:
                raise ValueError("Unsafe mode requires UNSAFE_BROWSER_USER_DATA_DIR in .env.")
            if not unsafe_dir.exists() or not unsafe_dir.is_dir():
                raise ValueError(f"Unsafe profile path not found: {unsafe_dir}")
            settings = replace(
                settings,
                browser_user_data_dir=unsafe_dir,
                unsafe_browser_user_data_dir=unsafe_dir,
            )
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


def _normalize_profile_value(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    cleaned = value.strip().strip('"').strip("'")
    if not cleaned:
        return None
    if cleaned.lower() == "auto":
        return "auto"
    label_patterns = [
        r"^(edge|chrome|firefox|yandex|opera)\s*[:\-]\s*",
        r"^(?:браузер|путь)\s*[:\-]\s*",
        r"^(?:profile path|root directory)\s*[:\-]\s*",
        r"^(?:путь профиля|корневая папка)\s*[:\-]\s*",
    ]
    for pattern in label_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    match = re.search(r"[A-Za-z]:\\\\.+", cleaned)
    if match:
        cleaned = match.group(0)
    return cleaned.strip() if cleaned else None
