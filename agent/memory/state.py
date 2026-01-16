from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional


@dataclass
class StepRecord:
    step: int
    tool: str
    args: Dict[str, object]
    reason: str
    url: str
    title: str
    status: str
    error: Optional[str] = None


@dataclass
class MemoryState:
    max_steps: int = 40
    steps: Deque[StepRecord] = field(default_factory=deque)
    summary: str = ""
    facts: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.steps.maxlen != self.max_steps:
            self.steps = deque(self.steps, maxlen=self.max_steps)

    def add_step(self, record: StepRecord) -> None:
        self.steps.append(record)

    def recent_steps(self, limit: int = 6) -> List[Dict[str, object]]:
        items = list(self.steps)[-limit:]
        return [
            {
                "step": item.step,
                "tool": item.tool,
                "args": item.args,
                "reason": item.reason,
                "status": item.status,
                "error": item.error,
                "url": item.url,
                "title": item.title,
            }
            for item in items
        ]
