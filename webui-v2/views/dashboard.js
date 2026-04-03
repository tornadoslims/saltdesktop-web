/* ============================================================
   Dashboard View — Living Summary (Home)
   "Good morning, Jim."
   ============================================================ */

Router.register('dashboard', {
  _container: null,

  render(container) {
    this._container = container;
    this._paint();
  },

  destroy() {
    this._container = null;
  },

  onEvent(data) {
    // Live-update recent feed if visible
    if (!this._container) return;
    const feed = this._container.querySelector('.activity-feed');
    if (!feed || !data.ceo_text) return;

    const item = document.createElement('div');
    item.className = 'activity-item activity-new';
    const icon = data.ceo_icon || (data.type?.includes('tool') ? '\uD83D\uDD28' : '\u26A1');
    item.innerHTML = `
      <span class="activity-icon">${icon}</span>
      <span class="activity-text">${this._esc(data.ceo_text || data.label || '')}</span>
      <span class="activity-time">just now</span>
    `;
    feed.prepend(item);

    // Limit to 12 items
    while (feed.children.length > 12) feed.removeChild(feed.lastChild);
  },

  _paint() {
    const c = this._container;
    if (!c) return;

    // Empty state — no companies at all
    if (State.workspaces.length === 0) {
      c.innerHTML = `<div class="view-page">
        <div class="view-greeting">${TimeHelpers.greeting()}, Jim.</div>
        <div class="empty-state-welcome">
          <div class="empty-state-welcome-title">Welcome to Salt Desktop</div>
          <div class="empty-state-welcome-text">Create your first company to get started.</div>
          <button class="btn-create-company-cta" id="dashboard-create-company">+ Create Company</button>
        </div>
      </div>`;
      document.getElementById('dashboard-create-company')?.addEventListener('click', () => {
        Sidebar._showNewCompanyModal();
      });
      return;
    }

    const greeting = TimeHelpers.greeting();
    const services = State.services.filter(s => s.status === 'running');
    const buildingMissions = [];
    const planningMissions = [];

    Object.values(State.missions).forEach(list => {
      list.forEach(m => {
        if (m.name === 'General workspace chat') return;
        const phase = State.getMissionPhase(m);
        if (phase === 'building') buildingMissions.push(m);
        if (phase === 'planning') planningMissions.push(m);
      });
    });

    let html = `<div class="view-page">`;

    // Greeting
    html += `<div class="view-greeting">${greeting}, Jim.</div>`;

    // What's Running
    if (services.length > 0) {
      html += `<div class="view-section">`;
      html += `<div class="section-header"><span class="section-title">What's Running</span><span class="section-count">${services.length}</span></div>`;
      html += `<div class="flex flex-col gap-8">`;
      services.forEach(svc => {
        const ago = TimeHelpers.ago(svc.last_run_at);
        const schedule = TimeHelpers.scheduleLabel(svc.schedule);
        let summary = '';
        if (svc.name.includes('Gmail') || svc.name.includes('Email')) {
          summary = `checked ${svc.run_count} times &middot; ${schedule}`;
        } else if (svc.name.includes('BTC') || svc.name.includes('Price')) {
          summary = `${svc.error_count_24h || 0} alerts today &middot; ${schedule}`;
        } else {
          summary = `${svc.run_count} runs &middot; ${schedule}`;
        }
        html += `
          <div class="agent-row card-clickable" data-svc="${svc.id}">
            <div class="agent-dot healthy"></div>
            <div class="agent-info">
              <div class="agent-name">${this._esc(svc.name)}</div>
              <div class="agent-meta">${summary} &middot; last ran ${ago}</div>
            </div>
            <span class="agent-badge badge-healthy">HEALTHY</span>
          </div>`;
      });
      html += `</div></div>`;
    }

    // In Progress
    if (buildingMissions.length > 0) {
      html += `<div class="view-section">`;
      html += `<div class="section-header"><span class="section-title">In Progress</span><span class="section-count">${buildingMissions.length}</span></div>`;
      html += `<div class="flex flex-col gap-8">`;
      buildingMissions.forEach(m => {
        const comps = m.components || [];
        const built = comps.filter(c => c.status === 'built').length;
        const building = comps.find(c => c.status === 'building');
        const pct = comps.length > 0 ? Math.round((built / comps.length) * 100) : 0;
        const buildingText = building ? `${building.name} being built now` : 'working...';

        html += `
          <div class="mission-row card-clickable" data-mission="${m.id}">
            <span class="mission-icon" style="color: var(--warning);">\u25D0</span>
            <div class="mission-info">
              <div class="mission-name">${this._esc(m.name)}</div>
              <div class="mission-meta">${built} of ${comps.length} components built &middot; ${buildingText}</div>
              <div class="progress-bar mt-8" style="width:200px">
                <div class="progress-fill yellow" style="width:${pct}%"></div>
              </div>
            </div>
          </div>`;
      });
      html += `</div></div>`;
    }

    // Planning
    if (planningMissions.length > 0) {
      html += `<div class="view-section">`;
      html += `<div class="section-header"><span class="section-title">Planning</span></div>`;
      planningMissions.forEach(m => {
        html += `
          <div class="mission-row card-clickable" data-mission="${m.id}">
            <span class="mission-icon" style="color: var(--text-muted);">\u25CB</span>
            <div class="mission-info">
              <div class="mission-name">${this._esc(m.name)}</div>
              <div class="mission-meta">planning &middot; ${TimeHelpers.ago(m.updated_at)}</div>
            </div>
            <span class="agent-badge badge-planning">PLANNING</span>
          </div>`;
      });
      html += `</div>`;
    }

    // Recent activity feed
    html += `<div class="view-section">`;
    html += `<div class="section-header"><span class="section-title">Recent</span></div>`;
    html += `<div class="activity-feed">`;
    html += this._recentFeed();
    html += `</div></div>`;

    // Your Companies
    html += `<div class="view-section">`;
    html += `<div class="section-header"><span class="section-title">Your Companies</span><span class="section-count">${State.workspaces.length}</span></div>`;
    html += `<div class="company-cards">`;
    State.workspaces.forEach(ws => {
      const missions = State.missions[ws.id] || [];
      const realMissions = missions.filter(m => m.name !== 'General workspace chat');
      const svcCount = State.services.filter(s => s.workspace_id === ws.id && s.status === 'running').length;
      const buildCount = realMissions.filter(m => State.getMissionPhase(m) === 'building').length;

      html += `
        <div class="card card-clickable company-card" data-ws="${ws.id}">
          <div class="company-card-name">${this._esc(ws.name)}</div>
          <div class="company-card-stats">
            ${svcCount > 0 ? `<span class="company-card-stat"><span class="dot green"></span> ${svcCount} running</span>` : ''}
            ${buildCount > 0 ? `<span class="company-card-stat"><span class="dot yellow"></span> ${buildCount} building</span>` : ''}
            <span class="company-card-stat">${realMissions.length} agent${realMissions.length !== 1 ? 's' : ''}</span>
          </div>
        </div>`;
    });
    html += `</div></div>`;

    // Global chat
    html += `
      <div class="global-chat-bar">
        <div class="global-chat-inner">
          <input class="chat-input" placeholder="Ask me anything..." />
          <button class="chat-send-btn">Send</button>
        </div>
      </div>`;

    html += `</div>`;
    c.innerHTML = html;

    // Bind clicks
    c.querySelectorAll('[data-mission]').forEach(el => {
      el.addEventListener('click', () => Router.go('mission/' + el.dataset.mission));
    });
    c.querySelectorAll('[data-ws]').forEach(el => {
      el.addEventListener('click', () => Router.go('company/' + el.dataset.ws));
    });
    c.querySelectorAll('[data-svc]').forEach(el => {
      el.addEventListener('click', () => {
        // Find the mission behind this service
        const svc = State.services.find(s => s.id === el.dataset.svc);
        if (svc) {
          const mission = Object.values(State.missions).flat().find(m => m.name === svc.name);
          if (mission) Router.go('mission/' + mission.id);
        }
      });
    });
  },

  _recentFeed() {
    const events = State._recentEvents || [];
    if (events.length === 0) {
      return '<div class="empty-state" style="padding:20px"><span class="text-muted">No recent activity yet. Create a company to get started.</span></div>';
    }
    return events.map(e => `
      <div class="activity-item">
        <span class="activity-icon">${e.icon}</span>
        <span class="activity-text">${e.text}</span>
        <span class="activity-time">${e.time}</span>
      </div>
    `).join('');
  },

  _esc(str) {
    const d = document.createElement('div');
    d.textContent = str || '';
    return d.innerHTML;
  },
});
