[English](#browser-agent-mvp) | [Русская версия](#русская-версия)

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

- `LLM_PROVIDER=openai|anthropic|gemini|google|ollama|mock`

OpenAI-compatible config:

```
LLM_PROVIDER=openai
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-4.1-nano
```

Note: GPT-5 family models require `max_completion_tokens` and may reject `temperature`; the provider layer auto-adjusts these parameters.

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
GEMINI_MODEL=gemini-2.0-flash-lite
```

Gemini model availability is validated on task start via ListModels. If the model is not available or does not support generateContent, the API returns a 400 error with guidance.

Ollama (local) config:

```
LLM_PROVIDER=ollama
OLLAMA_MODEL=qwen3:1.7b
OLLAMA_BASE_URL=http://localhost:11434
```

Browser selection and search engine:

- `BROWSER_ENGINE=auto|chromium|firefox` (auto tries to use the OS default on Windows; falls back to Chromium)
- `BROWSER_CHANNEL=chrome|msedge` (optional, Chromium only; if empty and engine=auto, it is detected)
- `SEARCH_ENGINE_URL=https://www.google.com` (used when bootstrapping a search for browser-only tasks)
- `UNSAFE_BROWSER_USER_DATA_DIR=auto` to reuse the default browser profile (unsafe; may be blocked by some services). Close all browser windows before запуск.

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
- Visible text summary is capped (currently 2000 chars).
- Interactive elements are capped (35 by default, 80 for mail/inbox pages).
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

## Русская версия

Рабочий MVP автономного агента, который управляет видимым браузером Playwright, принимает текстовую задачу и выполняет цикл Observe -> Decide -> Act -> Reflect/Retry. Поддерживает persistent сессии, tool-driven действия LLM, защитный gate для опасных действий и live-логи через SSE.

## Архитектура

- Playwright (headful, persistent profile) для автоматизации реального браузера
- Провайдер-агностичный слой LLM (по умолчанию OpenAI-compatible, Anthropic опционально)
- Coordinator + под-агенты (Navigator, Extractor, Reflector)
- Реестр инструментов и исполняющий слой с security gate
- FastAPI backend с SSE логами
- Минимальный PHP UI для ввода промпта + live лог + confirm/stop

Persistent сессии хранятся в `.browser-data`, чтобы можно было войти один раз и переиспользовать сессию между запусками.

Структура проекта:

- agent/ - AI агент, управление браузером, память, инструменты
- app/ - FastAPI API и SSE
- web/ - PHP UI

## Почему так

- Playwright persistent context сохраняет куки и сессии между запусками.
- Accessibility-like snapshot: общий скан интерактивных элементов + summary видимого текста.
- Tool calling: LLM решает, какое действие выполнить; код их исполняет.
- Управление контекстом: суммаризация истории, отдельное хранение фактов, ограничение размера snapshot.
- Обработка ошибок: ретраи, режим reflection, скриншот при ошибках.
- Security layer: рискованные действия требуют явного подтверждения пользователя.

## Установка

Требования:

- Python 3.13
- PHP 8+ (для UI)

Версии:

- Python 3.13
- Версии пакетов фиксируются `requirements.txt` на момент установки.

Установка:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install
```

Настройка env:

```bash
cp .env.example .env
```

Укажите хотя бы один LLM ключ или включите dry-run.

Dry-run режим:

- Установите `DRY_RUN=1` или оставьте API ключи пустыми для запуска без доступа к LLM.

Выбор провайдера:

- `LLM_PROVIDER=openai|anthropic|gemini|google|ollama|mock`

OpenAI-compatible конфиг:

```
LLM_PROVIDER=openai
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-4.1-nano
```

Примечание: модели семейства GPT-5 требуют `max_completion_tokens` и могут отклонять `temperature`; слой провайдера подстраивает параметры автоматически.

Anthropic конфиг:

```
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=your_key_here
ANTHROPIC_MODEL=claude-3-5-sonnet-latest
```

Google AI Studio (Gemini) конфиг:

```
LLM_PROVIDER=gemini
GOOGLE_API_KEY=your_key_here
GEMINI_MODEL=gemini-2.0-flash-lite
```

Доступность модели Gemini проверяется на старте задачи через ListModels. Если модель недоступна или не поддерживает `generateContent`, API вернет 400 с подсказкой.

Ollama (local) конфиг:

```
LLM_PROVIDER=ollama
OLLAMA_MODEL=qwen3:1.7b
OLLAMA_BASE_URL=http://localhost:11434
```

Выбор браузера и поисковика:

- `BROWSER_ENGINE=auto|chromium|firefox` (auto пытается использовать браузер по умолчанию в Windows; при сбое — Chromium)
- `BROWSER_CHANNEL=chrome|msedge` (опционально, только Chromium; если пусто и engine=auto, определяется автоматически)
- `SEARCH_ENGINE_URL=https://www.google.com` (используется при bootstrap поиска для browser-only задач)
- `UNSAFE_BROWSER_USER_DATA_DIR=auto` чтобы использовать профиль браузера по умолчанию (небезопасный режим; некоторые сервисы могут блокировать такой вход). Перед запуском закройте все окна браузера.

## Запуск

Запуск API:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

Запуск UI:

```bash
php -S localhost:8000 -t web
```

Откройте http://localhost:8000 и отправьте задачу.

## Демо-задачи (публичные сайты, без логина)

1) "Open https://www.wikipedia.org, search for Ada Lovelace, and summarize 3 facts."
2) "Open https://news.ycombinator.com, open the top story, and summarize the first paragraph."

