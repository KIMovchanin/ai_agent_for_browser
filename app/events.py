from __future__ import annotations

import json
import queue
import time
from typing import Dict, Iterable

from .task_manager import Task


def format_sse(event_type: str, data: Dict) -> str:
    payload = json.dumps(data, ensure_ascii=True)
    return f"event: {event_type}\ndata: {payload}\n\n"


def stream_events(task: Task) -> Iterable[str]:
    while True:
        try:
            event = task.events.get(timeout=1)
            yield format_sse(event["type"], event)
            if event["type"] == "status" and event["data"].get("status") in {
                "done",
                "stopped",
                "error",
            }:
                break
        except queue.Empty:
            yield ": keep-alive\n\n"
            if task.status in {"done", "stopped", "error"}:
                break
            time.sleep(0.1)
