const API_BASE = 'http://localhost:8080';

const promptEl = document.getElementById('prompt');
const runBtn = document.getElementById('run');
const confirmBtn = document.getElementById('confirm');
const stopBtn = document.getElementById('stop');
const statusEl = document.getElementById('status');
const logEl = document.getElementById('log');
const browserOnlyEl = document.getElementById('browser-only');
const searchEngineEl = document.getElementById('search-engine');
const providerEl = document.getElementById('provider-select');
const modelEl = document.getElementById('model-select');
const safeModeEl = document.getElementById('safe-mode');
const settingsButton = document.getElementById('settings-button');
const settingsPanel = document.getElementById('settings-panel');
const themeButtons = document.querySelectorAll('.theme-btn');
const langToggle = document.getElementById('lang-toggle');
const langSpans = langToggle ? langToggle.querySelectorAll('[data-lang]') : [];
const userReplyWrap = document.getElementById('user-reply');
const userReplyInput = document.getElementById('user-reply-input');

const tabs = document.querySelectorAll('.tab');
const tabPanels = document.querySelectorAll('.tab-panel');
const providerTabs = document.querySelectorAll('.provider-tab');
const providerPanels = document.querySelectorAll('.provider-panel');

const providerConfig = {
  openai: {
    endpoint: '/providers/openai/models',
    keyInput: 'openai-key',
    baseInput: 'openai-base',
    output: 'openai-models',
  },
  anthropic: {
    endpoint: '/providers/anthropic/models',
    keyInput: 'anthropic-key',
    baseInput: 'anthropic-base',
    output: 'anthropic-models',
  },
  google: {
    endpoint: '/providers/gemini/models',
    keyInput: 'google-key',
    baseInput: 'google-base',
    output: 'google-models',
  },
};

let eventSource = null;
let taskId = null;
let currentLang = 'ru';
let waitingForUserInput = false;

const MODEL_OPTIONS = {
  gemini: ['gemini-2.0-flash-lite', 'gemini-2.5-flash-lite'],
  openai: ['gpt-4.1-nano', 'gpt-4.1-mini', 'gpt-4.1'],
  ollama: ['qwen3:1.7b', 'functiongemma:latest'],
  anthropic: ['claude-3-5-sonnet-latest', 'claude-3-5-haiku-latest'],
};

