from __future__ import annotations

import re
from typing import Any, Dict, List

from playwright.sync_api import Page


INTERACTIVE_SELECTORS = (
    "a, button, input, textarea, select, option, "
    "[role='button'], [role='link'], [role='textbox'], [role='menuitem'], "
    "[role='option'], [contenteditable='true']"
)


def _collapse_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _safe_text(text: str, max_chars: int) -> str:
    text = _collapse_whitespace(text)
    if len(text) > max_chars:
        return text[: max_chars - 3] + "..."
    return text


def _infer_role(tag: str) -> str:
    if tag == "a":
        return "link"
    if tag == "button":
        return "button"
    if tag in {"input", "textarea", "select"}:
        return "input"
    return "generic"


def _element_name(text: str, aria_label: str, placeholder: str, name_attr: str) -> str:
    for value in (aria_label, text, placeholder, name_attr):
        if value:
            return value
    return ""


def build_snapshot(page: Page, max_elements: int = 60, max_text_chars: int = 2500) -> Dict[str, Any]:
    visible_text = ""
    try:
        visible_text = page.evaluate(
            "() => document.body ? document.body.innerText || '' : ''"
        )
    except Exception:
        visible_text = ""

    visible_text_summary = _safe_text(visible_text, max_text_chars)

    elements: List[Dict[str, Any]] = []
    try:
        raw_elements = page.query_selector_all(INTERACTIVE_SELECTORS)
    except Exception:
        raw_elements = []

    for handle in raw_elements:
        try:
            if not handle.is_visible():
                continue
            box = handle.bounding_box()
            if not box or box.get("width", 0) < 2 or box.get("height", 0) < 2:
                continue

            tag = (handle.evaluate("e => e.tagName.toLowerCase()") or "").strip()
            text = ""
            try:
                text = handle.inner_text() or ""
            except Exception:
                text = handle.text_content() or ""

            aria_label = handle.get_attribute("aria-label") or ""
            placeholder = handle.get_attribute("placeholder") or ""
            name_attr = handle.get_attribute("name") or ""
            role = handle.get_attribute("role") or _infer_role(tag)
            name = _element_name(text, aria_label, placeholder, name_attr)

            elements.append(
                {
                    "role": role,
                    "name": _safe_text(name, 160),
                    "aria_label": _safe_text(aria_label, 160),
                    "text": _safe_text(text, 160),
                    "bbox": {
                        "x": int(box["x"]),
                        "y": int(box["y"]),
                        "width": int(box["width"]),
                        "height": int(box["height"]),
                    },
                }
            )
        except Exception:
            continue

    elements.sort(key=lambda item: (item["bbox"]["y"], item["bbox"]["x"]))
    elements = elements[:max_elements]

    interactive_elements = []
    for idx, element in enumerate(elements, start=1):
        element["id"] = str(idx)
        interactive_elements.append(element)

    possible_popups = []
    try:
        popup_handles = page.query_selector_all("[role='dialog'], [aria-modal='true']")
        for handle in popup_handles[:3]:
            try:
                text = handle.inner_text() or ""
            except Exception:
                text = handle.text_content() or ""
            if text:
                possible_popups.append(_safe_text(text, 180))
    except Exception:
        pass

    snapshot = {
        "url": page.url,
        "title": page.title(),
        "visible_text_summary": visible_text_summary,
        "interactive_elements": interactive_elements,
        "warnings": [],
        "possible_popups": possible_popups,
    }
    if possible_popups:
        snapshot["warnings"].append("Possible popup/dialog detected")

    return snapshot
