from __future__ import annotations

import sys
import time
from typing import Any, Dict, Optional, Tuple

try:
    import winreg  # type: ignore
except ImportError:  # pragma: no cover - non-Windows
    winreg = None

from playwright.sync_api import Page, sync_playwright

from ..config import Settings
from .snapshot import build_snapshot


class BrowserController:
    def __init__(self, settings: Settings, start_new_window: bool = True) -> None:
        self.settings = settings
        self.settings.ensure_dirs()
        self.playwright = sync_playwright().start()
        engine, channel = self._resolve_browser_config()
        browser_type = getattr(self.playwright, engine, self.playwright.chromium)
        launch_kwargs = {
            "user_data_dir": str(self.settings.browser_user_data_dir),
            "headless": self.settings.browser_headless,
            "slow_mo": self.settings.browser_slow_mo_ms,
            "viewport": {"width": 1280, "height": 720},
        }
        if engine == "chromium" and channel:
            launch_kwargs["channel"] = channel

        try:
            self.context = browser_type.launch_persistent_context(**launch_kwargs)
        except Exception:
            if engine == "chromium" and channel:
                launch_kwargs.pop("channel", None)
                self.context = self.playwright.chromium.launch_persistent_context(**launch_kwargs)
            else:
                raise
        if start_new_window:
            self.page = self.context.new_page()
            self.page.bring_to_front()
        elif self.context.pages:
            self.page = self.context.pages[0]
        else:
            self.page = self.context.new_page()

        self.last_snapshot: Optional[Dict[str, Any]] = None
        if self.settings.trace_enabled:
            self.context.tracing.start(screenshots=True, snapshots=True, sources=True)

    def _resolve_browser_config(self) -> Tuple[str, Optional[str]]:
        engine = (self.settings.browser_engine or "chromium").strip().lower()
        channel = self.settings.browser_channel

        if engine == "auto":
            detected_engine, detected_channel = self._detect_default_browser()
            if not channel:
                channel = detected_channel
            engine = detected_engine

        if engine not in {"chromium", "firefox"}:
            engine = "chromium"
        if engine != "chromium":
            channel = None
        return engine, channel

    def _detect_default_browser(self) -> Tuple[str, Optional[str]]:
        if not sys.platform.startswith("win") or winreg is None:
            return "chromium", None

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\\Microsoft\\Windows\\Shell\\Associations\\UrlAssociations\\http\\UserChoice",
            ) as key:
                prog_id, _ = winreg.QueryValueEx(key, "ProgId")
        except OSError:
            return "chromium", None

        prog_id = str(prog_id).lower()
        if "chromehtml" in prog_id or "chrome" in prog_id:
            return "chromium", "chrome"
        if "msedge" in prog_id:
            return "chromium", "msedge"
        if "firefox" in prog_id:
            return "firefox", None
        return "chromium", None

    def close(self) -> None:
        try:
            if self.settings.trace_enabled:
                self.context.tracing.stop()
        finally:
            self.context.close()
            self.playwright.stop()

    def snapshot(self) -> Dict[str, Any]:
        snapshot = build_snapshot(self.page)
        self.last_snapshot = snapshot
        return snapshot

    def navigate(self, url: str) -> None:
        self.page.goto(url, wait_until="domcontentloaded")

    def back(self) -> None:
        self.page.go_back(wait_until="domcontentloaded")

    def forward(self) -> None:
        self.page.go_forward(wait_until="domcontentloaded")

    def wait(self, ms: int) -> None:
        time.sleep(max(ms, 0) / 1000.0)

    def wait_for_network_idle(self) -> None:
        self.page.wait_for_load_state("networkidle")

    def scroll(self, direction: str, amount: int) -> None:
        delta = max(amount, 1)
        if direction.lower() == "up":
            delta = -delta
        self.page.mouse.wheel(0, delta)

    def click(self, element: Dict[str, Any]) -> None:
        bbox = element.get("bbox")
        if not bbox:
            raise ValueError("Missing bbox for element")
        x = bbox["x"] + max(1, bbox["width"] // 2)
        y = bbox["y"] + max(1, bbox["height"] // 2)
        self.page.mouse.click(x, y)

    def type(self, element: Dict[str, Any], text: str, press_enter: bool = False) -> None:
        self.click(element)
        self.page.keyboard.type(text, delay=20)
        if press_enter:
            self.page.keyboard.press("Enter")

    def take_screenshot(self, path: str) -> None:
        self.page.screenshot(path=path, full_page=True)

    def save_trace(self, path: str) -> None:
        if not self.settings.trace_enabled:
            self.context.tracing.start(screenshots=True, snapshots=True, sources=True)
            self.settings.trace_enabled = True
        self.context.tracing.stop(path=path)
        self.context.tracing.start(screenshots=True, snapshots=True, sources=True)

    def resolve_element(
        self, element_id: Optional[str] = None, strategy: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        if not self.last_snapshot:
            raise ValueError("No snapshot available")
        elements = self.last_snapshot.get("interactive_elements", [])
        if element_id:
            for element in elements:
                if str(element.get("id")) == str(element_id):
                    return element
            raise ValueError(f"Element id {element_id} not found")

        if not strategy:
            raise ValueError("Missing element_id or strategy")

        target_text = (strategy.get("text") or "").lower()
        target_role = (strategy.get("role") or "").lower()
        target_name = (strategy.get("name") or "").lower()

        best_score = -1
        best_element = None
        for element in elements:
            score = 0
            role = (element.get("role") or "").lower()
            name = (element.get("name") or "").lower()
            text = (element.get("text") or "").lower()
            aria = (element.get("aria_label") or "").lower()

            if target_role and target_role == role:
                score += 3
            if target_name and target_name in name:
                score += 3
            if target_text and target_text in text:
                score += 2
            if target_text and target_text in aria:
                score += 2
            if target_name and target_name in aria:
                score += 1

            if score > best_score:
                best_score = score
                best_element = element

        if not best_element:
            raise ValueError("No element matched strategy")
        return best_element

    def current_page(self) -> Page:
        return self.page
