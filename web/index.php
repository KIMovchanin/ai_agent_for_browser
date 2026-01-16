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
        <h1>Browser Agent MVP</h1>
        <p class="hint">Enter a multi-step task and watch the browser.</p>
      </div>
      <button id="settings-button" class="icon-button" aria-label="Settings">
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7Zm8.94 2.52-1.72-.7a7.36 7.36 0 0 0-.6-1.44l.76-1.7a.9.9 0 0 0-.2-.98l-1.43-1.43a.9.9 0 0 0-.98-.2l-1.7.76c-.46-.26-.95-.48-1.44-.6l-.7-1.72a.9.9 0 0 0-.84-.57h-2.02a.9.9 0 0 0-.84.57l-.7 1.72c-.5.12-.98.34-1.44.6l-1.7-.76a.9.9 0 0 0-.98.2L4.82 6.2a.9.9 0 0 0-.2.98l.76 1.7c-.26.46-.48.95-.6 1.44l-1.72.7a.9.9 0 0 0-.57.84v2.02c0 .37.22.7.57.84l1.72.7c.12.5.34.98.6 1.44l-.76 1.7a.9.9 0 0 0 .2.98l1.43 1.43c.26.26.64.34.98.2l1.7-.76c.46.26.95.48 1.44.6l.7 1.72c.14.35.47.57.84.57h2.02c.37 0 .7-.22.84-.57l.7-1.72c.5-.12.98-.34 1.44-.6l1.7.76c.34.14.72.06.98-.2l1.43-1.43c.26-.26.34-.64.2-.98l-.76-1.7c.26-.46.48-.95.6-1.44l1.72-.7c.35-.14.57-.47.57-.84v-2.02a.9.9 0 0 0-.57-.84Z"/>
        </svg>
      </button>
      <div id="settings-panel" class="settings-panel">
        <div class="settings-title">&#1053;&#1072;&#1089;&#1090;&#1088;&#1086;&#1081;&#1082;&#1080;</div>
        <div class="settings-group">
          <div class="settings-label">&#1058;&#1077;&#1084;&#1072;</div>
          <div class="theme-toggle">
            <button class="theme-btn" data-theme="light">&#1057;&#1074;&#1077;&#1090;&#1083;&#1072;&#1103;</button>
            <button class="theme-btn" data-theme="dark">&#1058;&#1077;&#1084;&#1085;&#1072;&#1103;</button>
          </div>
        </div>
        <div class="settings-group">
          <label class="field">
            <span>&#1055;&#1086;&#1080;&#1089;&#1082;&#1086;&#1074;&#1080;&#1082;</span>
            <select id="search-engine">
              <option value="google">Google</option>
              <option value="duckduckgo">DuckDuckGo</option>
              <option value="bing">Bing</option>
              <option value="yandex">Yandex</option>
            </select>
          </label>
        </div>
        <div class="settings-group">
          <div class="settings-row">
            <label class="switch">
              <input type="checkbox" id="create-window" checked />
              <span class="slider"></span>
            </label>
            <span class="toggle-text">&#1057;&#1086;&#1079;&#1076;&#1072;&#1074;&#1072;&#1090;&#1100; &#1086;&#1082;&#1085;&#1072;</span>
            <span class="tooltip" data-tooltip="&#1045;&#1089;&#1083;&#1080; &#1074;&#1099;&#1082;&#1083;&#1102;&#1095;&#1077;&#1085;&#1086;, &#1072;&#1075;&#1077;&#1085;&#1090; &#1086;&#1090;&#1082;&#1088;&#1099;&#1074;&#1072;&#1077;&#1090; &#1074;&#1082;&#1083;&#1072;&#1076;&#1082;&#1080; &#1074; &#1090;&#1077;&#1082;&#1091;&#1097;&#1077;&#1084; &#1086;&#1082;&#1085;&#1077; &#1073;&#1088;&#1072;&#1091;&#1079;&#1077;&#1088;&#1072;. &#1045;&#1089;&#1083;&#1080; &#1074;&#1082;&#1083;&#1102;&#1095;&#1077;&#1085;&#1086;, &#1086;&#1090;&#1082;&#1088;&#1099;&#1074;&#1072;&#1077;&#1090; &#1085;&#1086;&#1074;&#1086;&#1077; &#1086;&#1082;&#1085;&#1086; &#1076;&#1083;&#1103; &#1088;&#1072;&#1073;&#1086;&#1090;&#1099; &#1072;&#1075;&#1077;&#1085;&#1090;&#1072;.">?</span>
          </div>
          <div class="settings-row">
            <label class="switch">
              <input type="checkbox" id="browser-only" checked />
              <span class="slider"></span>
            </label>
            <span class="toggle-text">browser-only</span>
            <span class="tooltip" data-tooltip="&#1055;&#1088;&#1080; &#1074;&#1082;&#1083;&#1102;&#1095;&#1077;&#1085;&#1085;&#1086;&#1084; &#1088;&#1077;&#1078;&#1080;&#1084;&#1077; &#1072;&#1075;&#1077;&#1085;&#1090; &#1074;&#1099;&#1087;&#1086;&#1083;&#1103;&#1077;&#1090; &#1079;&#1072;&#1076;&#1072;&#1095;&#1080; &#1090;&#1086;&#1083;&#1100;&#1082;&#1086; &#1095;&#1077;&#1088;&#1077;&#1079; &#1073;&#1088;&#1072;&#1091;&#1079;&#1077;&#1088;. &#1055;&#1088;&#1080; &#1074;&#1099;&#1082;&#1083;&#1102;&#1095;&#1077;&#1085;&#1085;&#1086;&#1084; &#8212; &#1084;&#1086;&#1078;&#1077;&#1090; &#1086;&#1090;&#1074;&#1077;&#1095;&#1072;&#1090;&#1100; &#1087;&#1088;&#1103;&#1084;&#1086; &#1074; &#1082;&#1086;&#1085;&#1089;&#1086;&#1083;&#1080; &#1085;&#1080;&#1078;&#1077;, &#1077;&#1089;&#1083;&#1080; &#1085;&#1077;&#1090; &#1103;&#1074;&#1085;&#1086;&#1081; &#1079;&#1072;&#1076;&#1072;&#1095;&#1080;; &#1074;&#1086;&#1079;&#1084;&#1086;&#1078;&#1085;&#1099; &#1085;&#1077;&#1073;&#1086;&#1083;&#1100;&#1096;&#1080;&#1077; &#1086;&#1096;&#1080;&#1073;&#1082;&#1080;.">?</span>
          </div>
        </div>
      </div>
    </div>
    <div class="tabs">
      <button class="tab active" data-tab="agent">Agent</button>
      <button class="tab" data-tab="models">Models</button>
    </div>
    <div id="tab-agent" class="tab-panel active">
      <textarea id="prompt" rows="5" placeholder="Example: Open wikipedia.org, search for Ada Lovelace, summarize 3 facts."></textarea>
      <div class="controls">
        <button id="run">Run</button>
        <button id="confirm" disabled>Confirm / Continue</button>
        <button id="stop" disabled>Stop</button>
      </div>
      <div class="status" id="status">Idle</div>
      <pre id="log"></pre>
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