const I18N = {
  en: {
    title: 'Browser Agent MVP',
    hint: 'Enter a multi-step task and watch the browser.',
    settings_title: 'Settings',
    label_theme: 'Theme',
    theme_light: 'Light',
    theme_dark: 'Dark',
    label_search_engine: 'Search engine',
    label_provider: 'LLM provider',
    label_model: 'Model',
    label_safe_mode: 'Safe mode',
    label_browser_only: 'Browser-only',
    tooltip_safe_mode:
      'Safe: isolated .browser-data profile, no logins. Unsafe: uses your browser profile (set UNSAFE_BROWSER_USER_DATA_DIR in .env, browser must be closed). Risk of profile corruption.',
    tooltip_browser_only:
      'When enabled, the agent acts only via the browser. When disabled, it can answer directly in the console if no explicit browser task is given.',
    tab_agent: 'Agent',
    tab_models: 'Models',
    button_run: 'Run',
    button_confirm: 'Confirm / Continue',
    button_stop: 'Stop',
    status_idle: 'Idle',
    status_starting: 'Starting task...',
    status_wait_confirm: 'Waiting for confirmation',
    status_wait_user: 'Waiting for user input',
    status_prefix: 'Status:',
    status_running: 'running',
    status_waiting_confirm: 'waiting_confirm',
    status_waiting_user: 'waiting_user',
    status_done: 'done',
    status_stopped: 'stopped',
    status_error: 'error',
    status_queued: 'queued',
    prompt_placeholder: 'Example: Open wikipedia.org, search for Ada Lovelace, summarize 3 facts.',
    log_confirm: 'CONFIRM REQUIRED',
    log_user_input: 'USER INPUT NEEDED',
    log_result: 'RESULT',
    log_event_error: 'Event stream error or closed.',
    log_failed_start: 'Failed to start',
    alert_enter_task: 'Enter a task prompt.',
    label_user_reply: 'User reply',
    hint_user_reply: 'Type your reply and click Confirm / Continue.',
    user_reply_placeholder: 'Type your reply here.',
    alert_enter_reply: 'Enter a reply for the agent.',
    action_navigate: 'navigating',
    action_click: 'clicking',
    action_type: 'typing',
    action_extract: 'analyzing',
    action_snapshot: 'scanning',
    action_scroll: 'scrolling',
    action_wait: 'waiting',
    action_back: 'back',
    action_forward: 'forward',
    action_ask_user: 'asking',
    action_finish: 'finishing',
    action_stop_task: 'stopping',
    action_take_screenshot: 'screenshot',
    action_save_trace: 'tracing',
    action_think: 'thinking',
    action_access: 'blocked',
    action_loop_guard: 'stuck',
    action_user_input: 'reply',
    action_tokens: 'tokens',
    action_guard: 'rerouting',
  },
  ru: {
    title: 'Browser Agent MVP',
    hint: '\u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u0437\u0430\u0434\u0430\u0447\u0443 \u0438 \u043d\u0430\u0431\u043b\u044e\u0434\u0430\u0439\u0442\u0435 \u0437\u0430 \u0431\u0440\u0430\u0443\u0437\u0435\u0440\u043e\u043c.',
    settings_title: '\u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438',
    label_theme: '\u0422\u0435\u043c\u0430',
    theme_light: '\u0421\u0432\u0435\u0442\u043b\u0430\u044f',
    theme_dark: '\u0422\u0435\u043c\u043d\u0430\u044f',
    label_search_engine: '\u041f\u043e\u0438\u0441\u043a\u043e\u0432\u0438\u043a',
    label_provider: '\u041f\u0440\u043e\u0432\u0430\u0439\u0434\u0435\u0440 LLM',
    label_model: '\u041c\u043e\u0434\u0435\u043b\u044c',
    label_safe_mode: '\u0411\u0435\u0437\u043e\u043f\u0430\u0441\u043d\u0430\u044f \u0440\u0430\u0431\u043e\u0442\u0430',
    label_browser_only: '\u0422\u043e\u043b\u044c\u043a\u043e \u0431\u0440\u0430\u0443\u0437\u0435\u0440',
    tooltip_safe_mode:
      '\u0412\u043a\u043b: \u0438\u0437\u043e\u043b\u0438\u0440\u043e\u0432\u0430\u043d\u043d\u044b\u0439 \u043f\u0440\u043e\u0444\u0438\u043b\u044c .browser-data, \u0432\u0445\u043e\u0434\u044b \u043d\u0435 \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u044e\u0442\u0441\u044f. \u0412\u044b\u043a\u043b: \u043f\u0440\u043e\u0444\u0438\u043b\u044c \u0431\u0440\u0430\u0443\u0437\u0435\u0440\u0430 (\u0443\u043a\u0430\u0436\u0438\u0442\u0435 \u043f\u0443\u0442\u044c \u0432 .env: UNSAFE_BROWSER_USER_DATA_DIR, \u0431\u0440\u0430\u0443\u0437\u0435\u0440 \u0434\u043e\u043b\u0436\u0435\u043d \u0431\u044b\u0442\u044c \u0437\u0430\u043a\u0440\u044b\u0442). \u0415\u0441\u0442\u044c \u0440\u0438\u0441\u043a \u043f\u043e\u0432\u0440\u0435\u0434\u0438\u0442\u044c \u043f\u0440\u043e\u0444\u0438\u043b\u044c.',
    tooltip_browser_only:
      '\u041f\u0440\u0438 \u0432\u043a\u043b\u044e\u0447\u0435\u043d\u043d\u043e\u043c \u0440\u0435\u0436\u0438\u043c\u0435 \u0430\u0433\u0435\u043d\u0442 \u0432\u044b\u043f\u043e\u043b\u043d\u044f\u0435\u0442 \u0437\u0430\u0434\u0430\u0447\u0438 \u0442\u043e\u043b\u044c\u043a\u043e \u0447\u0435\u0440\u0435\u0437 \u0431\u0440\u0430\u0443\u0437\u0435\u0440. \u041f\u0440\u0438 \u0432\u044b\u043a\u043b\u044e\u0447\u0435\u043d\u043d\u043e\u043c \u2014 \u043c\u043e\u0436\u0435\u0442 \u043e\u0442\u0432\u0435\u0447\u0430\u0442\u044c \u043f\u0440\u044f\u043c\u043e \u0432 \u043a\u043e\u043d\u0441\u043e\u043b\u0438 \u043d\u0438\u0436\u0435, \u0435\u0441\u043b\u0438 \u043d\u0435\u0442 \u044f\u0432\u043d\u043e\u0439 \u0437\u0430\u0434\u0430\u0447\u0438.',
    tab_agent: '\u0410\u0433\u0435\u043d\u0442',
    tab_models: '\u041c\u043e\u0434\u0435\u043b\u0438',
    button_run: '\u0417\u0430\u043f\u0443\u0441\u0442\u0438\u0442\u044c',
    button_confirm: '\u041f\u043e\u0434\u0442\u0432\u0435\u0440\u0434\u0438\u0442\u044c / \u041f\u0440\u043e\u0434\u043e\u043b\u0436\u0438\u0442\u044c',
    button_stop: '\u041e\u0441\u0442\u0430\u043d\u043e\u0432\u0438\u0442\u044c',
    status_idle: '\u041e\u0436\u0438\u0434\u0430\u043d\u0438\u0435',
    status_starting: '\u0417\u0430\u043f\u0443\u0441\u043a \u0437\u0430\u0434\u0430\u0447\u0438...',
    status_wait_confirm: '\u041e\u0436\u0438\u0434\u0430\u043d\u0438\u0435 \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0435\u043d\u0438\u044f',
    status_wait_user: '\u041e\u0436\u0438\u0434\u0430\u043d\u0438\u0435 \u0432\u0432\u043e\u0434\u0430',
    status_prefix: '\u0421\u0442\u0430\u0442\u0443\u0441:',
    status_running: '\u0432 \u0440\u0430\u0431\u043e\u0442\u0435',
    status_waiting_confirm: '\u043e\u0436\u0438\u0434\u0430\u0435\u0442 \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0435\u043d\u0438\u044f',
    status_waiting_user: '\u043e\u0436\u0438\u0434\u0430\u0435\u0442 \u0432\u0432\u043e\u0434\u0430',
    status_done: '\u0433\u043e\u0442\u043e\u0432\u043e',
    status_stopped: '\u043e\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u043e',
    status_error: '\u043e\u0448\u0438\u0431\u043a\u0430',
    status_queued: '\u0432 \u043e\u0447\u0435\u0440\u0435\u0434\u0438',
    prompt_placeholder:
      '\u041f\u0440\u0438\u043c\u0435\u0440: \u043e\u0442\u043a\u0440\u043e\u0439\u0442\u0435 wikipedia.org, \u043d\u0430\u0439\u0434\u0438\u0442\u0435 Ada Lovelace \u0438 \u043a\u0440\u0430\u0442\u043a\u043e \u043f\u0435\u0440\u0435\u0441\u043a\u0430\u0436\u0438\u0442\u0435 3 \u0444\u0430\u043a\u0442\u0430.',
    log_confirm: '\u0422\u0420\u0415\u0411\u0423\u0415\u0422\u0421\u042f \u041f\u041e\u0414\u0422\u0412\u0415\u0420\u0416\u0414\u0415\u041d\u0418\u0415',
    log_user_input: '\u0422\u0420\u0415\u0411\u0423\u0415\u0422\u0421\u042f \u0412\u0412\u041e\u0414',
    log_result: '\u0420\u0415\u0417\u0423\u041b\u042c\u0422\u0410\u0422',
    log_event_error: '\u041e\u0448\u0438\u0431\u043a\u0430 \u043f\u043e\u0442\u043e\u043a\u0430 \u0441\u043e\u0431\u044b\u0442\u0438\u0439 \u0438\u043b\u0438 \u043e\u043d \u0437\u0430\u043a\u0440\u044b\u0442.',
    log_failed_start: '\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0441\u0442\u0430\u0440\u0442\u043e\u0432\u0430\u0442\u044c',
    alert_enter_task: '\u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u0437\u0430\u0434\u0430\u0447\u0443.',
    label_user_reply: '\u041e\u0442\u0432\u0435\u0442 \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044e',
    hint_user_reply:
      '\u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u043e\u0442\u0432\u0435\u0442 \u0438 \u043d\u0430\u0436\u043c\u0438\u0442\u0435 Confirm / Continue.',
    user_reply_placeholder: '\u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u043e\u0442\u0432\u0435\u0442 \u0437\u0434\u0435\u0441\u044c.',
    alert_enter_reply: '\u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u043e\u0442\u0432\u0435\u0442 \u0434\u043b\u044f \u0430\u0433\u0435\u043d\u0442\u0430.',
    action_navigate: '\u043f\u0435\u0440\u0435\u0445\u043e\u0436\u0443',
    action_click: '\u043a\u043b\u0438\u043a\u0430\u044e',
    action_type: '\u0432\u0432\u043e\u0436\u0443',
    action_extract: '\u0430\u043d\u0430\u043b\u0438\u0437\u0438\u0440\u0443\u044e',
    action_snapshot: '\u043e\u0441\u043c\u0430\u0442\u0440\u0438\u0432\u0430\u044e',
    action_scroll: '\u043b\u0438\u0441\u0442\u0430\u044e',
    action_wait: '\u0436\u0434\u0443',
    action_back: '\u043d\u0430\u0437\u0430\u0434',
    action_forward: '\u0432\u043f\u0435\u0440\u0451\u0434',
    action_ask_user: '\u0441\u043f\u0440\u0430\u0448\u0438\u0432\u0430\u044e',
    action_finish: '\u0437\u0430\u0432\u0435\u0440\u0448\u0430\u044e',
    action_stop_task: '\u043e\u0441\u0442\u0430\u043d\u0430\u0432\u043b\u0438\u0432\u0430\u044e',
    action_take_screenshot: '\u0441\u043a\u0440\u0438\u043d\u0448\u043e\u0442',
    action_save_trace: '\u0442\u0440\u0430\u0441\u0441\u0438\u0440\u0443\u044e',
    action_think: '\u0434\u0443\u043c\u0430\u044e',
    action_access: '\u043d\u0435\u0442 \u0434\u043e\u0441\u0442\u0443\u043f\u0430',
    action_loop_guard: '\u0437\u0430\u0441\u0442\u0440\u044f\u043b',
    action_user_input: '\u043e\u0442\u0432\u0435\u0442',
    action_tokens: '\u0442\u043e\u043a\u0435\u043d\u044b',
    action_guard: '\u043f\u0435\u0440\u0435\u043d\u0430\u043f\u0440\u0430\u0432\u043b\u044f\u044e',
  },
};

