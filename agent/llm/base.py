from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional


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


class MeteredLLM(BaseLLM):
    def __init__(self, base: BaseLLM, on_response: Callable[[LLMResponse], None]) -> None:
        self.base = base
        self.on_response = on_response
        self.supports_tools = base.supports_tools

    def complete(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Dict[str, Any]] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> LLMResponse:
        response = self.base.complete(
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        self.on_response(response)
        return response
