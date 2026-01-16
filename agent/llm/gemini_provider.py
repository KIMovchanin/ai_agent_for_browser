import hashlib
from typing import Any, Dict, List, Optional, Set

import httpx

from .base import BaseLLM, LLMError, LLMResponse

_MODELS_CACHE: Dict[str, Dict[str, Set[str]]] = {}


class GeminiProvider(BaseLLM):
    supports_tools = False

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_s: int = 60,
        max_retries: int = 2,
        default_temperature: float = 0.2,
        default_max_tokens: int = 600,
        base_url: str = "https://generativelanguage.googleapis.com",
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.default_temperature = default_temperature
        self.default_max_tokens = default_max_tokens
        self.base_url = base_url.rstrip("/")

    def _endpoint(self) -> str:
        return f"{self.base_url}/v1beta/models/{self.model}:generateContent?key={self.api_key}"

    def _cache_key(self) -> str:
        raw = f"{self.base_url}|{self.api_key}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def list_models(self) -> Dict[str, Set[str]]:
        cache_key = self._cache_key()
        if cache_key in _MODELS_CACHE:
            return _MODELS_CACHE[cache_key]

        models: Dict[str, Set[str]] = {}
        page_token: Optional[str] = None
        base_url = f"{self.base_url}/v1beta/models"

        for attempt in range(self.max_retries + 1):
            try:
                while True:
                    params = {"key": self.api_key}
                    if page_token:
                        params["pageToken"] = page_token
                    with httpx.Client(timeout=self.timeout_s) as client:
                        response = client.get(base_url, params=params)
                    if response.status_code >= 400:
                        raise LLMError(f"Gemini listModels error {response.status_code}: {response.text}")
                    data = response.json()
                    for item in data.get("models", []) or []:
                        name = item.get("name")
                        methods = item.get("supportedGenerationMethods") or []
                        if name:
                            models[name] = set(methods)
                    page_token = data.get("nextPageToken")
                    if not page_token:
                        break
                _MODELS_CACHE[cache_key] = models
                return models
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                if attempt >= self.max_retries:
                    raise LLMError(str(exc)) from exc

        raise LLMError("Gemini listModels request failed")

    def validate_model(self) -> None:
        models = self.list_models()
        target = self.model
        if target.startswith("models/"):
            target_full = target
            target = target.replace("models/", "")
        else:
            target_full = f"models/{target}"

        if target_full not in models:
            available = sorted(
                name.replace("models/", "")
                for name, methods in models.items()
                if "generateContent" in methods
            )
            sample = ", ".join(available[:12])
            raise LLMError(
                f"Gemini model '{self.model}' is not available. "
                f"Available generateContent models include: {sample}"
            )

        methods = models[target_full]
        if "generateContent" not in methods:
            raise LLMError(f"Gemini model '{self.model}' does not support generateContent.")

    def complete(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Dict[str, Any]] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> LLMResponse:
        system_parts: List[str] = []
        contents: List[Dict[str, Any]] = []
        for message in messages:
            role = message.get("role")
            content = message.get("content")
            if isinstance(content, list):
                content = "\n".join(str(part) for part in content)
            if role == "system":
                if content:
                    system_parts.append(str(content))
                continue
            mapped_role = "model" if role == "assistant" else "user"
            contents.append({"role": mapped_role, "parts": [{"text": content or ""}]})

        if system_parts:
            system_text = "\n".join(system_parts)
            if contents:
                contents[0]["parts"].insert(0, {"text": f"SYSTEM: {system_text}"})
            else:
                contents = [{"role": "user", "parts": [{"text": f"SYSTEM: {system_text}"}]}]

        payload: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature if temperature is not None else self.default_temperature,
                "maxOutputTokens": max_tokens if max_tokens is not None else self.default_max_tokens,
            },
        }

        headers = {"Content-Type": "application/json"}

        for attempt in range(self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout_s) as client:
                    response = client.post(self._endpoint(), headers=headers, json=payload)
                if response.status_code >= 400:
                    raise LLMError(f"Gemini error {response.status_code}: {response.text}")
                data = response.json()
                candidates = data.get("candidates", []) or []
                if not candidates:
                    raise LLMError("Gemini response missing candidates")
                parts = candidates[0].get("content", {}).get("parts", []) or []
                text_parts = [part.get("text", "") for part in parts if part.get("text")]
                content_text = "\n".join(text_parts).strip()
                return LLMResponse(content=content_text, tool_calls=[], raw=data)
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                if attempt >= self.max_retries:
                    raise LLMError(str(exc)) from exc

        raise LLMError("Gemini request failed")