function setStatus(text) {
  statusEl.textContent = text;
}

function t(key) {
  return (I18N[currentLang] && I18N[currentLang][key]) || I18N.en[key] || key;
}

function statusLabel(value) {
  const map = {
    running: t('status_running'),
    waiting_confirm: t('status_waiting_confirm'),
    waiting_user: t('status_waiting_user'),
    done: t('status_done'),
    stopped: t('status_stopped'),
    error: t('status_error'),
    queued: t('status_queued'),
  };
  return map[value] || value;
}

function actionLabel(tool) {
  const map = {
    navigate: 'action_navigate',
    click: 'action_click',
    type: 'action_type',
    extract: 'action_extract',
    snapshot: 'action_snapshot',
    scroll: 'action_scroll',
    wait: 'action_wait',
    wait_for_network_idle: 'action_wait',
    back: 'action_back',
    forward: 'action_forward',
    ask_user: 'action_ask_user',
    finish: 'action_finish',
    stop_task: 'action_stop_task',
    take_screenshot: 'action_take_screenshot',
    save_trace: 'action_save_trace',
    none: 'action_think',
    access: 'action_access',
    loop_guard: 'action_loop_guard',
    user_input: 'action_user_input',
    tokens: 'action_tokens',
    guard: 'action_guard',
  };
  const key = map[tool] || '';
  return key ? t(key) : '';
}

