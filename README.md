# Browser Agent MVP

Working MVP of an autonomous browser agent that controls a visible Playwright browser, accepts a text task, and loops Observe -> Decide -> Act -> Reflect/Retry. It supports persistent sessions, tool-driven LLM actions, security gating, and live logs over SSE.

## Architecture

- Playwright (headful, persistent profile) for real browser automation
- Provider-agnostic LLM layer (OpenAI-compatible by default, Anthropic optional)
- Coordinator + sub-agents (Navigator, Extractor, Reflector)
- Tool registry and execution layer with security gate
- FastAPI backend with SSE logs
- Minimal PHP UI for prompt + live log + confirm/stop

Persistent sessions are stored in `.browser-data` so you can log in once and reuse the session across runs.

Project structure:

- agent/ - AI agent, browser control, memory, tools
- app/ - FastAPI API and SSE
- web/ - PHP UI

## Why this approach

- Playwright persistent context preserves cookies and sessions between runs.
- Accessibility-ish snapshot: generic interactive element scan + visible text summary.
- Tool calling: the LLM decides actions; the code executes them.
- Context management: summarize long histories, store facts separately, cap snapshot size.
- Error handling: retries, reflection mode, and screenshot on failures.
- Security layer: risky actions require explicit user confirmation.

## Setup

Requirements:

- Python 3.13
- PHP 8+ (for the UI)

Versions:

- Python 3.13
- Package versions are controlled by `requirements.txt` at install time.

Install:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install
```

Configure env:

```bash
cp .env.example .env
```

Set at least one LLM key or enable dry-run.

Dry-run mode:

- Set `DRY_RUN=1` or leave API keys empty to run without LLM access.

Provider selection:

- `LLM_PROVIDER=openai|anthropic|gemini|google|mock`

OpenAI-compatible config:

```
LLM_PROVIDER=openai
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=o4-mini
```

Anthropic config:

```
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=your_key_here
ANTHROPIC_MODEL=claude-3-5-sonnet-latest
```

Google AI Studio (Gemini) config:

```
LLM_PROVIDER=gemini
GOOGLE_API_KEY=your_key_here
GEMINI_MODEL=gemini-2.5-flash-lite
```

Gemini model availability is validated on task start via ListModels. If the model is not available or does not support generateContent, the API returns a 400 error with guidance.

Browser selection and search engine:

- `BROWSER_ENGINE=auto|chromium|firefox` (auto tries to use the OS default on Windows; falls back to Chromium)
- `BROWSER_CHANNEL=chrome|msedge` (optional, Chromium only)
- `SEARCH_ENGINE_URL=https://www.google.com` (used when bootstrapping a search for browser-only tasks)

## Run

Start API:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

Start UI:

```bash
php -S localhost:8000 -t web
```

Open http://localhost:8000 and submit a task.

## Demo tasks (public sites, no login)

1) "Open https://www.wikipedia.org, search for Ada Lovelace, and summarize 3 facts."
2) "Open https://news.ycombinator.com, open the top story, and summarize the first paragraph."

## Security gate

Actions that look destructive or irreversible (delete, send, apply, pay, checkout, etc.) trigger a confirmation event. The agent pauses, logs the planned action, and waits for POST /tasks/{id}/confirm from the UI.

## Context + token constraints

- Snapshot is structured: url, title, visible text summary, and limited interactive elements.
- Short-term memory stores recent steps; older steps are summarized.
- Facts are stored separately for reuse in later reasoning.
- No full DOM dumps are sent to the LLM.

## Error handling

- Retry limit with escalating reflector mode.
- Screenshot saved on errors.
- Progress guard to detect stalls and switch strategy.

## LLM providers and cost

- Default: OpenAI-compatible API (paid; see https://platform.openai.com/docs).
- Optional: Anthropic API (paid; see https://docs.anthropic.com).
- Optional: Google AI Studio / Gemini API (pricing and quotas vary; see https://ai.google.dev/gemini-api/docs).
- Free options: use a free-tier OpenAI-compatible provider if available, or run a local model with an OpenAI-compatible server (e.g., LM Studio, Ollama). Free tier limits vary by provider and can change; check provider docs.
- Dry-run mode works without any key (agent will finish immediately with a message).

## Notes on tools and docs

- OpenAI Chat Completions tool calling: https://platform.openai.com/docs
- Anthropic Messages API: https://docs.anthropic.com
- Playwright Python: https://playwright.dev/python

## AI tooling used

This MVP was built with Codex CLI as the coding assistant. Prompts, architecture choices, and code reviews were performed via the assistant and then validated locally.

## Trade-offs due to 3-day timeline

- Single active task at a time due to shared persistent browser profile.
- Heuristic progress detection and security matching.
- Minimal UI and limited input handling (confirm resumes both confirmations and manual steps).

## Limitations

- No captcha or 2FA bypass; it will pause and ask for manual completion.
- Non-deterministic behavior depending on page structure and LLM quality.
- English-centric safety keyword list (includes a small set of Russian keywords).
- LLM extraction accuracy varies; verify before taking irreversible actions.

## Next improvements

- Multi-task scheduling with isolated browser profiles.
- Better element ranking and accessibility mapping.
- Structured user inputs for forms and credentials (without storing secrets).
- More robust per-site pop-up handling and dialog dismissal.
