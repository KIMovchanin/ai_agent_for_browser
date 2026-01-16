from __future__ import annotations

import logging
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent.config import Settings
from .events import stream_events
from .task_manager import TaskManager


logger = logging.getLogger("app")
if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
for name in ("app", "app.task_manager", "agent.loop", "agent.browser"):
    logging.getLogger(name).setLevel(logging.INFO)

settings = Settings.from_env()
manager = TaskManager(settings)

app = FastAPI(title="Browser Agent")


@app.on_event("startup")
def _log_startup() -> None:
    provider = settings.llm_provider
    if provider == "anthropic":
        model = settings.anthropic_model
    elif provider in {"gemini", "google"}:
        model = settings.gemini_model
    else:
        model = settings.openai_model
    logger.info(
        "Startup provider=%s model=%s dry_run=%s",
        provider,
        model,
        settings.dry_run,
    )
    logger.info(
        "Browser engine=%s channel=%s headless=%s profile=%s",
        settings.browser_engine,
        settings.browser_channel or "-",
        settings.browser_headless,
        settings.browser_user_data_dir,
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TaskCreate(BaseModel):
    prompt: str
    browser_only: bool = True
    search_engine: Optional[str] = None


class ModelListRequest(BaseModel):
    api_key: str
    base_url: Optional[str] = None


def _normalize_base_url(base_url: Optional[str], default: str) -> str:
    return (base_url or default).rstrip("/")


def _raise_for_status(provider: str, response: httpx.Response) -> None:
    if response.status_code >= 400:
        raise HTTPException(
            status_code=400,
            detail=f"{provider} error {response.status_code}: {response.text}",
        )


@app.post("/tasks")
def create_task(payload: TaskCreate):
    try:
        task = manager.create_task(
            payload.prompt,
            browser_only=payload.browser_only,
            search_engine=payload.search_engine,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"task_id": task.task_id}


@app.get("/tasks/{task_id}")
def get_task(task_id: str):
    try:
        task = manager.get_task(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "task_id": task.task_id,
        "prompt": task.prompt,
        "status": task.status,
        "result": task.result,
        "updated_at": task.updated_at,
    }


@app.get("/tasks/{task_id}/events")
def get_events(task_id: str):
    try:
        task = manager.get_task(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return StreamingResponse(stream_events(task), media_type="text/event-stream")


@app.post("/tasks/{task_id}/confirm")
def confirm_task(task_id: str):
    try:
        task = manager.confirm_task(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"task_id": task.task_id, "status": task.status}


@app.post("/tasks/{task_id}/stop")
def stop_task(task_id: str):
    try:
        task = manager.stop_task(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"task_id": task.task_id, "status": task.status}


@app.post("/providers/openai/models")
def list_openai_models(payload: ModelListRequest):
    base_url = _normalize_base_url(payload.base_url, "https://api.openai.com")
    if base_url.endswith("/v1"):
        url = f"{base_url}/models"
    else:
        url = f"{base_url}/v1/models"
    headers = {
        "Authorization": f"Bearer {payload.api_key}",
        "Content-Type": "application/json",
    }
    response = httpx.get(url, headers=headers, timeout=30)
    _raise_for_status("OpenAI", response)
    data = response.json()
    models = []
    for item in data.get("data", []) or []:
        model_id = item.get("id") or item.get("model") or item.get("name")
        if model_id:
            models.append(model_id)
    models.sort()
    return {"models": models}


@app.post("/providers/anthropic/models")
def list_anthropic_models(payload: ModelListRequest):
    base_url = _normalize_base_url(payload.base_url, "https://api.anthropic.com")
    url = f"{base_url}/v1/models"
    headers = {
        "x-api-key": payload.api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    response = httpx.get(url, headers=headers, timeout=30)
    _raise_for_status("Anthropic", response)
    data = response.json()
    models = []
    for item in data.get("data", []) or []:
        model_id = item.get("id") or item.get("model") or item.get("name")
        if model_id:
            models.append(model_id)
    models.sort()
    return {"models": models}


@app.post("/providers/gemini/models")
def list_gemini_models(payload: ModelListRequest):
    base_url = _normalize_base_url(payload.base_url, "https://generativelanguage.googleapis.com")
    url = f"{base_url}/v1beta/models"
    models = set()
    page_token = None
    while True:
        params = {"key": payload.api_key}
        if page_token:
            params["pageToken"] = page_token
        response = httpx.get(url, params=params, timeout=30)
        _raise_for_status("Gemini", response)
        data = response.json()
        for item in data.get("models", []) or []:
            methods = item.get("supportedGenerationMethods") or []
            if "generateContent" in methods:
                name = item.get("name", "")
                if name.startswith("models/"):
                    name = name.replace("models/", "", 1)
                if name:
                    models.add(name)
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return {"models": sorted(models)}
