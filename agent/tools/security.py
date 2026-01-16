from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple


class SecurityPolicy:
    def __init__(self) -> None:
        keywords = [
            "delete",
            "remove",
            "trash",
            "spam",
            "unsubscribe",
            "send",
            "submit",
            "apply",
            "respond",
            "checkout",
            "pay",
            "payment",
            "purchase",
            "buy",
            "order",
            "confirm",
            "approve",
            "publish",
            "save changes",
            "update settings",
            "place order",
            "sign up",
            "register",
            "withdraw",
            "transfer",
            "delete account",
            "close account",
            "cancel subscription",
            "remove account",
            "close",
            "drop",
            "erase",
            "wipe",
            "ban",
            "block",
            "report",
            "decline",
            "approve",
            "accept",
            "finalize",
            "complete",
            "charge",
            "donate",
            "pay now",
            "send now",
            "apply now",
            "submit now",
            "confirm order",
            "confirm payment",
            "confirm purchase",
            "confirm deletion",
            "confirm removal",
            "confirm submit",
            "confirm send",
            "confirm apply",
            "confirm checkout",
            "confirm purchase",
            "confirm pay",
            "confirm order",
        ]
        # Russian keywords via unicode escapes to keep ASCII source.
        keywords += [
            "\u0443\u0434\u0430\u043b\u0438\u0442\u044c",  # удалить
            "\u0443\u0434\u0430\u043b\u0435\u043d\u0438\u0435",  # удаление
            "\u0441\u043f\u0430\u043c",  # спам
            "\u043e\u0442\u043f\u0440\u0430\u0432\u0438\u0442\u044c",  # отправить
            "\u043e\u0442\u043a\u043b\u0438\u043a\u043d\u0443\u0442\u044c\u0441\u044f",  # откликнуться
            "\u043e\u043f\u043b\u0430\u0442\u0438\u0442\u044c",  # оплатить
            "\u0437\u0430\u043a\u0430\u0437\u0430\u0442\u044c",  # заказать
            "\u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0434\u0438\u0442\u044c",  # подтвердить
            "\u043a\u0443\u043f\u0438\u0442\u044c",  # купить
        ]
        escaped = [re.escape(word) for word in keywords]
        pattern = "|".join(escaped)
        self._regex = re.compile(pattern, re.IGNORECASE)

    def needs_confirmation(
        self, tool_name: str, args: Dict[str, Any], snapshot: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        if tool_name not in {"click", "type"}:
            return False, None

        target_text = self._target_text(args, snapshot)
        if not target_text:
            return False, None
        if self._regex.search(target_text):
            return True, target_text
        return False, None

    def _target_text(self, args: Dict[str, Any], snapshot: Dict[str, Any]) -> str:
        element_id = args.get("element_id")
        strategy = args.get("click_strategy") or {}

        parts = []
        if element_id:
            for element in snapshot.get("interactive_elements", []):
                if str(element.get("id")) == str(element_id):
                    parts.extend(
                        [
                            str(element.get("name", "")),
                            str(element.get("text", "")),
                            str(element.get("aria_label", "")),
                        ]
                    )
                    break
        parts.extend(
            [
                str(strategy.get("text", "")),
                str(strategy.get("name", "")),
                str(strategy.get("role", "")),
            ]
        )
        return " ".join(part for part in parts if part).strip()