function formatDuration(ms) {
  if (typeof ms !== 'number' || Number.isNaN(ms)) {
    return '';
  }
  if (ms >= 1000) {
    return `${(ms / 1000).toFixed(1)}s`;
  }
  return `${ms}ms`;
}

function applyLanguage(lang) {
  currentLang = lang;
  localStorage.setItem('ui_lang', lang);
  langSpans.forEach((span) => {
    span.classList.toggle('active', span.dataset.lang === lang);
  });
  document.querySelectorAll('[data-i18n]').forEach((el) => {
    const key = el.getAttribute('data-i18n');
    if (key) {
      el.textContent = t(key);
    }
  });
  document.querySelectorAll('[data-i18n-placeholder]').forEach((el) => {
    const key = el.getAttribute('data-i18n-placeholder');
    if (key) {
      el.setAttribute('placeholder', t(key));
    }
  });
  document.querySelectorAll('[data-i18n-tooltip]').forEach((el) => {
    const key = el.getAttribute('data-i18n-tooltip');
    if (key) {
      el.setAttribute('data-tooltip', t(key));
    }
  });
  setStatus(t('status_idle'));
}

function appendLog(line) {
  logEl.textContent += `${line}\n`;
  logEl.scrollTop = logEl.scrollHeight;
}

function resetUI() {
  logEl.textContent = '';
  confirmBtn.disabled = true;
  stopBtn.disabled = true;
  runBtn.disabled = false;
  waitingForUserInput = false;
  if (userReplyWrap) {
    userReplyWrap.classList.add('hidden');
  }
  if (userReplyInput) {
    userReplyInput.value = '';
  }
  setStatus(t('status_idle'));
}

