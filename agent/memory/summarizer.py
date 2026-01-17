from __future__ import annotations

from typing import List

from ..llm.base import BaseLLM, LLMError
from .state import MemoryState


class Summarizer:
    def __init__(self, llm: BaseLLM, max_history: int = 80, keep_last: int = 12) -> None:
        self.llm = llm
        self.max_history = max_history
        self.keep_last = keep_last

    def maybe_summarize(self, memory: MemoryState) -> None:
        if len(memory.steps) <= self.max_history:
            return
        steps = list(memory.steps)
        history = "\n".join(
            f"{item.step}. {item.tool} {item.args} => {item.status}"
            for item in steps
        )
        prompt = (
            "Summarize the following steps into concise memory. "
            "Preserve goals, progress, blockers, and facts. "
            "Output 5-8 bullet points.\n\n"
            f"Existing summary:\n{memory.summary}\n\n"
            f"Steps:\n{history}"
        )

        summary = memory.summary
        try:
            response = self.llm.complete(
                messages=[
                    {"role": "system", "content": "You are a precise summarizer."},
                    {"role": "user", "content": prompt},
                ],
                tools=None,
            )
            if response.content:
                summary = response.content.strip()
        except LLMError:
            summary = (summary + " | ") if summary else ""
            summary += "Condensed history; LLM summarizer failed."

        memory.summary = summary
        memory.steps = memory.steps.__class__(steps[-self.keep_last :], maxlen=memory.max_steps)
