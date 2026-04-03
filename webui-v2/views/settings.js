/* ============================================================
   Settings View — Configuration Options
   ============================================================ */

Router.register('settings', {
  async render(container) {
    container.innerHTML = `
      <div class="settings-page">
        <h2>Settings</h2>
        <p style="margin-top:8px">Configuration options for your workspace.</p>
        <div style="margin-top:32px; display:flex; flex-direction:column; gap:16px">

          <div class="card" style="padding:16px">
            <div style="display:flex; align-items:center; justify-content:space-between">
              <div>
                <div style="font-size:14px; font-weight:500; margin-bottom:4px">Mock Data Mode</div>
                <div style="font-size:13px; color:var(--text-muted)">Use sample data for UI development. Turn off to work with real data.</div>
              </div>
              <label class="toggle-switch">
                <input type="checkbox" id="mock-mode-toggle">
                <span class="toggle-slider"></span>
              </label>
            </div>
          </div>

          <div class="card" style="padding:16px">
            <div style="font-size:14px; font-weight:500; margin-bottom:8px">Planning Model</div>
            <div style="font-size:13px; color:var(--text-muted); margin-bottom:12px">Choose which LLM provider and model to use for the planning chat.</div>
            <div style="display:flex; flex-direction:column; gap:10px">
              <div style="display:flex; align-items:center; gap:12px">
                <label style="font-size:13px; min-width:70px">Provider</label>
                <select id="planning-provider" style="flex:1; padding:6px 10px; border-radius:6px; border:1px solid var(--border); background:var(--surface); color:var(--text); font-size:13px">
                  <option value="anthropic">Anthropic (Claude)</option>
                  <option value="openai">OpenAI (GPT)</option>
                </select>
              </div>
              <div style="display:flex; align-items:center; gap:12px">
                <label style="font-size:13px; min-width:70px">Model</label>
                <input type="text" id="planning-model" placeholder="Leave blank for default" style="flex:1; padding:6px 10px; border-radius:6px; border:1px solid var(--border); background:var(--surface); color:var(--text); font-size:13px">
              </div>
              <div style="display:flex; align-items:center; gap:8px; margin-top:4px">
                <button id="save-planning-model" style="padding:6px 16px; border-radius:6px; border:none; background:var(--accent); color:#fff; font-size:13px; cursor:pointer">Save</button>
                <span id="planning-model-status" style="font-size:12px; color:var(--text-muted)"></span>
              </div>
            </div>
          </div>

          <div class="card" style="padding:16px">
            <div style="font-size:14px; font-weight:500; margin-bottom:4px">API Server</div>
            <div style="font-size:13px; color:var(--text-muted)">Connected to localhost:8718</div>
          </div>
          <div class="card" style="padding:16px">
            <div style="font-size:14px; font-weight:500; margin-bottom:4px">Theme</div>
            <div style="font-size:13px; color:var(--text-muted)">Dark (default)</div>
          </div>
          <div class="card" style="padding:16px">
            <div style="font-size:14px; font-weight:500; margin-bottom:4px">Version</div>
            <div style="font-size:13px; color:var(--text-muted)">Salt Desktop v0.1</div>
          </div>
        </div>
      </div>
    `;

    // Load current mock mode state
    const toggle = container.querySelector('#mock-mode-toggle');
    try {
      const status = await API.get('/api/mock/status');
      toggle.checked = !!status.mock_mode;
    } catch (e) {
      console.error('Failed to load mock status:', e);
    }

    // Handle toggle changes
    toggle.addEventListener('change', async () => {
      try {
        if (toggle.checked) {
          await API.post('/api/mock/enable');
        } else {
          await API.post('/api/mock/disable');
        }
      } catch (e) {
        console.error('Failed to toggle mock mode:', e);
        // Revert on failure
        toggle.checked = !toggle.checked;
      }
    });

    // Load current planning model settings
    const providerSelect = container.querySelector('#planning-provider');
    const modelInput = container.querySelector('#planning-model');
    const saveBtn = container.querySelector('#save-planning-model');
    const statusSpan = container.querySelector('#planning-model-status');

    try {
      const settings = await API.get('/api/settings/planning-model');
      if (settings.provider) providerSelect.value = settings.provider;
      if (settings.model) modelInput.value = settings.model;
      modelInput.placeholder = settings.model || 'Leave blank for default';
    } catch (e) {
      console.error('Failed to load planning model settings:', e);
    }

    // Save planning model settings
    saveBtn.addEventListener('click', async () => {
      try {
        statusSpan.textContent = 'Saving...';
        const result = await API.post('/api/settings/planning-model', {
          provider: providerSelect.value,
          model: modelInput.value || '',
        });
        statusSpan.textContent = `Saved: ${result.provider} / ${result.model}`;
        setTimeout(() => { statusSpan.textContent = ''; }, 3000);
      } catch (e) {
        console.error('Failed to save planning model:', e);
        statusSpan.textContent = 'Failed to save';
        statusSpan.style.color = '#f44';
        setTimeout(() => { statusSpan.textContent = ''; statusSpan.style.color = ''; }, 3000);
      }
    });
  },
  destroy() {},
});