function applyTheme(theme) {
  if (theme === 'dark') {
    document.body.dataset.theme = 'dark';
  } else {
    document.body.dataset.theme = 'light';
  }
  themeButtons.forEach((button) => {
    button.classList.toggle('active', button.dataset.theme === theme);
  });
  localStorage.setItem('ui_theme', theme);
}

function loadSettings() {
  const storedLang = localStorage.getItem('ui_lang') || 'ru';
  applyLanguage(storedLang);

  const theme = localStorage.getItem('ui_theme') || 'light';
  applyTheme(theme);

  const storedSearch = localStorage.getItem('search_engine') || 'google';
  if (searchEngineEl) {
    searchEngineEl.value = storedSearch;
  }

  const storedProvider = localStorage.getItem('llm_provider') || 'openai';
  if (providerEl) {
    providerEl.value = storedProvider;
  }
  setModelOptions(storedProvider);
  const storedModel = localStorage.getItem(`llm_model_${storedProvider}`) || '';
  const legacyModel = localStorage.getItem('llm_model') || '';
  if (modelEl && (storedModel || legacyModel)) {
    modelEl.value = storedModel || legacyModel;
  }

  const storedSafeMode = localStorage.getItem('safe_mode');
  if (storedSafeMode !== null && safeModeEl) {
    safeModeEl.checked = storedSafeMode === 'true';
  }

  const storedBrowserOnly = localStorage.getItem('browser_only');
  if (storedBrowserOnly !== null && browserOnlyEl) {
    browserOnlyEl.checked = storedBrowserOnly === 'true';
  }
}

function setModelOptions(provider) {
  if (!modelEl) return;
  const options = MODEL_OPTIONS[provider] || [];
  modelEl.innerHTML = '';
  options.forEach((model) => {
    const option = document.createElement('option');
    option.value = model;
    option.textContent = model;
    modelEl.appendChild(option);
  });
  if (!options.length) {
    const option = document.createElement('option');
    option.value = '';
    option.textContent = 'No models available';
    modelEl.appendChild(option);
  }
}

