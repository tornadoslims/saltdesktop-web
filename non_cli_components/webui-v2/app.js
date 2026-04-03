/* ============================================================
   Salt Desktop v0.1 — Core Application
   API Client, Router, State, Sidebar, Status Bar, SSE, Graph
   ============================================================ */

// ---------------------------------------------------------------------------
// API Client
// ---------------------------------------------------------------------------
const API = {
  base: '',
  async get(path) {
    const res = await fetch(this.base + path);
    if (!res.ok) throw new Error(`GET ${path} → ${res.status}`);
    return res.json();
  },
  async post(path, data) {
    const res = await fetch(this.base + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error(`POST ${path} → ${res.status}`);
    return res.json();
  },
  // SSE stream — returns EventSource
  stream(path) {
    return new EventSource(this.base + path);
  },
};

// ---------------------------------------------------------------------------
// State — single source of truth
// ---------------------------------------------------------------------------
const State = {
  workspaces: [],
  missions: {},   // workspace_id -> [missions]
  services: [],
  agents: [],
  components: {}, // workspace_id -> [components]
  graphs: {},     // workspace_id -> { nodes, edges }
  chatHistory: {}, // workspace_id -> { messages, total }
  signals: [],
  health: null,
  tickerEvents: [],
  _listeners: [],

  onChange(fn) { this._listeners.push(fn); },
  _notify(key) { this._listeners.forEach(fn => fn(key)); },

  async loadAll() {
    try {
      const [ws, svc, agents, health] = await Promise.all([
        API.get('/api/workspaces'),
        API.get('/api/services'),
        API.get('/api/agents'),
        API.get('/api/health'),
      ]);
      this.workspaces = ws;
      this.services = svc;
      this.agents = agents;
      this.health = health;

      // Load missions + components for each workspace
      await Promise.all(ws.map(async w => {
        const [missions, components, graph] = await Promise.all([
          API.get(`/api/workspaces/${w.id}/missions`),
          API.get(`/api/workspaces/${w.id}/components`),
          API.get(`/api/workspaces/${w.id}/graph`),
        ]);
        // Normalize mission fields: API returns mission_id/goal, UI expects id/name
        missions.forEach(m => {
          if (!m.id && m.mission_id) m.id = m.mission_id;
          if (!m.name && m.goal) m.name = m.goal;
        });
        this.missions[w.id] = missions;
        this.components[w.id] = components;
        this.graphs[w.id] = graph;
      }));

      this._notify('all');
    } catch (e) {
      console.error('State.loadAll failed:', e);
    }
  },

  async loadChatHistory(workspaceId, missionId) {
    try {
      let url = `/api/workspaces/${workspaceId}/chat/history`;
      if (missionId) url += `?mission_id=${encodeURIComponent(missionId)}`;
      const data = await API.get(url);
      const cacheKey = missionId || workspaceId;
      this.chatHistory[cacheKey] = data;
      return data;
    } catch (e) {
      console.error('loadChatHistory failed:', e);
      return { messages: [], total: 0 };
    }
  },

  // Derived helpers
  getService(missionName) {
    return this.services.find(s => s.name === missionName);
  },

  getMission(missionId) {
    for (const wid of Object.keys(this.missions)) {
      const m = this.missions[wid]?.find(m => m.id === missionId || m.mission_id === missionId);
      if (m) return m;
    }
    return null;
  },

  getWorkspace(id) {
    return this.workspaces.find(w => w.id === id);
  },

  // Determine mission phase
  getMissionPhase(mission) {
    if (!mission) return 'planning';
    const comps = mission.components || [];
    const allBuilt = comps.length > 0 && comps.every(c => c.status === 'built');
    const anyBuilding = comps.some(c => c.status === 'building');
    const svc = this.getService(mission.name);

    if (svc && svc.status === 'running') return 'live';
    if (allBuilt) return 'complete';
    if (anyBuilding || comps.some(c => c.status === 'built')) return 'building';
    if (mission.status === 'planning') return 'planning';
    if (comps.length === 0) return 'planning';
    return 'planning';
  },

  getAllComponents() {
    const all = [];
    for (const wid of Object.keys(this.components)) {
      all.push(...(this.components[wid] || []));
    }
    return all;
  },
};

// ---------------------------------------------------------------------------
// Router — hash-based SPA routing
// ---------------------------------------------------------------------------
const Router = {
  _routes: {},
  _current: null,
  _currentView: null,

  register(name, view) {
    this._routes[name] = view;
  },

  init() {
    window.addEventListener('hashchange', () => this._onRoute());
    this._onRoute();
  },

  go(route) {
    window.location.hash = '#/' + route;
  },

  _onRoute() {
    const hash = window.location.hash.slice(2) || 'dashboard';
    const parts = hash.split('/');
    let routeName = parts[0];
    const params = parts.slice(1);

    // Redirect removed routes to dashboard
    if (routeName === 'myai') {
      Router.go('dashboard');
      return;
    }

    // Destroy previous view
    if (this._currentView && this._currentView.destroy) {
      this._currentView.destroy();
    }

    const container = document.getElementById('view-container');
    if (!container) return;
    container.innerHTML = '';

    const view = this._routes[routeName];
    if (view) {
      this._current = routeName;
      this._currentView = view;
      view.render(container, ...params);
      Sidebar.setActive(routeName, params);
    } else {
      container.innerHTML = '<div class="empty-state"><div class="empty-state-text">Page not found</div></div>';
    }
  },

  getCurrent() {
    return this._current;
  },
};

// ---------------------------------------------------------------------------
// Time formatting helpers
// ---------------------------------------------------------------------------
const TimeHelpers = {
  ago(isoString) {
    if (!isoString) return '';
    const diff = Date.now() - new Date(isoString).getTime();
    const secs = Math.floor(diff / 1000);
    if (secs < 10) return 'just now';
    if (secs < 60) return `${secs}s ago`;
    const mins = Math.floor(secs / 60);
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    const days = Math.floor(hrs / 24);
    return `${days}d ago`;
  },

  greeting() {
    const h = new Date().getHours();
    if (h < 12) return 'Good morning';
    if (h < 17) return 'Good afternoon';
    return 'Good evening';
  },

  scheduleLabel(schedule) {
    if (!schedule) return '';
    if (schedule === '* * * * *') return 'every minute';
    if (schedule === '*/5 * * * *') return 'every 5 minutes';
    if (schedule === '*/15 * * * *') return 'every 15 minutes';
    if (schedule.startsWith('0 ')) return 'hourly';
    return schedule;
  },
};

// ---------------------------------------------------------------------------
// Sidebar
// ---------------------------------------------------------------------------
const Sidebar = {
  _expanded: {},

  render() {
    this._renderCompanies();
    this._bindNavClicks();
  },

  _bindNavClicks() {
    document.querySelectorAll('.sidebar-nav .nav-item').forEach(el => {
      el.addEventListener('click', (e) => {
        e.preventDefault();
        const route = el.dataset.route;
        Router.go(route);
      });
    });
  },

  _renderCompanies() {
    const container = document.getElementById('sidebar-companies');
    if (!container) return;
    let html = '';

    if (State.workspaces.length === 0) {
      // Empty state — no companies
      html += `<div class="sidebar-empty-state">
        <div class="sidebar-empty-text">No companies yet</div>
        <button class="btn-new-company-inline" id="btn-new-company-empty">+ New Company</button>
      </div>`;
    } else {
      State.workspaces.forEach(ws => {
        const wsId = ws.id;
        const missions = State.missions[wsId] || [];
        const expanded = this._expanded[wsId] !== false; // default expanded

        // Collect all agents (missions) with phases, sorted: running > building > planning > complete
        const phaseOrder = { live: 0, building: 1, planning: 2, complete: 3 };
        const allAgents = [];

        missions.forEach(m => {
          if (m.name === 'General workspace chat') return;
          const phase = State.getMissionPhase(m);
          allAgents.push({ mission: m, phase });
        });

        allAgents.sort((a, b) => (phaseOrder[a.phase] ?? 4) - (phaseOrder[b.phase] ?? 4));

        html += `<div class="company-section" data-ws="${wsId}">`;
        html += `<div class="company-header" data-ws="${wsId}">`;
        html += `<span class="company-toggle ${expanded ? '' : 'collapsed'}">&#9662;</span>`;
        html += `<span class="company-name">${this._esc(ws.name)}</span>`;
        html += `</div>`;
        html += `<div class="company-items ${expanded ? '' : 'collapsed'}" style="max-height:${expanded ? '800px' : '0'}">`;

        // Flat list — no sub-headers
        allAgents.forEach(({ mission, phase }) => {
          const dotClass = phase === 'live' ? 'running' : phase;
          const statusLabel = phase === 'live' ? 'running' : phase;
          const activity = this._getActivityLabel(mission, phase);
          html += `<div class="sidebar-entry" data-mission="${mission.id}" data-ws="${wsId}">`;
          html += `<div class="sidebar-entry-top">`;
          html += `<div class="sidebar-entry-dot ${dotClass}"></div>`;
          const displayName = (mission.name && mission.name !== 'New agent') ? (mission.name.length > 30 ? mission.name.slice(0, 30) + '...' : mission.name) : 'New Agent';
          html += `<span class="sidebar-entry-name">${this._esc(displayName)}</span>`;
          html += `<span class="sidebar-entry-status ${dotClass}">${statusLabel}</span>`;
          html += `</div>`;
          if (activity) html += `<div class="sidebar-entry-activity">${activity}</div>`;
          html += `</div>`;
        });

        html += `<div class="btn-new-agent" data-ws="${wsId}">+ New Agent</div>`;
        html += `</div>`; // company-items
        html += `</div>`; // company-section
      });

      html += `<div class="sidebar-new-company-row">`;
      html += `<button class="btn-new-company-inline" id="btn-new-company-bottom">+ New Company</button>`;
      html += `</div>`;
    }

    container.innerHTML = html;

    // Bind events
    container.querySelectorAll('.company-header').forEach(el => {
      el.addEventListener('click', (e) => {
        const wsId = el.dataset.ws;
        if (e.target.classList.contains('company-name')) {
          Router.go('company/' + wsId);
          return;
        }
        this._expanded[wsId] = this._expanded[wsId] === false;
        this._renderCompanies();
      });
    });

    container.querySelectorAll('.sidebar-entry').forEach(el => {
      el.addEventListener('click', () => {
        Router.go('mission/' + el.dataset.mission);
      });
    });

    container.querySelectorAll('.btn-new-agent').forEach(el => {
      el.addEventListener('click', async () => {
        try {
          const wsId = el.dataset.ws;
          const result = await API.post(`/api/workspaces/${wsId}/missions`, { goal: 'New agent' });
          const missionId = result.mission_id || result.id;
          await State.loadAll();
          Sidebar._renderCompanies();
          Router.go('mission/' + missionId);
        } catch (e) {
          console.error('Failed to create agent:', e);
        }
      });
    });

    // New company buttons
    const newCompanyBtns = container.querySelectorAll('.btn-new-company-inline');
    newCompanyBtns.forEach(btn => {
      btn.addEventListener('click', () => this._showNewCompanyModal());
    });
  },

  _getActivityLabel(mission, phase) {
    if (phase === 'live') {
      const svc = State.getService(mission.name);
      return this._getAgentActivity(svc);
    }
    if (phase === 'building') {
      const comps = mission.components || [];
      const built = comps.filter(c => c.status === 'built').length;
      return `building ${built}/${comps.length}`;
    }
    if (phase === 'planning') {
      return TimeHelpers.ago(mission.updated_at);
    }
    if (phase === 'complete') {
      return 'ready to deploy';
    }
    return null;
  },

  _showNewCompanyModal() {
    // Remove existing modal if any
    const existing = document.getElementById('new-company-modal');
    if (existing) existing.remove();

    const overlay = document.createElement('div');
    overlay.id = 'new-company-modal';
    overlay.className = 'modal-overlay';
    overlay.innerHTML = `
      <div class="modal-box">
        <div class="modal-title">New Company</div>
        <div class="modal-subtitle">What should we call your company?</div>
        <input class="modal-input" id="new-company-name" type="text" placeholder="e.g. My Startup" autofocus />
        <div class="modal-actions">
          <button class="modal-btn modal-btn-cancel" id="modal-cancel">Cancel</button>
          <button class="modal-btn modal-btn-confirm" id="modal-create">Create</button>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);

    const input = document.getElementById('new-company-name');
    const cancel = document.getElementById('modal-cancel');
    const create = document.getElementById('modal-create');

    const close = () => overlay.remove();
    cancel.addEventListener('click', close);
    overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });

    const doCreate = async () => {
      const name = input.value.trim();
      if (!name) return;
      try {
        const result = await API.post('/api/workspaces', { name });
        close();
        await State.loadAll();
        Sidebar._renderCompanies();
        if (result.id) Router.go('company/' + result.id);
      } catch (e) {
        console.error('Create company failed:', e);
        input.style.borderColor = 'var(--error)';
      }
    };

    create.addEventListener('click', doCreate);
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') doCreate(); });
    setTimeout(() => input.focus(), 50);
  },

  _getAgentActivity(svc) {
    if (!svc) return null;
    const runCount = svc.run_count || 0;
    const ago = TimeHelpers.ago(svc.last_run_at);
    if (svc.name.includes('Gmail') || svc.name.includes('Email')) {
      return `checked ${runCount} times &middot; ${ago}`;
    }
    if (svc.name.includes('BTC') || svc.name.includes('Price')) {
      return `price $67,432 &middot; ${ago}`;
    }
    return `${runCount} runs &middot; ${ago}`;
  },

  _getMissionActivity(mission, phase) {
    if (phase === 'building') {
      const comps = mission.components || [];
      const built = comps.filter(c => c.status === 'built').length;
      const building = comps.find(c => c.status === 'building');
      let text = `${built} of ${comps.length} components`;
      if (building) text = `building ${building.name} &middot; ` + text;
      return text;
    }
    if (phase === 'planning') {
      return `planning &middot; ${TimeHelpers.ago(mission.updated_at)}`;
    }
    return null;
  },

  setActive(routeName, params) {
    // Nav items (both top and bottom nav)
    document.querySelectorAll('.sidebar-nav .nav-item').forEach(el => {
      el.classList.toggle('active', el.dataset.route === routeName);
    });

    // Company headers
    document.querySelectorAll('.company-header').forEach(el => {
      el.classList.toggle('active', routeName === 'company' && params[0] === el.dataset.ws);
    });

    // Sidebar entries
    document.querySelectorAll('.sidebar-entry').forEach(el => {
      el.classList.toggle('active', routeName === 'mission' && params[0] === el.dataset.mission);
    });
  },

  _esc(str) {
    const d = document.createElement('div');
    d.textContent = str || '';
    return d.innerHTML;
  },
};

// ---------------------------------------------------------------------------
// Status Bar / Ticker
// ---------------------------------------------------------------------------
const Ticker = {
  _events: [],

  init() {
    this._seedEvents();
    this._render();
  },

  _seedEvents() {
    this._events = [];
  },

  addEvent(evt) {
    this._events.unshift(evt);
    if (this._events.length > 20) this._events.pop();
    this._render();
  },

  _render() {
    const track = document.getElementById('ticker-track');
    if (!track) return;

    // Duplicate for seamless scroll
    const items = this._events.map(e =>
      `<span class="ticker-item"><span class="ticker-dot ${e.icon}"></span>${this._esc(e.text)}</span>`
    ).join('');

    track.innerHTML = items + items;
  },

  _esc(str) {
    const d = document.createElement('div');
    d.textContent = str || '';
    return d.innerHTML;
  },
};

// ---------------------------------------------------------------------------
// SSE — live event stream
// ---------------------------------------------------------------------------
const SSE = {
  _source: null,

  connect() {
    if (this._source) this._source.close();

    this._source = API.stream('/api/events/stream?detail=ceo');

    this._source.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        this._handleEvent(data);
      } catch (e) {
        // keepalive or parse error, ignore
      }
    };

    this._source.onerror = () => {
      // Will auto-reconnect
      console.warn('SSE connection lost, reconnecting...');
    };
  },

  _handleEvent(data) {
    const type = data.type || '';

    // Only add ticker events for meaningful signal activity, skip generic/keepalive
    const ceoText = data.ceo_text || data.label || '';
    const genericTexts = ['AI is active', 'Thinking...', 'Connected', ''];
    if (ceoText && !genericTexts.some(g => ceoText.startsWith(g))) {
      const signalTypes = ['tool_start', 'tool_end', 'task_complete', 'task_failed', 'task_dispatched', 'subagent_start', 'subagent_end', 'session_start', 'session_end'];
      if (signalTypes.some(s => type.includes(s))) {
        const icon = type.includes('tool') ? 'yellow' : type.includes('task') ? 'cyan' : 'green';
        Ticker.addEvent({ icon, text: ceoText + ' (' + TimeHelpers.ago(data.timestamp) + ')' });
      }
    }

    // Update status bar summary
    if (type === 'system.health') {
      const sumEl = document.getElementById('status-summary');
      if (sumEl) {
        const active = data.tasks_active || 0;
        sumEl.textContent = active > 0 ? `${active} working` : 'Connected';
      }
    }

    // Dispatch to current view if it has an onEvent handler
    if (Router._currentView && Router._currentView.onEvent) {
      Router._currentView.onEvent(data);
    }
  },

  disconnect() {
    if (this._source) {
      this._source.close();
      this._source = null;
    }
  },
};

// ---------------------------------------------------------------------------
// Graph Renderer — canvas-based N8N-style
// ---------------------------------------------------------------------------
const GraphRenderer = {
  NODE_W: 260,
  NODE_H_BASE: 80,
  NODE_H_BUILDING: 110,
  NODE_H_ACTIVE: 120,
  NODE_PADDING: 14,
  NODE_RADIUS: 10,

  _canvas: null,
  _ctx: null,
  _nodes: [],
  _edges: [],
  _positions: {},
  _animFrame: null,
  _breathPhase: 0,
  _dpr: 1,
  _panX: 0,
  _panY: 0,
  _zoom: 1,
  _dragging: false,
  _dragStart: null,
  _missionPhase: 'building',

  init(canvas, nodes, edges, missionPhase) {
    this._canvas = canvas;
    this._ctx = canvas.getContext('2d');
    this._nodes = nodes || [];
    this._edges = edges || [];
    this._missionPhase = missionPhase || 'building';
    this._breathPhase = 0;
    this._dpr = window.devicePixelRatio || 1;
    this._panX = 0;
    this._panY = 0;
    this._zoom = 1;

    this._resize();
    this._layout();
    this._bindEvents();
    this._startAnimation();
  },

  destroy() {
    if (this._animFrame) cancelAnimationFrame(this._animFrame);
    this._animFrame = null;
    if (this._canvas) {
      this._canvas.removeEventListener('mousedown', this._onMouseDown);
      this._canvas.removeEventListener('wheel', this._onWheel);
    }
  },

  _resize() {
    const parent = this._canvas.parentElement;
    if (!parent) return;
    const w = parent.clientWidth;
    const h = parent.clientHeight;
    this._canvas.width = w * this._dpr;
    this._canvas.height = h * this._dpr;
    this._canvas.style.width = w + 'px';
    this._canvas.style.height = h + 'px';
    this._ctx.setTransform(this._dpr, 0, 0, this._dpr, 0, 0);
  },

  _layout() {
    // Simple left-to-right layout using topological sort
    const nodeMap = {};
    this._nodes.forEach(n => { nodeMap[n.id] = n; });

    // Build adjacency
    const inDegree = {};
    const adj = {};
    this._nodes.forEach(n => { inDegree[n.id] = 0; adj[n.id] = []; });
    this._edges.forEach(e => {
      const from = e.from || e.source;
      const to = e.to || e.target;
      if (adj[from]) adj[from].push(to);
      if (inDegree[to] !== undefined) inDegree[to]++;
    });

    // Topological levels
    const levels = [];
    const visited = new Set();
    let queue = Object.keys(inDegree).filter(id => inDegree[id] === 0);

    while (queue.length > 0) {
      levels.push([...queue]);
      queue.forEach(id => visited.add(id));
      const next = [];
      queue.forEach(id => {
        (adj[id] || []).forEach(to => {
          inDegree[to]--;
          if (inDegree[to] === 0 && !visited.has(to)) next.push(to);
        });
      });
      queue = next;
    }

    // Add any unvisited nodes
    this._nodes.forEach(n => {
      if (!visited.has(n.id)) {
        levels.push([n.id]);
        visited.add(n.id);
      }
    });

    // Position nodes
    const hGap = 320;
    const vGap = 140;
    const canvasW = this._canvas.width / this._dpr;
    const canvasH = this._canvas.height / this._dpr;

    const totalW = levels.length * hGap;
    const maxPerLevel = Math.max(...levels.map(l => l.length), 1);
    const totalH = maxPerLevel * vGap;

    const startX = (canvasW - totalW) / 2 + hGap / 2;
    const startY = (canvasH - totalH) / 2 + vGap / 2;

    this._positions = {};
    levels.forEach((level, li) => {
      const levelH = level.length * vGap;
      const levelStartY = startY + (totalH - levelH) / 2;
      level.forEach((id, ni) => {
        this._positions[id] = {
          x: startX + li * hGap,
          y: levelStartY + ni * vGap,
        };
      });
    });
  },

  _bindEvents() {
    this._onMouseDown = (e) => {
      this._dragging = true;
      this._dragStart = { x: e.clientX - this._panX, y: e.clientY - this._panY };
      this._canvas.style.cursor = 'grabbing';
    };
    this._onMouseMove = (e) => {
      if (!this._dragging) return;
      this._panX = e.clientX - this._dragStart.x;
      this._panY = e.clientY - this._dragStart.y;
    };
    this._onMouseUp = () => {
      this._dragging = false;
      this._canvas.style.cursor = 'grab';
    };
    this._onWheel = (e) => {
      e.preventDefault();
      const delta = e.deltaY > 0 ? 0.95 : 1.05;
      this._zoom = Math.max(0.3, Math.min(2.5, this._zoom * delta));
    };

    this._canvas.addEventListener('mousedown', this._onMouseDown);
    window.addEventListener('mousemove', this._onMouseMove);
    window.addEventListener('mouseup', this._onMouseUp);
    this._canvas.addEventListener('wheel', this._onWheel, { passive: false });
    this._canvas.style.cursor = 'grab';
  },

  _startAnimation() {
    const draw = () => {
      this._breathPhase += 0.02;
      this._draw();
      this._animFrame = requestAnimationFrame(draw);
    };
    draw();
  },

  _draw() {
    const ctx = this._ctx;
    const w = this._canvas.width / this._dpr;
    const h = this._canvas.height / this._dpr;

    ctx.save();
    ctx.clearRect(0, 0, w, h);

    // Background
    ctx.fillStyle = '#0d1117';
    ctx.fillRect(0, 0, w, h);

    // Grid dots
    ctx.fillStyle = '#1a1f27';
    const gridSize = 30;
    for (let gx = 0; gx < w; gx += gridSize) {
      for (let gy = 0; gy < h; gy += gridSize) {
        ctx.fillRect(gx, gy, 1, 1);
      }
    }

    // Apply pan and zoom
    ctx.translate(w / 2 + this._panX, h / 2 + this._panY);
    ctx.scale(this._zoom, this._zoom);
    ctx.translate(-w / 2, -h / 2);

    // Draw edges first
    this._drawEdges(ctx);

    // Draw nodes
    this._nodes.forEach(node => {
      this._drawNode(ctx, node);
    });

    ctx.restore();
  },

  _drawEdges(ctx) {
    this._edges.forEach(edge => {
      const fromId = edge.from || edge.source;
      const toId = edge.to || edge.target;
      const from = this._positions[fromId];
      const to = this._positions[toId];
      if (!from || !to) return;

      const fromNode = this._nodes.find(n => n.id === fromId);
      const toNode = this._nodes.find(n => n.id === toId);

      // Determine edge color based on source status
      const isDraftEdge = edge.is_draft || this._missionPhase === 'draft';
      let color = '#30363d';
      let alpha = 0.6;
      if (isDraftEdge) { color = '#64748b'; alpha = 0.3; }
      else if (fromNode && fromNode.status === 'built') { color = '#22c55e'; alpha = 0.5; }
      else if (fromNode && fromNode.status === 'building') { color = '#f59e0b'; alpha = 0.5; }

      const startX = from.x + this.NODE_W / 2;
      const startY = from.y;
      const endX = to.x - this.NODE_W / 2;
      const endY = to.y;

      // Bezier curve
      const cpOffset = Math.abs(endX - startX) * 0.4;
      ctx.beginPath();
      ctx.moveTo(startX, startY);
      ctx.bezierCurveTo(startX + cpOffset, startY, endX - cpOffset, endY, endX, endY);

      ctx.strokeStyle = color;
      ctx.globalAlpha = alpha;
      ctx.lineWidth = isDraftEdge ? 1.5 : 2;
      if (isDraftEdge) ctx.setLineDash([6, 4]);
      ctx.stroke();
      if (isDraftEdge) ctx.setLineDash([]);
      ctx.globalAlpha = 1;

      // Arrow head
      const angle = Math.atan2(endY - (endY - cpOffset * 0.01), endX - (endX - cpOffset));
      ctx.beginPath();
      ctx.moveTo(endX, endY);
      ctx.lineTo(endX - 8, endY - 4);
      ctx.lineTo(endX - 8, endY + 4);
      ctx.closePath();
      ctx.fillStyle = color;
      ctx.globalAlpha = alpha;
      ctx.fill();
      ctx.globalAlpha = 1;

      // Edge label
      if (edge.display_label) {
        const midX = (startX + endX) / 2;
        const midY = (startY + endY) / 2 - 10;
        ctx.font = '11px -apple-system, BlinkMacSystemFont, sans-serif';
        ctx.fillStyle = '#64748b';
        ctx.textAlign = 'center';
        ctx.fillText(edge.display_label, midX, midY);
      }
    });
  },

  _drawNode(ctx, node) {
    const pos = this._positions[node.id];
    if (!pos) return;

    const isDraft = node.is_draft || this._missionPhase === 'draft';
    const isBuilding = node.status === 'building';
    const isBuilt = node.status === 'built';
    const isPlanned = node.status === 'planned';
    const isLive = this._missionPhase === 'live' && isBuilt;
    const isActive = node.is_active;

    const nodeH = isActive ? this.NODE_H_ACTIVE : (isBuilding ? this.NODE_H_BUILDING : this.NODE_H_BASE);
    const x = pos.x - this.NODE_W / 2;
    const y = pos.y - nodeH / 2;
    const r = this.NODE_RADIUS;

    // Draft mode: ghosted with subtle pulse
    if (isDraft) {
      const pulseAlpha = 0.35 + Math.sin(this._breathPhase * 1.5) * 0.1;
      ctx.globalAlpha = pulseAlpha;

      // Background
      ctx.beginPath();
      this._roundRect(ctx, x, y, this.NODE_W, nodeH, r);
      ctx.fillStyle = '#141820';
      ctx.fill();

      // Dashed border
      ctx.strokeStyle = this._typeColor(node.type) || '#30363d';
      ctx.lineWidth = 1.5;
      ctx.setLineDash([6, 4]);
      ctx.stroke();
      ctx.setLineDash([]);

      const pad = this.NODE_PADDING;
      let ty = y + pad;

      // Icon + Name
      const icon = this._typeIcon(node.type);
      ctx.font = 'bold 14px -apple-system, BlinkMacSystemFont, sans-serif';
      ctx.fillStyle = '#e2e8f0';
      ctx.textAlign = 'left';
      ctx.fillText(icon + '  ' + node.label, x + pad, ty + 13);
      ty += 24;

      // Type badge
      const typeBadge = (node.type || '').toUpperCase();
      this._drawBadge(ctx, x + pad, ty, typeBadge, this._typeColor(node.type));

      // DRAFT badge
      const typeW = ctx.measureText(typeBadge).width + 16;
      this._drawBadge(ctx, x + pad + typeW + 6, ty, 'DRAFT', '#64748b');

      ctx.globalAlpha = 1;
      return;
    }

    // Glow for building/live
    if (isBuilding) {
      const glowAlpha = 0.15 + Math.sin(this._breathPhase * 2) * 0.08;
      ctx.shadowColor = '#f59e0b';
      ctx.shadowBlur = 16;
      ctx.globalAlpha = glowAlpha + 0.5;
    } else if (isLive) {
      const glowAlpha = 0.12 + Math.sin(this._breathPhase) * 0.06;
      ctx.shadowColor = '#22c55e';
      ctx.shadowBlur = 12;
      ctx.globalAlpha = glowAlpha + 0.7;
    }

    // Background
    ctx.beginPath();
    this._roundRect(ctx, x, y, this.NODE_W, nodeH, r);
    ctx.fillStyle = isPlanned ? '#141820' : '#1c2128';
    ctx.fill();

    // Border
    let borderColor = '#30363d';
    if (isBuilding) borderColor = '#f59e0b';
    else if (isBuilt && !isLive) borderColor = '#22c55e';
    else if (isLive) borderColor = '#22c55e';
    else if (isPlanned) borderColor = '#30363d';

    ctx.strokeStyle = borderColor;
    ctx.lineWidth = isPlanned ? 1 : 2;
    if (isPlanned) ctx.setLineDash([4, 4]);
    ctx.stroke();
    ctx.setLineDash([]);

    ctx.shadowColor = 'transparent';
    ctx.shadowBlur = 0;
    ctx.globalAlpha = isPlanned ? 0.6 : 1;

    const pad = this.NODE_PADDING;
    let ty = y + pad;

    // Icon + Name
    const icon = this._typeIcon(node.type);
    ctx.font = 'bold 14px -apple-system, BlinkMacSystemFont, sans-serif';
    ctx.fillStyle = '#e2e8f0';
    ctx.textAlign = 'left';
    ctx.fillText(icon + '  ' + node.label, x + pad, ty + 13);
    ty += 24;

    // Type badge + Status badge + Lines
    const typeBadge = (node.type || '').toUpperCase();
    const statusText = node.display_status || node.status;
    const lineCount = node.line_count || 0;

    // Type badge
    this._drawBadge(ctx, x + pad, ty, typeBadge, this._typeColor(node.type));

    // Status badge
    const typeW = ctx.measureText(typeBadge).width + 16;
    const statusColor = this._statusColor(node.status);
    this._drawBadge(ctx, x + pad + typeW + 6, ty, statusText, statusColor);

    // Line count
    if (lineCount > 0) {
      const statusW = ctx.measureText(statusText).width + 16;
      ctx.font = '11px -apple-system, BlinkMacSystemFont, sans-serif';
      ctx.fillStyle = '#64748b';
      ctx.fillText(`${lineCount} lines`, x + pad + typeW + statusW + 18, ty + 10);
    }
    ty += 22;

    // Progress bar (building)
    if (isBuilding) {
      const barW = this.NODE_W - pad * 2;
      const barH = 4;
      ctx.fillStyle = '#21262d';
      this._roundRect(ctx, x + pad, ty, barW, barH, 2);
      ctx.fill();

      const progress = node.progress_percent || 25;
      ctx.fillStyle = '#f59e0b';
      this._roundRect(ctx, x + pad, ty, barW * (progress / 100), barH, 2);
      ctx.fill();
      ty += 14;
    }

    // Active agent info
    if (isActive || isBuilding) {
      ctx.font = '12px -apple-system, BlinkMacSystemFont, sans-serif';
      ctx.fillStyle = '#94a3b8';
      const agentText = isBuilding ? 'Coder \u00b7 writing code' : 'running';
      ctx.fillText('\uD83D\uDD28 ' + agentText, x + pad, ty + 12);
    }

    ctx.globalAlpha = 1;
  },

  _drawBadge(ctx, x, y, text, color) {
    ctx.font = 'bold 10px -apple-system, BlinkMacSystemFont, sans-serif';
    const textW = ctx.measureText(text).width;
    const bw = textW + 12;
    const bh = 18;
    const br = 4;

    ctx.fillStyle = color + '22';
    this._roundRect(ctx, x, y, bw, bh, br);
    ctx.fill();

    ctx.fillStyle = color;
    ctx.textAlign = 'left';
    ctx.fillText(text, x + 6, y + 12);
  },

  _typeIcon(type) {
    const icons = {
      connector: '\u26A1',
      processor: '\u2699\uFE0F',
      ai: '\uD83E\uDDE0',
      output: '\uD83D\uDCE4',
      scheduler: '\u23F0',
      storage: '\uD83D\uDCBE',
    };
    return icons[type] || '\u2B1B';
  },

  _typeColor(type) {
    const colors = {
      connector: '#06b6d4',
      processor: '#f59e0b',
      ai: '#8b5cf6',
      output: '#22c55e',
      scheduler: '#3b82f6',
      storage: '#f472b6',
    };
    return colors[type] || '#64748b';
  },

  _statusColor(status) {
    const colors = {
      planned: '#64748b',
      building: '#f59e0b',
      built: '#22c55e',
      live: '#22c55e',
      testing: '#3b82f6',
      deployed: '#22c55e',
    };
    return colors[status] || '#64748b';
  },

  _roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + r);
    ctx.lineTo(x + w, y + h - r);
    ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    ctx.lineTo(x + r, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - r);
    ctx.lineTo(x, y + r);
    ctx.quadraticCurveTo(x, y, x + r, y);
    ctx.closePath();
  },

  zoomIn() { this._zoom = Math.min(2.5, this._zoom * 1.15); },
  zoomOut() { this._zoom = Math.max(0.3, this._zoom * 0.85); },
  resetView() { this._panX = 0; this._panY = 0; this._zoom = 1; },
};

// ---------------------------------------------------------------------------
// SaltApp — main entry point
// ---------------------------------------------------------------------------
const SaltApp = {
  async init() {
    await State.loadAll();
    Sidebar.render();
    Ticker.init();
    Router.init();
    SSE.connect();

    // Refresh data + sidebar every 15s
    setInterval(async () => {
      await State.loadAll();
      Sidebar._renderCompanies();
      Sidebar.setActive(Router._current, (window.location.hash.slice(2) || 'dashboard').split('/').slice(1));
    }, 15000);
  },
};
