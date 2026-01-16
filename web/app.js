const API_BASE = 'http://localhost:8080';

const promptEl = document.getElementById('prompt');
const runBtn = document.getElementById('run');
const confirmBtn = document.getElementById('confirm');
const stopBtn = document.getElementById('stop');
const statusEl = document.getElementById('status');
const logEl = document.getElementById('log');
const browserOnlyEl = document.getElementById('browser-only');
const createWindowEl = document.getElementById('create-window');
const searchEngineEl = document.getElementById('search-engine');
const settingsButton = document.getElementById('settings-button');
const settingsPanel = document.getElementById('settings-panel');
const themeButtons = document.querySelectorAll('.theme-btn');

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

function setStatus(text) {
  statusEl.textContent = text;
}

function appendLog(line) {
  logEl.textContent += `${line}\n`;
  logEl.scrollTop = logEl.scrollHeight;
}

function resetUI() {
  logEl.textContent = '';
  confirmBtn.disabled = true;
  stopBtn.disabled = true;
  setStatus('Idle');
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
  const theme = localStorage.getItem('ui_theme') || 'light';
  applyTheme(theme);

  const storedSearch = localStorage.getItem('search_engine') || 'google';
  if (searchEngineEl) {
    searchEngineEl.value = storedSearch;
  }

  const storedBrowserOnly = localStorage.getItem('browser_only');
  if (storedBrowserOnly !== null && browserOnlyEl) {
    browserOnlyEl.checked = storedBrowserOnly === 'true';
  }

  const storedCreateWindow = localStorage.getItem('create_window');
  if (storedCreateWindow !== null && createWindowEl) {
    createWindowEl.checked = storedCreateWindow === 'true';
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

  if (browserOnlyEl) {
    browserOnlyEl.addEventListener('change', () => {
      localStorage.setItem('browser_only', String(browserOnlyEl.checked));
    });
  }

  if (createWindowEl) {
    createWindowEl.addEventListener('change', () => {
      localStorage.setItem('create_window', String(createWindowEl.checked));
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
    const message = `[${data.step || ''}] ${data.tool || ''} ${data.status || ''} ${data.reason || ''}`;
    appendLog(message.trim());
  });
  eventSource.addEventListener('needs_confirmation', (event) => {
    const payload = JSON.parse(event.data);
    const data = payload.data || {};
    appendLog(`CONFIRM REQUIRED: ${data.summary || ''}`);
    confirmBtn.disabled = false;
    stopBtn.disabled = false;
    setStatus('Waiting for confirmation');
  });
  eventSource.addEventListener('needs_user_input', (event) => {
    const payload = JSON.parse(event.data);
    const data = payload.data || {};
    appendLog(`USER INPUT NEEDED: ${data.question || ''}`);
    confirmBtn.disabled = false;
    stopBtn.disabled = false;
    setStatus('Waiting for user input');
  });
  eventSource.addEventListener('result', (event) => {
    const payload = JSON.parse(event.data);
    const data = payload.data || {};
    appendLog(`RESULT: ${data.result || ''}`);
  });
  eventSource.addEventListener('status', (event) => {
    const payload = JSON.parse(event.data);
    const data = payload.data || {};
    setStatus(`Status: ${data.status || ''}`);
    if (['done', 'stopped', 'error'].includes(data.status)) {
      confirmBtn.disabled = true;
      stopBtn.disabled = true;
      if (eventSource) {
        eventSource.close();
      }
    }
  });
  eventSource.onerror = () => {
    appendLog('Event stream error or closed.');
  };
}

runBtn.addEventListener('click', async () => {
  const prompt = promptEl.value.trim();
  if (!prompt) {
    alert('Enter a task prompt.');
    return;
  }
  resetUI();
  setStatus('Starting task...');
  const response = await fetch(`${API_BASE}/tasks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      prompt,
      browser_only: browserOnlyEl.checked,
      create_window: createWindowEl.checked,
      search_engine: searchEngineEl.value,
    }),
  });
  if (!response.ok) {
    const err = await response.json();
    appendLog(`Failed to start: ${err.detail || response.statusText}`);
    setStatus('Error');
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
  await fetch(`${API_BASE}/tasks/${taskId}/confirm`, { method: 'POST' });
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
