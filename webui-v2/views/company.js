/* ============================================================
   Company Info View — Inside a Company
   Agents + Missions + Completed + New Agent
   ============================================================ */

Router.register('company', {
  _container: null,
  _wsId: null,

  render(container, wsId) {
    this._container = container;
    this._wsId = wsId;
    this._paint();
  },

  destroy() {
    this._container = null;
  },

  _paint() {
    const c = this._container;
    if (!c || !this._wsId) return;

    const ws = State.getWorkspace(this._wsId);
    if (!ws) {
      c.innerHTML = '<div class="empty-state"><div class="empty-state-text">Company not found</div></div>';
      return;
    }

    const missions = (State.missions[this._wsId] || []).filter(m => m.name !== 'General workspace chat');
    const agents = [];
    const activeMissions = [];
    const completedMissions = [];

    missions.forEach(m => {
      const phase = State.getMissionPhase(m);
      if (phase === 'live') agents.push({ mission: m, phase });
      else if (phase === 'complete') completedMissions.push({ mission: m, phase });
      else activeMissions.push({ mission: m, phase });
    });

    const desc = this._getDescription(ws);

    let html = `<div class="company-view">`;

    // Name + description
    html += `<div class="company-view-name">${this._esc(ws.name)}</div>`;
    html += `<div class="company-view-desc">${this._esc(desc)}</div>`;

    // Agents section
    html += `<div class="view-section">`;
    html += `<div class="section-header"><span class="section-title">AGENTS</span>`;
    if (agents.length > 0) html += `<span class="section-count">${agents.length} running</span>`;
    html += `</div>`;

    if (agents.length === 0) {
      html += `<div style="color:var(--text-dim); font-size:13px; padding:8px 0">No deployed agents yet. Complete an agent and deploy it.</div>`;
    } else {
      html += `<div class="flex flex-col gap-8">`;
      agents.forEach(({ mission }) => {
        const svc = State.getService(mission.name);
        const ago = svc ? TimeHelpers.ago(svc.last_run_at) : '';
        const schedule = svc ? TimeHelpers.scheduleLabel(svc.schedule) : '';
        const runs = svc ? svc.run_count : 0;

        html += `
          <div class="agent-row card-clickable" data-mission="${mission.id}">
            <div class="agent-dot healthy"></div>
            <div class="agent-info">
              <div class="agent-name">${this._esc(mission.name)}</div>
              <div class="agent-meta">healthy &middot; ${runs} runs &middot; ${schedule} &middot; last ran ${ago}</div>
            </div>
            <span class="agent-badge badge-healthy">HEALTHY</span>
          </div>`;
      });
      html += `</div>`;
    }
    html += `</div>`;

    // In Progress section
    html += `<div class="view-section">`;
    html += `<div class="section-header"><span class="section-title">IN PROGRESS</span>`;
    if (activeMissions.length > 0) html += `<span class="section-count">${activeMissions.length} in progress</span>`;
    html += `</div>`;

    if (activeMissions.length === 0) {
      html += `<div style="color:var(--text-dim); font-size:13px; padding:8px 0">No agents in progress.</div>`;
    } else {
      html += `<div class="flex flex-col gap-8">`;
      activeMissions.forEach(({ mission, phase }) => {
        const comps = mission.components || [];
        const built = comps.filter(c => c.status === 'built').length;
        const phaseIcon = phase === 'building' ? '\u25D0' : '\u25CB';
        const phaseColor = phase === 'building' ? 'var(--warning)' : 'var(--text-muted)';
        const badgeClass = phase === 'building' ? 'badge-building' : 'badge-planning';
        const badgeText = phase === 'building' ? 'BUILDING' : 'PLANNING';
        const meta = phase === 'building'
          ? `${built} of ${comps.length} components built`
          : `${comps.length} components planned`;

        html += `
          <div class="mission-row card-clickable" data-mission="${mission.id}">
            <span class="mission-icon" style="color:${phaseColor}">${phaseIcon}</span>
            <div class="mission-info">
              <div class="mission-name">${this._esc(mission.name)}</div>
              <div class="mission-meta">${meta}</div>
            </div>
            <span class="agent-badge ${badgeClass}">${badgeText}</span>
          </div>`;
      });
      html += `</div>`;
    }
    html += `</div>`;

    // Completed section
    if (completedMissions.length > 0) {
      html += `<div class="view-section">`;
      html += `<div class="section-header"><span class="section-title">Completed</span><span class="section-count">${completedMissions.length}</span></div>`;
      html += `<div class="flex flex-col gap-8">`;
      completedMissions.forEach(({ mission }) => {
        html += `
          <div class="mission-row card-clickable" data-mission="${mission.id}">
            <span class="mission-icon" style="color:var(--accent)">\u2713</span>
            <div class="mission-info">
              <div class="mission-name">${this._esc(mission.name)}</div>
              <div class="mission-meta">completed &middot; not deployed</div>
            </div>
            <span class="agent-badge badge-complete">COMPLETE</span>
          </div>`;
      });
      html += `</div></div>`;
    }

    // New Agent button
    html += `
      <div style="margin-top:24px">
        <button class="btn-primary" id="btn-new-mission-company">+ New Agent</button>
      </div>`;

    html += `</div>`;
    c.innerHTML = html;

    // Bind clicks
    c.querySelectorAll('[data-mission]').forEach(el => {
      el.addEventListener('click', () => Router.go('mission/' + el.dataset.mission));
    });
  },

  _getDescription(ws) {
    if (ws.name.includes('Personal') || ws.name.includes('Automation')) {
      return 'Automates repetitive work tasks \u2014 email monitoring, notifications, and reporting.';
    }
    if (ws.name.includes('Trading')) {
      return 'Price monitoring, alerts, and trading tools.';
    }
    return 'AI-powered company workspace.';
  },

  _esc(str) {
    const d = document.createElement('div');
    d.textContent = str || '';
    return d.innerHTML;
  },
});
