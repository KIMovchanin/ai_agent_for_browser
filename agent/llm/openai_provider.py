import json
from typing import Any, Dict, List, Optional

import httpx

from .base import BaseLLM, LLMError, LLMResponse, ToolCall


class OpenAIProvider(BaseLLM):
    supports_tools = True

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout_s: int = 60,
        max_retries: int = 2,
        default_temperature: float = 0.2,
        default_max_tokens: int = 600,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.default_temperature = default_temperature
        self.default_max_tokens = default_max_tokens

    def _endpoint(self) -> str:
        if self.base_url.endswith("/v1"):
            return f"{self.base_url}/chat/completions"
        return f"{self.base_url}/v1/chat/completions"

    def complete(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Dict[str, Any]] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> LLMResponse:
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.default_temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.default_max_tokens,
        }
        if tools:
            payload["tools"] = tools
        if tool_choice:
            payload["tool_choice"] = tool_choice

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        for attempt in range(self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout_s) as client:
                    response = client.post(self._endpoint(), headers=headers, json=payload)
                if response.status_code >= 400:
                    raise LLMError(f"OpenAI error {response.status_code}: {response.text}")
                data = response.json()
                message = data["choices"][0]["message"]
                content = message.get("content")
                tool_calls = []
                for call in message.get("tool_calls", []) or []:
                    func = call.get("function", {})
                    name = func.get("name")
                    arguments = func.get("arguments")
                    if isinstance(arguments, str):
                        try:
                            arguments = json.loads(arguments)
                        except json.JSONDecodeError:
                            arguments = {"_raw": arguments}
                    if name:
                        tool_calls.append(ToolCall(name=name, arguments=arguments or {}))
                return LLMResponse(content=content, tool_calls=tool_calls, raw=data)
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                if attempt >= self.max_retries:
                    raise LLMError(str(exc)) from exc

        raise LLMError("OpenAI request failed")
