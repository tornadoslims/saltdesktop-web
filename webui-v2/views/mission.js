/* ============================================================
   Mission View — Phase Adaptive
   Planning | Building | Complete | Live
   ============================================================ */

Router.register('mission', {
  _container: null,
  _missionId: null,
  _mission: null,
  _phase: null,
  _graphInstance: null,
  _resizeObserver: null,
  _previewData: null,
  _previewLoading: false,

  render(container, missionId) {
    this._container = container;
    this._missionId = missionId;
    this._mission = State.getMission(missionId);
    if (!this._mission) {
      container.innerHTML = '<div class="empty-state"><div class="empty-state-text">Mission not found</div></div>';
      return;
    }
    this._phase = State.getMissionPhase(this._mission);
    this._paint();
  },

  destroy() {
    GraphRenderer.destroy();
    if (this._resizeObserver) this._resizeObserver.disconnect();
    this._container = null;
  },

  onEvent(data) {
    // Could update swarm or activity in real-time
  },

  _paint() {
    const c = this._container;
    const m = this._mission;
    const phase = this._phase;
    if (!c || !m) return;

    c.innerHTML = '';
    c.style.padding = '0';
    c.style.overflow = 'hidden';
    c.style.height = '100%';

    const wrapper = document.createElement('div');
    wrapper.className = 'mission-view';
    c.appendChild(wrapper);

    // Header with mission name
    const header = document.createElement('div');
    header.className = 'mission-header';
    header.innerHTML = `
      <span class="mission-header-name">${this._esc(m.name || m.goal || 'New Agent')}</span>
    `;
    wrapper.appendChild(header);

    // Lifecycle progress bar
    const lifecycleBar = document.createElement('div');
    lifecycleBar.className = 'lifecycle-bar';

    const stages = [
      { key: 'planning', label: "PLANNING" },
      { key: 'specd', label: "SPEC'D" },
      { key: 'building', label: 'BUILDING' },
      { key: 'live', label: 'LIVE' },
    ];
    // Map phase to stage index
    const phaseToIdx = { planning: 0, specd: 1, building: 2, complete: 3, live: 3 };
    const currentIdx = phaseToIdx[phase] !== undefined ? phaseToIdx[phase] : 0;

    let lifecycleHtml = '';
    stages.forEach((s, i) => {
      let cls = 'lifecycle-stage';
      let dot = '';
      if (i < currentIdx) {
        cls += ' completed';
        dot = '<span class="lifecycle-dot completed"></span>';
      } else if (i === currentIdx) {
        cls += ' active';
        dot = '<span class="lifecycle-dot active"></span>';
      } else {
        cls += ' future';
        dot = '<span class="lifecycle-dot future"></span>';
      }
      lifecycleHtml += `<div class="${cls}">${dot} ${s.label}</div>`;
      if (i < stages.length - 1) {
        const connCls = i < currentIdx ? 'lifecycle-connector completed' : 'lifecycle-connector';
        lifecycleHtml += `<div class="${connCls}"></div>`;
      }
    });

    // Action button for current phase
    let actionBtn = '';
    if (phase === 'planning') {
      // Lock It In is shown in the graph pane, but also show a small hint
    } else if (phase === 'specd') {
      actionBtn = '<button class="btn-primary btn-lifecycle-action" data-action="build">Build It</button>';
    } else if (phase === 'complete') {
      actionBtn = '<button class="btn-success btn-lifecycle-action" data-action="deploy">Deploy as Agent</button>';
    }

    lifecycleBar.innerHTML = lifecycleHtml + (actionBtn ? `<div style="margin-left:auto">${actionBtn}</div>` : '');
    wrapper.appendChild(lifecycleBar);

    // Bind lifecycle action buttons
    const actionBtnEl = lifecycleBar.querySelector('.btn-lifecycle-action');
    if (actionBtnEl) {
      actionBtnEl.addEventListener('click', async () => {
        const action = actionBtnEl.dataset.action;
        const missionId = m.id || m.mission_id;
        actionBtnEl.disabled = true;
        actionBtnEl.textContent = 'Working...';
        try {
          if (action === 'build') {
            // Approve creates components + tasks, then build dispatches to Claude Code
            await API.post(`/api/missions/${missionId}/approve`);
            // Fire build in background (don't await -- it takes minutes)
            API.post(`/api/missions/${missionId}/build`).catch(e => console.warn('Build dispatch:', e));
          } else if (action === 'deploy') {
            await API.post(`/api/workspaces/${m.company_id}/promote`);
          }
          await State.loadAll();
          Sidebar.render();
          this._mission = State.getMission(missionId);
          this._phase = State.getMissionPhase(this._mission);
          this._paint();
        } catch (e) {
          console.error('Lifecycle action failed:', e);
          actionBtnEl.disabled = false;
          actionBtnEl.textContent = action === 'build' ? 'Build It' : 'Deploy as Agent';
        }
      });
    }

    // Body
    const body = document.createElement('div');
    body.className = 'mission-body';
    wrapper.appendChild(body);

    if (phase === 'planning') {
      this._renderPlanning(body, m);
    } else if (phase === 'building') {
      this._renderBuilding(body, m);
    } else if (phase === 'complete') {
      this._renderComplete(body, m);
    } else if (phase === 'live') {
      this._renderLive(body, m);
    }
  },

  // ── PLANNING: Chat + Draft Graph (50/50 split) ──
  _renderPlanning(body, m) {
    const hasPreview = this._previewData && this._previewData.components && this._previewData.components.length > 0;

    body.innerHTML = `
      <div class="mission-split">
        <div class="mission-chat-pane">
          <div class="chat-messages" id="chat-messages"></div>
          <div class="chat-input-bar">
            <input class="chat-input" placeholder="Describe what you want to build..." />
            <button class="chat-send-btn">Send</button>
          </div>
        </div>
        <div class="mission-graph-pane">
          <div class="graph-container" id="mission-graph">
            <canvas id="graph-canvas"></canvas>
            <div class="graph-toolbar">
              <button class="graph-btn" onclick="GraphRenderer.zoomIn()">+</button>
              <button class="graph-btn" onclick="GraphRenderer.zoomOut()">&minus;</button>
              <button class="graph-btn" onclick="GraphRenderer.resetView()">\u2302</button>
            </div>
            <div class="draft-graph-status" id="draft-graph-status">
              ${this._previewLoading ? '<span class="draft-loading">Updating preview...</span>' : ''}
              ${!hasPreview && !this._previewLoading ? '<span class="draft-empty">Components will appear as you describe what you want to build...</span>' : ''}
            </div>
            ${hasPreview ? `
              <div class="draft-lock-btn-container" id="draft-lock-btn">
                <button class="btn-primary btn-lock-it-in">Lock It In</button>
              </div>` : ''}
          </div>
        </div>
      </div>
    `;

    this._loadChat(m);
    this._bindChatSend(m);

    // Render preview graph or real graph
    if (hasPreview) {
      this._initPreviewGraph(m);
    } else {
      this._initGraph(m, 'planning');
    }

    // Bind Lock It In button
    if (hasPreview) {
      const lockBtn = document.getElementById('draft-lock-btn');
      if (lockBtn) {
        lockBtn.querySelector('button').addEventListener('click', () => this._lockItIn(m));
      }
    }
  },

  _bindChatSend(m) {
    const input = this._container.querySelector('.chat-input');
    const btn = this._container.querySelector('.chat-send-btn');
    if (!input || !btn) return;

    const send = async () => {
      const text = input.value.trim();
      if (!text) return;
      input.value = '';

      // Append user message to chat UI immediately
      const msgContainer = document.getElementById('chat-messages');
      if (msgContainer) {
        const userDiv = document.createElement('div');
        userDiv.className = 'chat-msg user';
        userDiv.textContent = text;
        msgContainer.appendChild(userDiv);
        msgContainer.scrollTop = msgContainer.scrollHeight;
      }

      // Send chat message via API — returns SSE stream
      try {
        const resp = await fetch(API.base + '/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            workspace_id: m.company_id,
            mission_id: m.id || m.mission_id,
            message: text,
          }),
        });

        if (!resp.ok) {
          console.error('Chat send failed:', resp.status);
          return;
        }

        // Create assistant message bubble for streaming
        let aDiv = null;
        let fullContent = '';
        if (msgContainer) {
          aDiv = document.createElement('div');
          aDiv.className = 'chat-msg assistant';
          aDiv.textContent = '';
          msgContainer.appendChild(aDiv);
          msgContainer.scrollTop = msgContainer.scrollHeight;
        }

        // Parse SSE stream
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop(); // keep incomplete line in buffer

          for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed || !trimmed.startsWith('data: ')) continue;
            const payload = trimmed.slice(6);
            if (payload === '[DONE]') continue;

            try {
              const parsed = JSON.parse(payload);
              // OpenAI SSE format: choices[0].delta.content
              const delta = parsed.choices && parsed.choices[0] && parsed.choices[0].delta;
              if (delta && delta.content) {
                fullContent += delta.content;
                if (aDiv) {
                  let rendered = this._esc(fullContent);
                  rendered = rendered.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
                  rendered = rendered.replace(/\n/g, '<br>');
                  aDiv.innerHTML = rendered;
                  msgContainer.scrollTop = msgContainer.scrollHeight;
                }
              }
              // Also handle direct content field (command responses)
              if (parsed.content && !parsed.choices) {
                fullContent += parsed.content;
                if (aDiv) {
                  let rendered = this._esc(fullContent);
                  rendered = rendered.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
                  rendered = rendered.replace(/\n/g, '<br>');
                  aDiv.innerHTML = rendered;
                  msgContainer.scrollTop = msgContainer.scrollHeight;
                }
              }
            } catch (e) {
              // Non-JSON line, skip
            }
          }
        }

        // If no content was streamed, remove empty bubble
        if (aDiv && !fullContent) {
          aDiv.remove();
        }

        // Trigger async preview generation (don't block)
        this._fetchPreview(m);
      } catch (e) {
        console.error('Chat send failed:', e);
      }
    };

    btn.addEventListener('click', send);
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        send();
      }
    });
  },

  async _fetchPreview(m) {
    const missionId = m.id || m.mission_id;

    // Show loading state
    this._previewLoading = true;
    const statusEl = document.getElementById('draft-graph-status');
    if (statusEl) {
      statusEl.innerHTML = '<span class="draft-loading">Updating preview...</span>';
    }

    try {
      const result = await API.post(`/api/missions/${missionId}/generate-preview`);
      if (result && result.components) {
        this._previewData = result;
      }
    } catch (e) {
      console.error('Preview generation failed:', e);
    } finally {
      this._previewLoading = false;
    }

    // Re-render the graph pane with preview data (without re-rendering entire view)
    const hasPreview = this._previewData && this._previewData.components && this._previewData.components.length > 0;

    if (statusEl) {
      if (hasPreview) {
        statusEl.innerHTML = '';
      } else {
        statusEl.innerHTML = '<span class="draft-empty">Components will appear as you describe what you want to build...</span>';
      }
    }

    if (hasPreview) {
      this._initPreviewGraph(m);

      // Add Lock It In button if not present
      const graphPane = document.getElementById('mission-graph');
      if (graphPane && !document.getElementById('draft-lock-btn')) {
        const lockDiv = document.createElement('div');
        lockDiv.className = 'draft-lock-btn-container';
        lockDiv.id = 'draft-lock-btn';
        lockDiv.innerHTML = '<button class="btn-primary btn-lock-it-in">Lock It In</button>';
        graphPane.appendChild(lockDiv);
        lockDiv.querySelector('button').addEventListener('click', () => this._lockItIn(m));
      }
    }
  },

  _initPreviewGraph(m) {
    const preview = this._previewData;
    if (!preview || !preview.components) return;

    // Convert preview data to graph nodes/edges format
    const nodes = preview.components.map((c, i) => ({
      id: 'preview-' + i,
      label: c.name,
      type: c.type || 'processor',
      status: 'draft',
      display_status: 'DRAFT',
      is_draft: true,
    }));

    // Build name-to-id lookup
    const nameToId = {};
    preview.components.forEach((c, i) => {
      nameToId[c.name] = 'preview-' + i;
    });

    const edges = (preview.connections || []).map(c => ({
      from: nameToId[c.from] || '',
      to: nameToId[c.to] || '',
      display_label: c.label || '',
      is_draft: true,
    })).filter(e => e.from && e.to);

    setTimeout(() => {
      const canvas = document.getElementById('graph-canvas');
      if (!canvas) return;
      const container = document.getElementById('mission-graph');
      if (container) {
        canvas.style.width = '100%';
        canvas.style.height = '100%';
      }
      GraphRenderer.init(canvas, nodes, edges, 'draft');

      if (container && !this._resizeObserver) {
        this._resizeObserver = new ResizeObserver(() => {
          GraphRenderer._resize();
          GraphRenderer._layout();
        });
        this._resizeObserver.observe(container);
      }
    }, 50);
  },

  async _lockItIn(m) {
    const missionId = m.id || m.mission_id;
    const lockBtn = document.querySelector('.btn-lock-it-in');
    if (lockBtn) {
      lockBtn.textContent = 'Generating full plan...';
      lockBtn.disabled = true;
    }

    try {
      await API.post(`/api/missions/${missionId}/generate`);
      // Reload state and re-render
      await State.loadAll();
      Sidebar.render();
      this._mission = State.getMission(missionId);
      this._previewData = null;
      this._phase = State.getMissionPhase(this._mission);
      this._paint();
    } catch (e) {
      console.error('Lock It In failed:', e);
      if (lockBtn) {
        lockBtn.textContent = 'Lock It In';
        lockBtn.disabled = false;
      }
    }
  },

  // ── BUILDING: Full graph + swarm panel below ──
  _renderBuilding(body, m) {
    const comps = m.components || [];
    const built = comps.filter(c => c.status === 'built').length;
    const building = comps.filter(c => c.status === 'building');
    const planned = comps.filter(c => c.status === 'planned');

    body.innerHTML = `
      <div style="display:flex; flex-direction:column; width:100%; height:100%">
        <div class="mission-full-graph" style="flex:1; min-height:300px">
          <div class="graph-container" id="mission-graph">
            <canvas id="graph-canvas"></canvas>
            <div class="graph-toolbar">
              <button class="graph-btn" onclick="GraphRenderer.zoomIn()">+</button>
              <button class="graph-btn" onclick="GraphRenderer.zoomOut()">&minus;</button>
              <button class="graph-btn" onclick="GraphRenderer.resetView()">\u2302</button>
            </div>
          </div>
        </div>
        <div style="padding:16px 24px; border-top:1px solid var(--border); background:var(--bg-panel); max-height:280px; overflow-y:auto" id="swarm-panel">
          ${this._buildSwarmHtml(m, comps, built, building, planned)}
        </div>
      </div>
    `;

    this._initGraph(m, 'building');
  },

  // ── COMPLETE: Graph + deploy actions ──
  _renderComplete(body, m) {
    body.innerHTML = `
      <div style="display:flex; flex-direction:column; width:100%; height:100%">
        <div class="mission-full-graph" style="flex:1; min-height:400px">
          <div class="graph-container" id="mission-graph">
            <canvas id="graph-canvas"></canvas>
            <div class="graph-toolbar">
              <button class="graph-btn" onclick="GraphRenderer.zoomIn()">+</button>
              <button class="graph-btn" onclick="GraphRenderer.zoomOut()">&minus;</button>
              <button class="graph-btn" onclick="GraphRenderer.resetView()">\u2302</button>
            </div>
          </div>
        </div>
        <div style="padding:20px 24px; border-top:1px solid var(--border); background:var(--bg-panel); display:flex; align-items:center; gap:12px">
          <div style="flex:1">
            <div style="font-size:15px; font-weight:600; color:var(--text)">All components built</div>
            <div style="font-size:13px; color:var(--text-muted); margin-top:2px">Ready to deploy. Test it first or go live.</div>
          </div>
          <button class="btn-secondary">Try It</button>
          <button class="btn-success">Deploy as Agent</button>
        </div>
      </div>
    `;

    this._initGraph(m, 'complete');
  },

  // ── LIVE: Health bar + graph + controls ──
  _renderLive(body, m) {
    const svc = State.getService(m.name);
    const ago = svc ? TimeHelpers.ago(svc.last_run_at) : 'unknown';
    const schedule = svc ? TimeHelpers.scheduleLabel(svc.schedule) : '';
    const runs = svc ? svc.run_count : 0;

    body.innerHTML = `
      <div style="display:flex; flex-direction:column; width:100%; height:100%">
        <div style="padding:16px 24px; flex-shrink:0">
          <div class="health-bar">
            <div class="health-dot"></div>
            <div class="health-name">${this._esc(m.name)}</div>
            <span class="health-badge">HEALTHY</span>
            <div class="health-stats">
              <span>${runs} runs</span>
              <span>${schedule}</span>
              <span>last ran ${ago}</span>
            </div>
          </div>
        </div>
        <div class="mission-full-graph" style="flex:1; min-height:300px">
          <div class="graph-container" id="mission-graph">
            <canvas id="graph-canvas"></canvas>
            <div class="graph-toolbar">
              <button class="graph-btn" onclick="GraphRenderer.zoomIn()">+</button>
              <button class="graph-btn" onclick="GraphRenderer.zoomOut()">&minus;</button>
              <button class="graph-btn" onclick="GraphRenderer.resetView()">\u2302</button>
            </div>
          </div>
        </div>
        <div style="padding:12px 24px; border-top:1px solid var(--border); background:var(--bg-panel)">
          <div class="agent-controls">
            <button class="agent-control-btn">Pause</button>
            <button class="agent-control-btn">Restart</button>
            <button class="agent-control-btn danger">Undeploy</button>
          </div>
        </div>
      </div>
    `;

    this._initGraph(m, 'live');
  },

  _buildSwarmHtml(m, comps, built, building, planned) {
    const totalWorkers = building.length + (planned.length > 0 ? 1 : 0);
    let html = `
      <div class="swarm-header">
        <div class="swarm-title">Building ${this._esc(m.name)}</div>
        <div class="swarm-count">${totalWorkers} agents working</div>
      </div>`;

    // Done
    comps.filter(c => c.status === 'built').forEach(comp => {
      html += `
        <div class="swarm-worker" style="opacity:0.6">
          <span class="swarm-role">\u2705</span>
          <span class="swarm-component">${this._esc(comp.name)}</span>
          <span class="swarm-activity">done</span>
        </div>`;
    });

    // Building
    building.forEach(comp => {
      html += `
        <div class="swarm-worker">
          <span class="swarm-role">\uD83D\uDD28 Coder</span>
          <span class="swarm-component">building ${this._esc(comp.name)}</span>
          <span class="swarm-activity">writing code</span>
        </div>`;
    });

    // Researcher
    if (planned.length > 0) {
      html += `
        <div class="swarm-worker">
          <span class="swarm-role">\uD83D\uDD0D Researcher</span>
          <span class="swarm-component">investigating APIs</span>
          <span class="swarm-activity">reading docs</span>
        </div>`;
    }

    // Queued
    planned.forEach(comp => {
      html += `
        <div class="swarm-queued">
          <span class="swarm-queued-dot"></span>
          <span>${this._esc(comp.name)}</span>
          <span style="margin-left:auto; color:var(--text-dim)">queued</span>
        </div>`;
    });

    // Progress
    const pct = comps.length > 0 ? Math.round((built / comps.length) * 100) : 0;
    html += `
      <div style="margin-top:12px; display:flex; align-items:center; gap:16px">
        <div style="flex:1">
          <div style="display:flex; justify-content:space-between; font-size:12px; color:var(--text-muted); margin-bottom:4px">
            <span>${built} of ${comps.length} components built</span>
            <span>${pct}%</span>
          </div>
          <div class="progress-bar"><div class="progress-fill yellow" style="width:${pct}%"></div></div>
        </div>
      </div>`;

    return html;
  },

  async _loadChat(m) {
    const wsId = m.company_id;
    const missionId = m.id || m.mission_id;
    const data = await State.loadChatHistory(wsId, missionId);
    const container = document.getElementById('chat-messages');
    if (!container) return;

    let html = '';
    (data.messages || []).forEach(msg => {
      const cls = msg.role === 'user' ? 'user' : 'assistant';
      // Simple markdown-like bold
      let content = this._esc(msg.content);
      content = content.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
      content = content.replace(/\n/g, '<br>');
      html += `<div class="chat-msg ${cls}">${content}</div>`;
    });
    container.innerHTML = html;
    container.scrollTop = container.scrollHeight;
  },

  _initGraph(m, phase) {
    // Find graph data for this mission's workspace
    const wsId = m.company_id;
    const graphData = State.graphs[wsId];
    if (!graphData) return;

    // Filter to only nodes/edges for this mission
    const missionId = m.id || m.mission_id;
    const nodes = graphData.nodes.filter(n => n.mission_id === missionId);
    const nodeIds = new Set(nodes.map(n => n.id));
    const edges = graphData.edges.filter(e => {
      const from = e.from || e.source;
      const to = e.to || e.target;
      return nodeIds.has(from) && nodeIds.has(to);
    });

    // Add line_count from components
    const allComps = State.components[wsId] || [];
    nodes.forEach(n => {
      const comp = allComps.find(c => c.component_id === n.id);
      if (comp) n.line_count = comp.line_count || 0;
    });

    setTimeout(() => {
      const canvas = document.getElementById('graph-canvas');
      if (!canvas) return;
      const container = document.getElementById('mission-graph');
      if (container) {
        // Make canvas fill its container
        canvas.style.width = '100%';
        canvas.style.height = '100%';
      }
      GraphRenderer.init(canvas, nodes, edges, phase);

      // Handle resize
      if (container) {
        this._resizeObserver = new ResizeObserver(() => {
          GraphRenderer._resize();
          GraphRenderer._layout();
        });
        this._resizeObserver.observe(container);
      }
    }, 50);
  },

  _esc(str) {
    const d = document.createElement('div');
    d.textContent = str || '';
    return d.innerHTML;
  },
});