## Security gate

Действия, выглядящие как деструктивные или необратимые (delete, send, apply, pay, checkout и т.д.), требуют подтверждения. Агент ставит задачу на паузу, пишет краткий план действия и ждёт POST /tasks/{id}/confirm из UI.

## Управление контекстом и лимитами токенов

- Snapshot структурированный: url, title, summary видимого текста, ограниченный список интерактивных элементов.
- Summary видимого текста ограничен (сейчас 2000 символов).
- Интерактивные элементы ограничены (35 по умолчанию, 80 для почты/входящих).
- Краткосрочная память хранит последние шаги; старые шаги суммаризируются.
- Факты хранятся отдельно для дальнейшего использования.
- Полный DOM не отправляется в LLM.

## Обработка ошибок

- Лимит ретраев с переходом в reflector-режим.
- Скриншот сохраняется при ошибках.
- Прогресс-гард для обнаружения зацикливания и смены стратегии.

## Провайдеры LLM и стоимость

- По умолчанию: OpenAI-compatible API (платный; см. https://platform.openai.com/docs).
- Опционально: Anthropic API (платный; см. https://docs.anthropic.com).
- Опционально: Google AI Studio / Gemini API (цены и квоты зависят от аккаунта; см. https://ai.google.dev/gemini-api/docs).
- Бесплатные варианты: используйте бесплатный OpenAI-compatible провайдер, если доступен, или локальную модель с OpenAI-compatible сервером (например, LM Studio, Ollama). Лимиты бесплатных тарифов меняются — проверяйте в документации провайдера.
- Dry-run работает без ключа (агент завершит задачу с сообщением).

## Документация и ссылки

- OpenAI Chat Completions tool calling: https://platform.openai.com/docs
- Anthropic Messages API: https://docs.anthropic.com
- Playwright Python: https://playwright.dev/python

## Использованные AI-инструменты

Этот MVP был собран с помощью Codex CLI как ассистента разработчика. Промпты, архитектура и ревью проходили через ассистента и затем проверялись локально.

## Компромиссы из-за 3-дневного дедлайна

- Одновременно поддерживается только одна активная задача из-за общего persistent профиля браузера.
- Эвристическое определение прогресса и security matching.
- Минимальный UI и ограниченная обработка пользовательского ввода (confirm продолжает как подтверждения, так и ручные шаги).

## Ограничения

- Нет обхода капчи или 2FA; агент ставит задачу на паузу и ждёт ручного действия.
- Поведение зависит от структуры страницы и качества LLM, возможна недетерминированность.
- Список ключевых слов для безопасности ориентирован на английский (включает небольшой набор русских).
- Точность извлечения данных зависит от LLM; проверяйте перед необратимыми действиями.

## Улучшения дальше

- Планировщик с изолированными профилями браузера для параллельных задач.
- Более качественное ранжирование элементов и accessiblity-маппинг.
- Структурированный ввод для форм и учётных данных (без хранения секретов).
- Более надёжная обработка попапов и диалогов на разных сайтах.
