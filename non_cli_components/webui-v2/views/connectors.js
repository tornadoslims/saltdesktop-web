/* ============================================================
   Connectors View — External Service Connections
   Shows all 19 supported services and their connection status
   ============================================================ */

Router.register('connectors', {
  _container: null,
  _connections: [],

  async render(container) {
    this._container = container;
    container.innerHTML = '<div class="view-page"><div class="view-greeting">Connectors</div><div style="color:var(--text-muted)">Loading connections...</div></div>';

    try {
      this._connections = await API.get('/api/connections');
    } catch (e) {
      console.error('Failed to load connections:', e);
      this._connections = [];
    }

    this._paint();
  },

  destroy() {
    this._container = null;
  },

  _paint() {
    const c = this._container;
    if (!c) return;

    const conns = this._connections;
    const connected = conns.filter(s => s.connected);
    const disconnected = conns.filter(s => !s.connected);

    // Service icons
    const icons = {
      gmail: '\uD83D\uDCE7',
      google_calendar: '\uD83D\uDCC5',
      google_drive: '\uD83D\uDCC1',
      github: '\uD83D\uDC19',
      salesforce: '\u2601\uFE0F',
      notion: '\uD83D\uDCDD',
      linear: '\uD83D\uDCD0',
      jira: '\uD83C\uDFAF',
      discord: '\uD83D\uDCAC',
      telegram: '\u2708\uFE0F',
      openai: '\uD83E\uDD16',
      stripe: '\uD83D\uDCB3',
      aws: '\u2601\uFE0F',
      snowflake: '\u2744\uFE0F',
      mysql: '\uD83D\uDDC4\uFE0F',
      postgresql: '\uD83D\uDC18',
      oracle: '\uD83C\uDFDB\uFE0F',
      redis: '\u26A1',
      gcp: '\uD83C\uDF10',
    };

    // Type labels
    const typeLabels = {
      oauth: 'OAuth',
      api_key: 'API Key',
      connection_string: 'Connection String',
    };

    // Group definitions
    const groupDefs = [
      { key: 'email_comm', label: 'Email & Communication', ids: ['gmail', 'discord', 'telegram'] },
      { key: 'productivity', label: 'Productivity', ids: ['google_calendar', 'google_drive', 'notion', 'linear', 'jira'] },
      { key: 'developer', label: 'Developer', ids: ['github', 'openai'] },
      { key: 'business', label: 'Business', ids: ['salesforce', 'stripe'] },
      { key: 'cloud', label: 'Cloud & Infrastructure', ids: ['aws', 'gcp'] },
      { key: 'databases', label: 'Databases', ids: ['snowflake', 'mysql', 'postgresql', 'oracle', 'redis'] },
    ];

    // Build lookup
    const connMap = {};
    conns.forEach(s => { connMap[s.id] = s; });

    let html = '<div class="view-page">';
    html += '<div class="view-greeting">Connectors</div>';
    html += '<div style="color:var(--text-muted); margin-top:-8px; margin-bottom:20px;">Connect external services to power your agents</div>';

    // Stats bar
    html += `<div class="connectors-stats">`;
    html += `<span class="connectors-stat"><span class="connectors-stat-num connected">${connected.length}</span> connected</span>`;
    html += `<span class="connectors-stat-sep">&middot;</span>`;
    html += `<span class="connectors-stat"><span class="connectors-stat-num available">${disconnected.length}</span> available</span>`;
    html += `</div>`;

    // Groups
    groupDefs.forEach(group => {
      const services = group.ids.map(id => connMap[id]).filter(Boolean);
      if (services.length === 0) return;

      html += `<div class="view-section">`;
      html += `<div class="section-header">`;
      html += `<span class="section-title">${this._esc(group.label)}</span>`;
      html += `<span class="section-count">${services.length}</span>`;
      html += `</div>`;

      html += `<div class="connectors-grid">`;
      services.forEach(svc => {
        const icon = icons[svc.id] || '\u2B1B';
        const typeLbl = typeLabels[svc.type] || svc.type;
        const isConn = svc.connected;

        html += `<div class="connector-card ${isConn ? 'connected' : 'disconnected'}" data-service-id="${svc.id}" data-connected="${isConn}">`;
        html += `<div class="connector-card-top">`;
        html += `<span class="connector-card-icon">${icon}</span>`;
        html += `<span class="connector-card-name">${this._esc(svc.name)}</span>`;
        if (isConn) {
          html += `<span class="connector-badge connected">CONNECTED</span>`;
        }
        html += `</div>`;
        html += `<div class="connector-card-meta">${this._esc(svc.category ? svc.category.replace(/_/g, ' ') : '')} &middot; ${typeLbl}</div>`;
        if (isConn) {
          html += `<div class="connector-card-scope">${svc.scope || 'Connected'}</div>`;
        } else {
          html += `<div class="connector-card-scope muted">Not connected</div>`;
        }
        html += `</div>`;
      });
      html += `</div></div>`;
    });

    html += '</div>';

    // Modal overlay (hidden by default)
    html += `<div class="connector-modal-overlay" id="connector-modal" style="display:none">`;
    html += `<div class="connector-modal">`;
    html += `<div class="connector-modal-title" id="connector-modal-title"></div>`;
    html += `<div class="connector-modal-body" id="connector-modal-body"></div>`;
    html += `<div class="connector-modal-footer">`;
    html += `<button class="connector-modal-btn" id="connector-modal-ok">OK</button>`;
    html += `</div></div></div>`;

    c.innerHTML = html;

    // Bind card clicks
    c.querySelectorAll('.connector-card').forEach(card => {
      card.addEventListener('click', () => {
        const svcId = card.dataset.serviceId;
        const isConn = card.dataset.connected === 'true';
        const svc = connMap[svcId];
        if (!svc) return;

        const icon = icons[svc.id] || '';
        const typeLbl = typeLabels[svc.type] || svc.type;

        if (isConn) {
          this._showConnectedModal(svc, icon, typeLbl);
        } else {
          this._showDisconnectedModal(svc, icon);
        }
      });
    });

    // Bind modal close
    const modal = c.querySelector('#connector-modal');
    const okBtn = c.querySelector('#connector-modal-ok');
    if (okBtn) {
      okBtn.addEventListener('click', () => { modal.style.display = 'none'; });
    }
    if (modal) {
      modal.addEventListener('click', (e) => {
        if (e.target === modal) modal.style.display = 'none';
      });
    }
  },

  _showDisconnectedModal(svc, icon) {
    const modal = this._container.querySelector('#connector-modal');
    const title = this._container.querySelector('#connector-modal-title');
    const body = this._container.querySelector('#connector-modal-body');
    title.textContent = `Connect ${svc.name}`;
    body.textContent = `To connect ${svc.name}, open the Salt Desktop companion app and complete the authentication flow.`;
    modal.style.display = 'flex';
  },

  _showConnectedModal(svc, icon, typeLbl) {
    const modal = this._container.querySelector('#connector-modal');
    const title = this._container.querySelector('#connector-modal-title');
    const body = this._container.querySelector('#connector-modal-body');
    title.innerHTML = `${icon} ${this._esc(svc.name)} <span class="connector-badge connected" style="font-size:11px; vertical-align:middle; margin-left:8px">CONNECTED</span>`;
    body.innerHTML = `
      <div class="connector-detail-row"><span class="connector-detail-label">Type</span><span>${this._esc(typeLbl)}</span></div>
      ${svc.scope ? `<div class="connector-detail-row"><span class="connector-detail-label">Scope</span><span>${this._esc(svc.scope)}</span></div>` : ''}
      <div class="connector-detail-row"><span class="connector-detail-label">Status</span><span style="color:var(--success)">&#10003; Connected</span></div>
    `;
    modal.style.display = 'flex';
  },

  _esc(str) {
    const d = document.createElement('div');
    d.textContent = str || '';
    return d.innerHTML;
  },
});
