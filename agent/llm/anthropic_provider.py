from typing import Any, Dict, List, Optional

import httpx

from .base import BaseLLM, LLMError, LLMResponse


class AnthropicProvider(BaseLLM):
    supports_tools = False

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_s: int = 60,
        max_retries: int = 2,
        default_temperature: float = 0.2,
        default_max_tokens: int = 600,
        base_url: str = "https://api.anthropic.com",
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.default_temperature = default_temperature
        self.default_max_tokens = default_max_tokens
        self.base_url = base_url.rstrip("/")

    def _endpoint(self) -> str:
        return f"{self.base_url}/v1/messages"

    def complete(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Dict[str, Any]] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> LLMResponse:
        system_parts = []
        converted: List[Dict[str, Any]] = []
        for message in messages:
            role = message.get("role")
            content = message.get("content")
            if role == "system":
                if isinstance(content, list):
                    system_parts.extend([str(part) for part in content])
                elif content:
                    system_parts.append(str(content))
                continue
            if isinstance(content, list):
                content = "\n".join(str(part) for part in content)
            converted.append({"role": role, "content": content or ""})

        payload: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens if max_tokens is not None else self.default_max_tokens,
            "temperature": temperature if temperature is not None else self.default_temperature,
            "system": "\n".join(system_parts),
            "messages": converted,
        }

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        for attempt in range(self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout_s) as client:
                    response = client.post(self._endpoint(), headers=headers, json=payload)
                if response.status_code >= 400:
                    raise LLMError(f"Anthropic error {response.status_code}: {response.text}")
                data = response.json()
                parts = []
                for item in data.get("content", []) or []:
                    if item.get("type") == "text":
                        parts.append(item.get("text", ""))
                content = "\n".join(parts).strip()
                return LLMResponse(content=content, tool_calls=[], raw=data)
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                if attempt >= self.max_retries:
                    raise LLMError(str(exc)) from exc

        raise LLMError("Anthropic request failed")
