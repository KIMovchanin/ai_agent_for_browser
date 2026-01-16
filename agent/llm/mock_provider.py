from typing import Any, Dict, List, Optional

from .base import BaseLLM, LLMResponse, ToolCall


class MockProvider(BaseLLM):
    supports_tools = True

    def __init__(self, message: str = "Dry-run mode: configure an API key to enable real actions.") -> None:
        self.message = message

    def complete(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Dict[str, Any]] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> LLMResponse:
        return LLMResponse(
            content=self.message,
            tool_calls=[ToolCall(name="finish", arguments={"result": self.message})],
            raw=None,
        )
