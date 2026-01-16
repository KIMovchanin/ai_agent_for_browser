from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


class LLMError(RuntimeError):
    pass


@dataclass
class ToolCall:
    name: str
    arguments: Dict[str, Any]


@dataclass
class LLMResponse:
    content: Optional[str]
    tool_calls: List[ToolCall]
    raw: Optional[Dict[str, Any]] = None


class BaseLLM:
    supports_tools: bool = False

    def complete(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Dict[str, Any]] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> LLMResponse:
        raise NotImplementedError
