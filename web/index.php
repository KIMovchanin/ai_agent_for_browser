<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Browser Agent MVP</title>
  <link rel="stylesheet" href="styles.css" />
</head>
<body>
  <div class="container">
    <div class="header">
      <div class="title-block">
        <h1 data-i18n="title">Browser Agent MVP</h1>
        <p class="hint" data-i18n="hint">Enter a multi-step task and watch the browser.</p>
      </div>
      <div class="header-actions">
        <button id="lang-toggle" class="lang-toggle" type="button" aria-label="Language">
          <span data-lang="ru">RU</span>
          <span class="divider">/</span>
          <span data-lang="en">EN</span>
        </button>
        <button id="settings-button" class="icon-button" aria-label="Settings">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7Zm8.94 2.52-1.72-.7a7.36 7.36 0 0 0-.6-1.44l.76-1.7a.9.9 0 0 0-.2-.98l-1.43-1.43a.9.9 0 0 0-.98-.2l-1.7.76c-.46-.26-.95-.48-1.44-.6l-.7-1.72a.9.9 0 0 0-.84-.57h-2.02a.9.9 0 0 0-.84.57l-.7 1.72c-.5.12-.98.34-1.44.6l-1.7-.76a.9.9 0 0 0-.98.2L4.82 6.2a.9.9 0 0 0-.2.98l.76 1.7c-.26.46-.48.95-.6 1.44l-1.72.7a.9.9 0 0 0-.57.84v2.02c0 .37.22.7.57.84l1.72.7c.12.5.34.98.6 1.44l-.76 1.7a.9.9 0 0 0 .2.98l1.43 1.43c.26.26.64.34.98.2l1.7-.76c.46.26.95.48 1.44.6l.7 1.72c.14.35.47.57.84.57h2.02c.37 0 .7-.22.84-.57l.7-1.72c.5-.12.98-.34 1.44-.6l1.7.76c.34.14.72.06.98-.2l1.43-1.43c.26-.26.34-.64.2-.98l-.76-1.7c.26-.46.48-.95.6-1.44l1.72-.7c.35-.14.57-.47.57-.84v-2.02a.9.9 0 0 0-.57-.84Z"/>
          </svg>
        </button>
      </div>
      <div id="settings-panel" class="settings-panel">
        <div class="settings-title" data-i18n="settings_title">Settings</div>
        <div class="settings-group">
          <div class="settings-label" data-i18n="label_theme">Theme</div>
          <div class="theme-toggle">
            <button class="theme-btn" data-theme="light" data-i18n="theme_light">Light</button>
            <button class="theme-btn" data-theme="dark" data-i18n="theme_dark">Dark</button>
          </div>
        </div>
        <div class="settings-group">
          <label class="field">
            <span data-i18n="label_search_engine">Search engine</span>
            <select id="search-engine">
              <option value="google">Google</option>
              <option value="duckduckgo">DuckDuckGo</option>
              <option value="bing">Bing</option>
              <option value="yandex">Yandex</option>
            </select>
          </label>
        </div>
        <div class="settings-group">
          <label class="field">
            <span data-i18n="label_provider">LLM provider</span>
            <select id="provider-select">
              <option value="gemini">Google (Gemini)</option>
              <option value="openai">OpenAI</option>
              <option value="ollama">Local (Ollama)</option>
              <option value="anthropic">Anthropic</option>
            </select>
          </label>
        </div>
        <div class="settings-group">
          <label class="field">
            <span data-i18n="label_model">Model</span>
            <select id="model-select">
              <option value="gemini-2.0-flash-lite">gemini-2.0-flash-lite</option>
              <option value="gemini-2.5-flash-lite">gemini-2.5-flash-lite</option>
            </select>
          </label>
        </div>
        <div class="settings-group">
          <div class="settings-row">
            <label class="switch">
              <input type="checkbox" id="safe-mode" checked />
              <span class="slider"></span>
            </label>
            <span class="toggle-text" data-i18n="label_safe_mode">Safe mode</span>
            <span class="tooltip" data-i18n-tooltip="tooltip_safe_mode" data-tooltip="Safe: isolated .browser-data profile, no logins. Unsafe: uses your browser profile (set UNSAFE_BROWSER_USER_DATA_DIR in .env, browser must be closed). Risk of profile corruption.">?</span>
          </div>
          <div class="settings-row">
            <label class="switch">
              <input type="checkbox" id="browser-only" checked />
              <span class="slider"></span>
            </label>
            <span class="toggle-text" data-i18n="label_browser_only">Browser-only</span>
            <span class="tooltip" data-i18n-tooltip="tooltip_browser_only" data-tooltip="When enabled, the agent acts only via the browser. When disabled, it can answer directly in the console if no explicit browser task is given.">?</span>
          </div>
        </div>
      </div>
    </div>
    <div class="tabs">
      <button class="tab active" data-tab="agent" data-i18n="tab_agent">Agent</button>
      <button class="tab" data-tab="models" data-i18n="tab_models">Models</button>
    </div>
    <div id="tab-agent" class="tab-panel active">
      <textarea id="prompt" rows="5" data-i18n-placeholder="prompt_placeholder" placeholder="Example: Open wikipedia.org, search for Ada Lovelace, summarize 3 facts."></textarea>
      <div class="controls">
        <button id="run" data-i18n="button_run">Run</button>
        <button id="confirm" disabled data-i18n="button_confirm">Confirm / Continue</button>
        <button id="stop" disabled data-i18n="button_stop">Stop</button>
      </div>
      <div class="status" id="status" data-i18n="status_idle">Idle</div>
      <pre id="log"></pre>
      <div id="user-reply" class="user-reply hidden">
        <label class="field">
          <span data-i18n="label_user_reply">User reply</span>
          <input type="text" id="user-reply-input" data-i18n-placeholder="user_reply_placeholder" placeholder="Type your reply here." />
        </label>
        <div class="user-reply-hint" data-i18n="hint_user_reply">
          Type your reply and click Confirm / Continue.
        </div>
      </div>
    </div>
    <div id="tab-models" class="tab-panel">
      <p class="hint">Keys are used only to fetch model lists and are not stored.</p>
      <div class="provider-tabs">
        <button class="provider-tab active" data-provider="openai">OpenAI</button>
        <button class="provider-tab" data-provider="anthropic">Anthropic</button>
        <button class="provider-tab" data-provider="google">Google</button>
      </div>
      <div id="provider-openai" class="provider-panel active">
        <label class="field">
          <span>OpenAI API Key</span>
          <input type="password" id="openai-key" placeholder="sk-..." />
        </label>
        <label class="field">
          <span>Base URL (optional)</span>
          <input type="text" id="openai-base" placeholder="https://api.openai.com" />
        </label>
        <button class="fetch-models" data-provider="openai">Fetch Models</button>
        <pre class="models-output" id="openai-models"></pre>
      </div>
      <div id="provider-anthropic" class="provider-panel">
        <label class="field">
          <span>Anthropic API Key</span>
          <input type="password" id="anthropic-key" placeholder="sk-ant-..." />
        </label>
        <label class="field">
          <span>Base URL (optional)</span>
          <input type="text" id="anthropic-base" placeholder="https://api.anthropic.com" />
        </label>
        <button class="fetch-models" data-provider="anthropic">Fetch Models</button>
        <pre class="models-output" id="anthropic-models"></pre>
      </div>
      <div id="provider-google" class="provider-panel">
        <label class="field">
          <span>Google API Key</span>
          <input type="password" id="google-key" placeholder="AIza..." />
        </label>
        <label class="field">
          <span>Base URL (optional)</span>
          <input type="text" id="google-base" placeholder="https://generativelanguage.googleapis.com" />
        </label>
        <button class="fetch-models" data-provider="google">Fetch Models</button>
        <pre class="models-output" id="google-models"></pre>
      </div>
    </div>
  </div>
  <script src="app.js"></script>
</body>
</html>
