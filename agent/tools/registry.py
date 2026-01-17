from __future__ import annotations

from typing import Any, Dict, List


def tool_definitions() -> List[Dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "navigate",
                "description": "Navigate the browser to a URL.",
                "parameters": {
                    "type": "object",
                    "properties": {"url": {"type": "string"}},
                    "required": ["url"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "snapshot",
                "description": "Capture a structured snapshot of the page.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "click",
                "description": "Click an element by element_id or strategy.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "element_id": {"type": "string"},
                        "click_strategy": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string"},
                                "role": {"type": "string"},
                                "name": {"type": "string"},
                            },
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "type",
                "description": "Type text into an element.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "element_id": {"type": "string"},
                        "text": {"type": "string"},
                        "press_enter": {"type": "boolean"},
                        "click_strategy": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string"},
                                "role": {"type": "string"},
                                "name": {"type": "string"},
                            },
                        },
                    },
                    "required": ["text"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "scroll",
                "description": "Scroll the page.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "direction": {"type": "string", "enum": ["up", "down"]},
                        "amount": {"type": "integer"},
                    },
                    "required": ["direction", "amount"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "wait",
                "description": "Wait for a fixed delay.",
                "parameters": {
                    "type": "object",
                    "properties": {"ms": {"type": "integer"}},
                    "required": ["ms"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "wait_for_network_idle",
                "description": "Wait until the network is idle.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "back",
                "description": "Navigate back.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "forward",
                "description": "Navigate forward.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "extract",
                "description": "Extract structured data based on a schema.",
                "parameters": {
                    "type": "object",
                    "properties": {"schema": {"type": "string"}},
                    "required": ["schema"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "ask_user",
                "description": "Ask the user for manual input. Provide 2-3 short numbered options the user can choose from.",
                "parameters": {
                    "type": "object",
                    "properties": {"question": {"type": "string"}},
                    "required": ["question"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "finish",
                "description": "Finish the task with a result summary.",
                "parameters": {
                    "type": "object",
                    "properties": {"result": {"type": "string"}},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "take_screenshot",
                "description": "Capture a screenshot to artifacts.",
                "parameters": {
                    "type": "object",
                    "properties": {"label": {"type": "string"}},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "save_trace",
                "description": "Save a Playwright trace.",
                "parameters": {
                    "type": "object",
                    "properties": {"label": {"type": "string"}},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "stop_task",
                "description": "Stop the task safely.",
                "parameters": {
                    "type": "object",
                    "properties": {"reason": {"type": "string"}},
                },
            },
        },
    ]
