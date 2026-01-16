from __future__ import annotations

from typing import Dict

from ..memory.state import MemoryState
from .extractor import Extractor
from .navigator import Navigator
from .reflector import Reflector


class Coordinator:
    def __init__(self, navigator: Navigator, extractor: Extractor, reflector: Reflector) -> None:
        self.navigator = navigator
        self.extractor = extractor
        self.reflector = reflector

    def choose_mode(
        self,
        goal: str,
        memory: MemoryState,
        snapshot: Dict[str, object],
        error_count: int,
        no_progress_steps: int,
    ) -> str:
        if error_count > 0 or no_progress_steps >= 2:
            return "reflector"
        goal_lower = goal.lower()
        if any(token in goal_lower for token in ["extract", "summarize", "list", "find"]):
            if len(memory.steps) > 2:
                return "extractor"
        return "navigator"

    def select_agent(
        self,
        goal: str,
        memory: MemoryState,
        snapshot: Dict[str, object],
        error_count: int,
        no_progress_steps: int,
    ):
        mode = self.choose_mode(goal, memory, snapshot, error_count, no_progress_steps)
        if mode == "reflector":
            return self.reflector
        if mode == "extractor":
            return self.extractor
        return self.navigator
