import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

try:
    import winreg  # type: ignore
except ImportError:  # pragma: no cover - non-Windows
    winreg = None


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
    ollama_api_key: Optional[str]
    ollama_model: str
    ollama_base_url: str
    dry_run: bool

    browser_user_data_dir: Path
    unsafe_browser_user_data_dir: Optional[Path]
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
        openai_model = os.getenv("OPENAI_MODEL", "gpt-4.1-nano")
        anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        anthropic_model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")
        google_api_key = os.getenv("GOOGLE_API_KEY")
        gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-lite")
        gemini_base_url = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com")
        dry_run = os.getenv("DRY_RUN", "0").strip() == "1"

        browser_engine = os.getenv("BROWSER_ENGINE", "auto").strip().lower()
        browser_channel = os.getenv("BROWSER_CHANNEL") or None
        browser_user_data_dir = Path(os.getenv("BROWSER_USER_DATA_DIR", ".browser-data"))
        unsafe_browser_user_data_dir_value = os.getenv("UNSAFE_BROWSER_USER_DATA_DIR")
        unsafe_browser_user_data_dir = _resolve_unsafe_user_data_dir(
            unsafe_browser_user_data_dir_value, browser_channel
        )
        browser_headless = os.getenv("BROWSER_HEADLESS", "0").strip() == "1"
        browser_slow_mo_ms = int(os.getenv("BROWSER_SLOW_MO_MS", "30"))
        search_engine_url = os.getenv("SEARCH_ENGINE_URL", "https://www.google.com").strip()

        max_steps = int(os.getenv("MAX_STEPS", "60"))
        max_retries = int(os.getenv("MAX_RETRIES", "2"))
        no_progress_limit = int(os.getenv("NO_PROGRESS_LIMIT", "5"))

        screenshot_dir = Path(os.getenv("SCREENSHOT_DIR", "artifacts/screenshots"))
        trace_dir = Path(os.getenv("TRACE_DIR", "artifacts/traces"))
        trace_enabled = os.getenv("TRACE_ENABLED", "0").strip() == "1"

        ollama_api_key = os.getenv("OLLAMA_API_KEY")
        ollama_model = os.getenv("OLLAMA_MODEL", "")
        ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

        request_timeout_s = int(os.getenv("REQUEST_TIMEOUT_S", "180"))

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
            ollama_api_key=ollama_api_key,
            ollama_model=ollama_model,
            ollama_base_url=ollama_base_url,
            dry_run=dry_run,
            browser_user_data_dir=browser_user_data_dir,
            unsafe_browser_user_data_dir=unsafe_browser_user_data_dir,
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


def _resolve_unsafe_user_data_dir(
    value: Optional[str],
    browser_channel: Optional[str],
) -> Optional[Path]:
    if not value:
        return None
    raw = value.strip()
    if raw.lower() != "auto":
        return Path(raw)
    if not sys.platform.startswith("win"):
        return None
    channel = (browser_channel or _detect_default_browser_channel() or "").lower()
    if channel in {"chrome", "msedge", "brave"}:
        return _chromium_user_data_dir(channel)
    if channel == "firefox":
        return _firefox_profile_dir()
    return None


def _chromium_user_data_dir(channel: str) -> Optional[Path]:
    local = os.getenv("LOCALAPPDATA")
    if not local:
        return None
    if channel == "chrome":
        return Path(local) / "Google" / "Chrome" / "User Data"
    if channel == "msedge":
        return Path(local) / "Microsoft" / "Edge" / "User Data"
    if channel == "brave":
        return Path(local) / "BraveSoftware" / "Brave-Browser" / "User Data"
    return None


def _firefox_profile_dir() -> Optional[Path]:
    appdata = os.getenv("APPDATA")
    if not appdata:
        return None
    profiles_dir = Path(appdata) / "Mozilla" / "Firefox" / "Profiles"
    if not profiles_dir.exists():
        return None
    candidates = [path for path in profiles_dir.iterdir() if path.is_dir()]
    for suffix in (".default-release", ".default"):
        for candidate in candidates:
            if candidate.name.endswith(suffix):
                return candidate
    return candidates[0] if candidates else None


def _detect_default_browser_channel() -> Optional[str]:
    if not sys.platform.startswith("win") or winreg is None:
        return None
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\\Microsoft\\Windows\\Shell\\Associations\\UrlAssociations\\http\\UserChoice",
        ) as key:
            prog_id, _ = winreg.QueryValueEx(key, "ProgId")
    except OSError:
        return None
    prog_id = str(prog_id).lower()
    if "chromehtml" in prog_id or "chrome" in prog_id:
        return "chrome"
    if "msedge" in prog_id:
        return "msedge"
    if "firefox" in prog_id:
        return "firefox"
    return None