function bindSettings() {
  themeButtons.forEach((button) => {
    button.addEventListener('click', () => {
      applyTheme(button.dataset.theme);
    });
  });

  if (searchEngineEl) {
    searchEngineEl.addEventListener('change', () => {
      localStorage.setItem('search_engine', searchEngineEl.value);
    });
  }

  if (providerEl) {
    providerEl.addEventListener('change', () => {
      const provider = providerEl.value;
      localStorage.setItem('llm_provider', provider);
      setModelOptions(provider);
      const storedModel = localStorage.getItem(`llm_model_${provider}`);
      if (modelEl && storedModel) {
        modelEl.value = storedModel;
      }
    });
  }

  if (modelEl) {
    modelEl.addEventListener('change', () => {
      const provider = providerEl ? providerEl.value : 'gemini';
      localStorage.setItem(`llm_model_${provider}`, modelEl.value);
    });
  }

  if (safeModeEl) {
    safeModeEl.addEventListener('change', () => {
      localStorage.setItem('safe_mode', String(safeModeEl.checked));
    });
  }

  if (browserOnlyEl) {
    browserOnlyEl.addEventListener('change', () => {
      localStorage.setItem('browser_only', String(browserOnlyEl.checked));
    });
  }

  if (settingsButton && settingsPanel) {
    settingsButton.addEventListener('click', (event) => {
      event.stopPropagation();
      settingsPanel.classList.toggle('open');
    });
    settingsPanel.addEventListener('click', (event) => {
      event.stopPropagation();
    });
    document.addEventListener('click', () => {
      settingsPanel.classList.remove('open');
    });
  }

  if (langToggle) {
    langToggle.addEventListener('click', () => {
      const next = currentLang === 'ru' ? 'en' : 'ru';
      applyLanguage(next);
    });
  }
}

function setActiveTab(tabId) {
  tabs.forEach((tab) => {
    tab.classList.toggle('active', tab.dataset.tab === tabId);
  });
  tabPanels.forEach((panel) => {
    panel.classList.toggle('active', panel.id === `tab-${tabId}`);
  });
}

function setActiveProvider(provider) {
  providerTabs.forEach((tab) => {
    tab.classList.toggle('active', tab.dataset.provider === provider);
  });
  providerPanels.forEach((panel) => {
    panel.classList.toggle('active', panel.id === `provider-${provider}`);
  });
}

