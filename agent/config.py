import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


@dataclass
class Settings:
    llm_provider: str
    openai_api_key: Optional[str]
    openai_base_url: str
    openai_model: str
    anthropic_api_key: Optional[str]
    anthropic_model: str
    google_api_key: Optional[str]
    gemini_model: str
    gemini_base_url: str
    dry_run: bool

    browser_user_data_dir: Path
    browser_headless: bool
    browser_slow_mo_ms: int
    browser_engine: str
    browser_channel: Optional[str]
    search_engine_url: str

    max_steps: int
    max_retries: int
    no_progress_limit: int

    screenshot_dir: Path
    trace_dir: Path
    trace_enabled: bool

    request_timeout_s: int

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()

        llm_provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()
        openai_api_key = os.getenv("OPENAI_API_KEY")
        openai_base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com")
        openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        anthropic_model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")
        google_api_key = os.getenv("GOOGLE_API_KEY")
        gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
        gemini_base_url = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com")
        dry_run = os.getenv("DRY_RUN", "0").strip() == "1"

        if not openai_api_key and not anthropic_api_key and not google_api_key:
            dry_run = True

        browser_user_data_dir = Path(os.getenv("BROWSER_USER_DATA_DIR", ".browser-data"))
        browser_headless = os.getenv("BROWSER_HEADLESS", "0").strip() == "1"
        browser_slow_mo_ms = int(os.getenv("BROWSER_SLOW_MO_MS", "250"))
        browser_engine = os.getenv("BROWSER_ENGINE", "auto").strip().lower()
        browser_channel = os.getenv("BROWSER_CHANNEL") or None
        search_engine_url = os.getenv("SEARCH_ENGINE_URL", "https://www.google.com").strip()

        max_steps = int(os.getenv("MAX_STEPS", "60"))
        max_retries = int(os.getenv("MAX_RETRIES", "2"))
        no_progress_limit = int(os.getenv("NO_PROGRESS_LIMIT", "5"))

        screenshot_dir = Path(os.getenv("SCREENSHOT_DIR", "artifacts/screenshots"))
        trace_dir = Path(os.getenv("TRACE_DIR", "artifacts/traces"))
        trace_enabled = os.getenv("TRACE_ENABLED", "0").strip() == "1"

        request_timeout_s = int(os.getenv("REQUEST_TIMEOUT_S", "60"))

        return cls(
            llm_provider=llm_provider,
            openai_api_key=openai_api_key,
            openai_base_url=openai_base_url,
            openai_model=openai_model,
            anthropic_api_key=anthropic_api_key,
            anthropic_model=anthropic_model,
            google_api_key=google_api_key,
            gemini_model=gemini_model,
            gemini_base_url=gemini_base_url,
            dry_run=dry_run,
            browser_user_data_dir=browser_user_data_dir,
            browser_headless=browser_headless,
            browser_slow_mo_ms=browser_slow_mo_ms,
            browser_engine=browser_engine,
            browser_channel=browser_channel,
            search_engine_url=search_engine_url,
            max_steps=max_steps,
            max_retries=max_retries,
            no_progress_limit=no_progress_limit,
            screenshot_dir=screenshot_dir,
            trace_dir=trace_dir,
            trace_enabled=trace_enabled,
            request_timeout_s=request_timeout_s,
        )

    def ensure_dirs(self) -> None:
        self.browser_user_data_dir.mkdir(parents=True, exist_ok=True)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self.trace_dir.mkdir(parents=True, exist_ok=True)
