/* ============================================================
   My AI View — Building + Running sections
   The user's AI workforce at a glance
   ============================================================ */

Router.register('myai', {
  _container: null,

  render(container) {
    this._container = container;
    this._paint();
  },

  destroy() {
    this._container = null;
  },

  onEvent(data) {
    // Could live-update swarm activity here
  },

  _paint() {
    const c = this._container;
    if (!c) return;

    const services = State.services.filter(s => s.status === 'running');
    const buildingMissions = [];

    Object.values(State.missions).forEach(list => {
      list.forEach(m => {
        if (m.name === 'General workspace chat') return;
        if (State.getMissionPhase(m) === 'building') buildingMissions.push(m);
      });
    });

    let html = `<div class="myai-page">`;
    html += `<div class="view-greeting">My AI</div>`;

    // ── Building section ──
    html += `<div class="view-section">`;
    html += `<div class="section-header"><span class="section-title">Building</span>`;
    if (buildingMissions.length > 0) {
      html += `<span class="section-count">${buildingMissions.length} active</span>`;
    }
    html += `</div>`;

    if (buildingMissions.length === 0) {
      html += `<div class="empty-state"><div class="empty-state-text" style="color:var(--text-dim)">No missions currently being built.</div></div>`;
    } else {
      buildingMissions.forEach(m => {
        html += this._renderSwarm(m);
      });
    }
    html += `</div>`;

    // ── Running section ──
    html += `<div class="view-section">`;
    html += `<div class="section-header"><span class="section-title">Running</span>`;
    if (services.length > 0) {
      html += `<span class="section-count">${services.length} live</span>`;
    }
    html += `</div>`;

    if (services.length === 0) {
      html += `<div class="empty-state"><div class="empty-state-text" style="color:var(--text-dim)">No services running yet. Deploy a completed mission to see it here.</div></div>`;
    } else {
      html += `<div class="flex flex-col gap-8">`;
      services.forEach(svc => {
        const ago = TimeHelpers.ago(svc.last_run_at);
        const schedule = TimeHelpers.scheduleLabel(svc.schedule);
        html += `
          <div class="agent-row card-clickable" data-svc="${svc.id}">
            <div class="agent-dot healthy"></div>
            <div class="agent-info">
              <div class="agent-name">${this._esc(svc.name)}</div>
              <div class="agent-meta">healthy &middot; ${schedule} &middot; ${svc.run_count} runs &middot; last ran ${ago}</div>
            </div>
            <span class="agent-badge badge-healthy">HEALTHY</span>
          </div>`;
      });
      html += `</div>`;
    }
    html += `</div>`;

    html += `</div>`;
    c.innerHTML = html;

    // Bind clicks
    c.querySelectorAll('[data-mission]').forEach(el => {
      el.addEventListener('click', () => Router.go('mission/' + el.dataset.mission));
    });
    c.querySelectorAll('[data-svc]').forEach(el => {
      el.addEventListener('click', () => {
        const svc = State.services.find(s => s.id === el.dataset.svc);
        if (svc) {
          const mission = Object.values(State.missions).flat().find(m => m.name === svc.name);
          if (mission) Router.go('mission/' + mission.id);
        }
      });
    });
  },

  _renderSwarm(mission) {
    const comps = mission.components || [];
    const built = comps.filter(c => c.status === 'built');
    const building = comps.filter(c => c.status === 'building');
    const planned = comps.filter(c => c.status === 'planned');
    const totalWorkers = building.length + 1; // +1 for researcher/analyst variety

    let html = `<div class="swarm-container" data-mission="${mission.id}" style="cursor:pointer">`;
    html += `<div class="swarm-header">`;
    html += `<div class="swarm-title">Building ${this._esc(mission.name)}</div>`;
    html += `<div class="swarm-count">${totalWorkers} agents working</div>`;
    html += `</div>`;

    // Built components
    built.forEach(comp => {
      html += `
        <div class="swarm-worker" style="opacity: 0.6">
          <span class="swarm-role">\u2705</span>
          <span class="swarm-component">${this._esc(comp.name)}</span>
          <span class="swarm-activity">done &middot; ${comp.line_count || '?'} lines</span>
        </div>`;
    });

    // Building components
    building.forEach(comp => {
      html += `
        <div class="swarm-worker">
          <span class="swarm-role">\uD83D\uDD28 Coder</span>
          <span class="swarm-component">building ${this._esc(comp.name)}</span>
          <span class="swarm-activity">writing code</span>
        </div>`;
    });

    // Add a researcher for variety if there are planned components
    if (planned.length > 0) {
      html += `
        <div class="swarm-worker">
          <span class="swarm-role">\uD83D\uDD0D Researcher</span>
          <span class="swarm-component">investigating APIs</span>
          <span class="swarm-activity">reading docs</span>
        </div>`;
    }

    // Queued components
    planned.forEach(comp => {
      html += `
        <div class="swarm-queued">
          <span class="swarm-queued-dot"></span>
          <span>${this._esc(comp.name)}</span>
          <span style="margin-left:auto; color:var(--text-dim)">queued</span>
        </div>`;
    });

    // Progress summary
    const pct = comps.length > 0 ? Math.round((built.length / comps.length) * 100) : 0;
    html += `
      <div style="margin-top:12px">
        <div style="display:flex; justify-content:space-between; font-size:12px; color:var(--text-muted); margin-bottom:4px">
          <span>${built.length} of ${comps.length} components built</span>
          <span>${pct}%</span>
        </div>
        <div class="progress-bar">
          <div class="progress-fill yellow" style="width:${pct}%"></div>
        </div>
      </div>`;

    html += `</div>`;
    return html;
  },

  _esc(str) {
    const d = document.createElement('div');
    d.textContent = str || '';
    return d.innerHTML;
  },
});