async function fetchModels(provider) {
  const config = providerConfig[provider];
  const keyInput = document.getElementById(config.keyInput);
  const baseInput = document.getElementById(config.baseInput);
  const outputEl = document.getElementById(config.output);

  const apiKey = keyInput.value.trim();
  const baseUrl = baseInput.value.trim();
  if (!apiKey) {
    outputEl.textContent = 'Enter an API key.';
    return;
  }

  outputEl.textContent = 'Loading...';
  const payload = { api_key: apiKey };
  if (baseUrl) {
    payload.base_url = baseUrl;
  }

  try {
  const response = await fetch(`${API_BASE}${config.endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: response.statusText }));
      outputEl.textContent = `Error: ${err.detail || response.statusText}`;
      return;
    }
    const data = await response.json();
    if (data.models && data.models.length) {
      outputEl.textContent = data.models.join('\n');
    } else {
      outputEl.textContent = 'No models returned.';
    }
  } catch (err) {
    outputEl.textContent = `Error: ${err.message || err}`;
  }
}

function connectEvents(id) {
  if (eventSource) {
    eventSource.close();
  }
  eventSource = new EventSource(`${API_BASE}/tasks/${id}/events`);
  eventSource.addEventListener('log', (event) => {
    const payload = JSON.parse(event.data);
    const data = payload.data || {};
    const action = actionLabel(data.tool || '');
    const duration = formatDuration(data.duration_ms);
    const parts = [];
    if (action) parts.push(action);
    if (data.tool) parts.push(data.tool);
    if (data.status) parts.push(data.status);
    if (data.reason) parts.push(data.reason);
    if (duration) parts.push(`(${duration})`);
    const message = `[${data.step || ''}] ${parts.join(' ')}`;
    const errorText = data.error ? ` | error: ${data.error}` : '';
    appendLog(`${message}${errorText}`.trim());
  });
  eventSource.addEventListener('needs_confirmation', (event) => {
    const payload = JSON.parse(event.data);
    const data = payload.data || {};
    appendLog(`${t('log_confirm')}: ${data.summary || ''}`);
    confirmBtn.disabled = false;
    stopBtn.disabled = false;
    waitingForUserInput = false;
    if (userReplyWrap) {
      userReplyWrap.classList.add('hidden');
    }
    setStatus(t('status_wait_confirm'));
  });
  eventSource.addEventListener('needs_user_input', (event) => {
    const payload = JSON.parse(event.data);
    const data = payload.data || {};
    appendLog(`${t('log_user_input')}: ${data.question || ''}`);
    confirmBtn.disabled = false;
    stopBtn.disabled = false;
    waitingForUserInput = true;
    if (userReplyWrap) {
      userReplyWrap.classList.remove('hidden');
    }
    if (userReplyInput) {
      userReplyInput.focus();
    }
    setStatus(t('status_wait_user'));
  });
  eventSource.addEventListener('result', (event) => {
    const payload = JSON.parse(event.data);
    const data = payload.data || {};
    appendLog(`${t('log_result')}: ${data.result || ''}`);
  });
  eventSource.addEventListener('status', (event) => {
    const payload = JSON.parse(event.data);
    const data = payload.data || {};
    setStatus(`${t('status_prefix')} ${statusLabel(data.status || '')}`);
    if (['done', 'stopped', 'error'].includes(data.status)) {
      confirmBtn.disabled = true;
      stopBtn.disabled = true;
      runBtn.disabled = false;
      waitingForUserInput = false;
      if (userReplyWrap) {
        userReplyWrap.classList.add('hidden');
      }
      if (eventSource) {
        eventSource.close();
      }
    }
  });
  eventSource.onerror = () => {
    appendLog(t('log_event_error'));
  };
}

runBtn.addEventListener('click', async () => {
  const prompt = promptEl.value.trim();
  if (!prompt) {
    alert(t('alert_enter_task'));
    return;
  }
  resetUI();
  setStatus(t('status_starting'));
  runBtn.disabled = true;
  const response = await fetch(`${API_BASE}/tasks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      prompt,
      browser_only: browserOnlyEl.checked,
      search_engine: searchEngineEl.value,
      model: modelEl ? modelEl.value : undefined,
      provider: providerEl ? providerEl.value : undefined,
      safe_mode: safeModeEl ? safeModeEl.checked : true,
    }),
  });
  if (!response.ok) {
    const err = await response.json();
    appendLog(`${t('log_failed_start')}: ${err.detail || response.statusText}`);
    setStatus(`${t('status_prefix')} ${t('status_error')}`);
    runBtn.disabled = false;
    return;
  }
  const data = await response.json();
  taskId = data.task_id;
  stopBtn.disabled = false;
  connectEvents(taskId);
});

confirmBtn.addEventListener('click', async () => {
  if (!taskId) return;
  confirmBtn.disabled = true;
  setStatus('Continuing...');
  const payload = {};
  if (waitingForUserInput && userReplyInput) {
    const reply = userReplyInput.value.trim();
    if (!reply) {
      appendLog(t('alert_enter_reply'));
      confirmBtn.disabled = false;
      return;
    }
    payload.response = reply;
    userReplyInput.value = '';
  }
  const body = Object.keys(payload).length ? JSON.stringify(payload) : null;
  await fetch(`${API_BASE}/tasks/${taskId}/confirm`, {
    method: 'POST',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body,
  });
});

stopBtn.addEventListener('click', async () => {
  if (!taskId) return;
  stopBtn.disabled = true;
  setStatus('Stopping...');
  await fetch(`${API_BASE}/tasks/${taskId}/stop`, { method: 'POST' });
});

tabs.forEach((tab) => {
  tab.addEventListener('click', () => {
    setActiveTab(tab.dataset.tab);
  });
});

providerTabs.forEach((tab) => {
  tab.addEventListener('click', () => {
    setActiveProvider(tab.dataset.provider);
  });
});

document.querySelectorAll('.fetch-models').forEach((button) => {
  button.addEventListener('click', () => {
    fetchModels(button.dataset.provider);
  });
});

setActiveTab('agent');
setActiveProvider('openai');
loadSettings();
bindSettings();
resetUI();
