# Documentation Files Summary

**Path:** `docs/`
**Purpose:** Design documents, specs, analysis notes, and planning artifacts for Salt Desktop.

## Files

### ACTIVITY_LOG.md
Running append-only log of development activity with timestamped entries. Records features completed, bugs fixed, architecture changes, and key numbers (routes, tests).

### SYSTEM_SPEC.md
Complete system specification regenerated after significant architecture changes. Covers all modules, APIs, data models, and conventions.

### V1_TECH_SPEC.md
Technical specification for the V1 release. Details implementation priorities, API endpoint specifications, and frontend integration requirements.

### FRONTEND_SPEC.md
Frontend architecture specification for the web UI. Covers view structure, state management, routing, SSE integration, and graph rendering.

### EVENT_STREAM_SPEC.md
Specification for the SSE event streaming system. Defines event types, payload formats, CEO-mode translation, and frontend consumption patterns.

### SALTAGENT_PRD.md
Product requirements document for the Salt Agent system. Covers the autonomous agent architecture being built separately.

### NEXT_SESSION.md
Notes for the next development session -- outstanding tasks, blocked items, and priorities.

### RECOVERED_SESSION_NOTES.md
Recovered notes from a previous development session with context about in-progress work.

### REPO_UNDERSTANDING.md
Analysis of the repository structure, module relationships, and data flow patterns.

### CLAUDE_CODE_INTERNALS.md
Analysis of Claude Code internal architecture -- how the CLI works, tool execution, session management.

### CLAWTEAM_ANALYSIS.md
Analysis of the ClawTeam/OpenClaw platform and its relationship to JBCP.

### KODE_AGENT_SDK_ANALYSIS.md
Analysis of the Kode Agent SDK for potential integration.

### LEARN_CLAUDE_CODE_ANALYSIS.md
Analysis of Claude Code's learning and context mechanisms.

### prd_analysis/ (directory)
Per-section analysis of the Salt Desktop PRD by 8 parallel agents:
- `00_consolidated_tasks.md` -- Consolidated task list from all sections
- `01_mission_lifecycle.md` -- Mission lifecycle analysis
- `02_home_dashboard.md` -- Home dashboard analysis
- `03_my_ai_swarm.md` -- My AI swarm view analysis
- `04_component_graph.md` -- Component graph visualization analysis
- `05_chat_ux.md` -- Chat UX analysis
- `06_component_sharing.md` -- Component sharing analysis
- `07_deployment_model.md` -- Deployment model analysis
- `08_company_view_naming.md` -- Company view and naming analysis
- `09_ceo_dev_mode.md` -- CEO vs developer mode analysis
