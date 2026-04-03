/* ============================================================
   Component Library — Trophy Case
   Browse everything built across all companies
   ============================================================ */

Router.register('library', {
  _container: null,

  render(container) {
    this._container = container;
    this._paint();
  },

  destroy() {
    this._container = null;
  },

  _paint() {
    const c = this._container;
    if (!c) return;

    const allComps = State.getAllComponents();
    const builtComps = allComps.filter(c => c.status === 'built');
    const totalLines = builtComps.reduce((sum, c) => sum + (c.line_count || 0), 0);

    // Group by type
    const groups = {};
    const typeOrder = ['connector', 'processor', 'ai', 'output', 'scheduler'];
    const typeLabels = {
      connector: 'Connectors',
      processor: 'Processors',
      ai: 'AI Modules',
      output: 'Outputs',
      scheduler: 'Schedulers',
    };
    const typeIcons = {
      connector: '\u26A1',
      processor: '\u2699\uFE0F',
      ai: '\uD83E\uDDE0',
      output: '\uD83D\uDCE4',
      scheduler: '\u23F0',
    };

    allComps.forEach(comp => {
      const t = comp.type || 'other';
      if (!groups[t]) groups[t] = [];
      groups[t].push(comp);
    });

    let html = `<div class="view-page">`;
    html += `<div class="view-greeting">Component Library</div>`;

    // Summary stats
    html += `
      <div style="display:flex; gap:24px; margin-bottom:28px; font-size:14px">
        <div style="color:var(--text-muted)"><span style="color:var(--text); font-weight:600; font-size:20px">${allComps.length}</span> components</div>
        <div style="color:var(--text-muted)"><span style="color:var(--success); font-weight:600; font-size:20px">${builtComps.length}</span> built</div>
        <div style="color:var(--text-muted)"><span style="color:var(--accent); font-weight:600; font-size:20px">${totalLines.toLocaleString()}</span> lines of code</div>
      </div>`;

    // Groups
    typeOrder.forEach(type => {
      const comps = groups[type];
      if (!comps || comps.length === 0) return;

      html += `<div class="view-section">`;
      html += `<div class="section-header">`;
      html += `<span class="section-title">${typeIcons[type] || ''} ${typeLabels[type] || type}</span>`;
      html += `<span class="section-count">${comps.length}</span>`;
      html += `</div>`;

      html += `<div class="library-grid">`;
      comps.forEach(comp => {
        const isBuilt = comp.status === 'built';
        const mission = this._findMission(comp.mission_id);
        const missionName = mission ? mission.name : '';
        const ago = comp.built_at ? TimeHelpers.ago(comp.built_at) : '';

        html += `
          <div class="card component-card">
            <div class="component-card-header">
              <div class="component-card-icon ${comp.type}">${typeIcons[comp.type] || '\u2B1B'}</div>
              <div>
                <div class="component-card-name">${this._esc(comp.name)}</div>
              </div>
              <span class="component-card-type type-${comp.type}">${(comp.type || '').toUpperCase()}</span>
            </div>
            <div class="component-card-desc">${this._esc(comp.description || '')}</div>
            <div class="component-card-stats">
              ${isBuilt && comp.line_count ? `<span class="component-card-stat">${comp.line_count} lines</span>` : ''}
              ${missionName ? `<span class="component-card-stat">used by ${this._esc(missionName)}</span>` : ''}
              ${ago ? `<span class="component-card-stat">built ${ago}</span>` : ''}
              ${!isBuilt ? `<span class="component-card-stat" style="color:var(--text-dim)">${comp.status}</span>` : ''}
            </div>
          </div>`;
      });
      html += `</div></div>`;
    });

    html += `</div>`;
    c.innerHTML = html;
  },

  _findMission(missionId) {
    if (!missionId) return null;
    return State.getMission(missionId);
  },

  _esc(str) {
    const d = document.createElement('div');
    d.textContent = str || '';
    return d.innerHTML;
  },
});
