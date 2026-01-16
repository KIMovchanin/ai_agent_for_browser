from __future__ import annotations

import re
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from queue import Queue
from typing import Any, Callable, Deque, Dict, Optional

from agent.config import Settings
from agent.llm import create_llm
from agent.llm.base import LLMError
from agent.loop import AgentSession


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
    create_window: bool = True
    result: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    event_history: Deque[Dict[str, Any]] = field(default_factory=lambda: deque(maxlen=200))
    thread: Optional[threading.Thread] = None


class TaskManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.tasks: Dict[str, Task] = {}
        self.lock = threading.Lock()

    def create_task(
        self,
        prompt: str,
        browser_only: bool = True,
        search_engine: Optional[str] = None,
        create_window: bool = True,
    ) -> Task:
        with self.lock:
            if any(task.status in {"running", "waiting_confirm", "waiting_user"} for task in self.tasks.values()):
                raise RuntimeError("Only one active task is supported with a shared browser profile.")
            task_id = uuid.uuid4().hex
            session = None
            mode = "agent"
            if not browser_only and not self._is_browser_task(prompt):
                mode = "direct"

            if mode == "agent":
                search_url = self._resolve_search_engine(search_engine)
                try:
                    session = AgentSession(
                        goal=prompt,
                        settings=self.settings,
                        emit=None,
                        browser_only=browser_only,
                        search_engine_url=search_url,
                        create_window=create_window,
                    )
                except LLMError as exc:
                    raise ValueError(str(exc)) from exc
            else:
                try:
                    create_llm(self.settings)
                except LLMError as exc:
                    raise ValueError(str(exc)) from exc
            events: Queue = Queue()
            task = Task(
                task_id=task_id,
                prompt=prompt,
                status="created",
                session=session,
                events=events,
                mode=mode,
                browser_only=browser_only,
                search_engine=(search_engine or "google"),
                create_window=create_window,
            )
            if task.session:
                task.session.emit = self._build_emitter(task)
            self.tasks[task_id] = task

        self._spawn(task)
        return task

    def get_task(self, task_id: str) -> Task:
        task = self.tasks.get(task_id)
        if not task:
            raise KeyError("Task not found")
        return task

    def confirm_task(self, task_id: str) -> Task:
        task = self.get_task(task_id)
        if task.session:
            task.session.confirm()
            self._spawn(task)
        return task

    def stop_task(self, task_id: str) -> Task:
        task = self.get_task(task_id)
        if task.session:
            task.session.request_stop()
            self._spawn(task)
        else:
            task.status = "stopped"
            self._emit(task, "status", {"status": task.status})
        return task

    def _spawn(self, task: Task) -> None:
        if task.thread and task.thread.is_alive():
            return
        task.thread = threading.Thread(target=self._run_task, args=(task,), daemon=True)
        task.thread.start()

    def _run_task(self, task: Task) -> None:
        try:
            task.status = "running"
            task.updated_at = time.time()
            if task.mode == "direct":
                self._run_direct(task)
            elif task.session:
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
            llm = create_llm(self.settings)
            reason = "Browser-only disabled and task is not explicit."
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
    def _is_browser_task(prompt: str) -> bool:
        text = prompt.lower()
        if re.search(r"https?://|www\\.", text):
            return True
        if re.search(r"\\b\\w+\\.(com|org|net|ru|io|ai|app|dev|edu|gov|co)\\b", text):
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
