import os
import sys

import httpx


def main() -> int:
    # Option 1 (recommended): export GOOGLE_API_KEY in your shell.
    # api_key = os.getenv("GOOGLE_API_KEY")

    # Option 2: paste the key here if you must (do not commit it).
    api_key = "AIzaSyCbI5yTQwtT7787ZFoT8xndahnQw_oPmq0"

    if not api_key:
        print("Missing GOOGLE_API_KEY. Set env var or paste into testAPI_gemini.py.")
        return 1

    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
    base_url = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com")
    base_url = base_url.rstrip("/")
    url = f"{base_url}/v1beta/models/{model}:generateContent?key={api_key}"

    payload = {
        "contents": [
            {"role": "user", "parts": [{"text": "ping"}]}
        ],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 20},
    }

    headers = {"Content-Type": "application/json"}

    try:
        response = httpx.post(url, headers=headers, json=payload, timeout=30)
    except httpx.HTTPError as exc:
        print(f"Request failed: {exc}")
        return 1

    print(f"Status: {response.status_code}")
    print(response.text[:1000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
