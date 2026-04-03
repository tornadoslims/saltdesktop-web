# Salt Desktop -- Codebase Documentation

File-by-file documentation for every source file in the project.

## Runtime (Python Backend)

### Core Infrastructure

| File | Purpose |
|------|---------|
| [jb_common.md](runtime/jb_common.md) | Shared utilities: paths, timestamps, JsonStore |
| [jb_database.md](runtime/jb_database.md) | SQLite data layer: 11 tables, WAL mode, thread-safe |
| [jb_api.md](runtime/jb_api.md) | FastAPI server on port 8718 -- ~40 endpoints |
| [init.md](runtime/init.md) | Package init file |

### Entity Modules (CRUD)

| File | Purpose |
|------|---------|
| [jb_companies.md](runtime/jb_companies.md) | Company/workspace CRUD, focused mission, context paths |
| [jb_missions.md](runtime/jb_missions.md) | Mission CRUD, items, lifecycle (planning -> active -> complete -> deployed) |
| [jb_queue.md](runtime/jb_queue.md) | Task queue: pending -> dispatched -> running -> complete/failed |
| [jb_components.md](runtime/jb_components.md) | Component registry, typed contracts, connections, graph generation |
| [jb_services.md](runtime/jb_services.md) | Service registry: lifecycle, run tracking, port allocation |
| [jb_company_mapping.md](runtime/jb_company_mapping.md) | External ID to company mapping |
| [jb_credentials.md](runtime/jb_credentials.md) | Credential store for 20 external services |

### Orchestration & Building

| File | Purpose |
|------|---------|
| [jb_orchestrator.md](runtime/jb_orchestrator.md) | 5-phase loop: retry -> dispatch -> reconcile -> lifecycle -> compact |
| [jb_builder.md](runtime/jb_builder.md) | Claude Code CLI builder: spawns `claude --print` to build components |
| [jb_plan_generate.md](runtime/jb_plan_generate.md) | Direct LLM calls to generate structured plans from chat |
| [jb_pipeline.md](runtime/jb_pipeline.md) | Pipeline generator + runner: topological sort, code gen, in-process execution |
| [jb_compaction.md](runtime/jb_compaction.md) | Updates mission_context.md after task completion, auto-complete lifecycle |
| [jb_commands.md](runtime/jb_commands.md) | Slash command handling (/mission, /status, /contextmem, /jbdebug) |

### Events & Real-time

| File | Purpose |
|------|---------|
| [jb_event_bus.md](runtime/jb_event_bus.md) | In-memory pub/sub event bus for SSE streaming |
| [jb_events.md](runtime/jb_events.md) | Append-only JSONL event log |

### Display & Translation

| File | Purpose |
|------|---------|
| [jb_labels.md](runtime/jb_labels.md) | Human-readable status labels, icons, role names |
| [jb_ceo_translator.md](runtime/jb_ceo_translator.md) | Translates raw signals to CEO-friendly activity text |
| [jb_swarm.md](runtime/jb_swarm.md) | Read-only view layer: workers grouped by mission, running services |
| [jb_mock_data.md](runtime/jb_mock_data.md) | Mock data for UI development (2 workspaces, 6 missions, 14 components) |

### CryptoDash (Sample Built Agent)

| File | Purpose |
|------|---------|
| [cryptodash_runner.md](runtime/cryptodash_runner.md) | CLI entry point: fetch -> history -> render -> alerts |
| [cryptodash_fetcher.md](runtime/cryptodash_fetcher.md) | CoinGecko API price fetcher |
| [cryptodash_history.md](runtime/cryptodash_history.md) | Rolling price history store (JSON) |
| [cryptodash_renderer.md](runtime/cryptodash_renderer.md) | Rich terminal dashboard with sparklines |
| [cryptodash_alerts.md](runtime/cryptodash_alerts.md) | Price threshold alerts with cooldown |
| [CRYPTODASH_README.md](runtime/CRYPTODASH_README.md) | CryptoDash documentation |

### Email Digest (Sample Built Agent)

| File | Purpose |
|------|---------|
| [email_digest_runner.md](runtime/email_digest_runner.md) | CLI entry point: fetch -> summarize -> post to Slack |
| [email_digest_gmail.md](runtime/email_digest_gmail.md) | Gmail connector via gog CLI |
| [email_digest_summarizer.md](runtime/email_digest_summarizer.md) | Claude CLI email categorizer/summarizer |
| [email_digest_slack.md](runtime/email_digest_slack.md) | Slack Block Kit formatter and webhook poster |
| [email_digest_state.md](runtime/email_digest_state.md) | Run state persistence (last_run_at, processed_ids) |
| [EMAIL_DIGEST_README.md](runtime/EMAIL_DIGEST_README.md) | Email Digest documentation |

### Other Runtime Files

| File | Purpose |
|------|---------|
| [JB_IMPORTANT_PROMPTS.md](runtime/JB_IMPORTANT_PROMPTS.md) | Transcript of parallel PRD analysis session |

## Web UI (JavaScript Frontend)

| File | Purpose |
|------|---------|
| [index_html.md](webui-v2/index_html.md) | Entry point HTML: sidebar, main content, status bar |
| [app.md](webui-v2/app.md) | Core app: API client, State, Router, Sidebar, SSE, GraphRenderer (1,094 lines) |
| [style.md](webui-v2/style.md) | Full CSS: dark theme, layout, components (1,890 lines) |

### Views

| File | Purpose |
|------|---------|
| [dashboard.md](webui-v2/views/dashboard.md) | Home page: greeting, running services, building progress, companies |
| [company.md](webui-v2/views/company.md) | Company detail: agents, in-progress, completed missions |
| [mission.md](webui-v2/views/mission.md) | Phase-adaptive mission view: planning chat, building graph, deploy |
| [library.md](webui-v2/views/library.md) | Component library: all built components grouped by type |
| [connectors.md](webui-v2/views/connectors.md) | External service connections: 19+ services with status |
| [settings.md](webui-v2/views/settings.md) | Settings: mock mode, planning model, version info |
| [myai.md](webui-v2/views/myai.md) | My AI swarm view (redirects to dashboard) |

## Configuration

| File | Purpose |
|------|---------|
| [requirements.md](config/requirements.md) | Python dependencies: FastAPI, uvicorn, anthropic, openai |
| [gitignore.md](config/gitignore.md) | Git exclusions: database, runtime data, secrets |
| [claude_md.md](config/claude_md.md) | Claude Code instructions: work style, coordination, architecture |

## Documentation

| File | Purpose |
|------|---------|
| [summaries.md](docs/summaries.md) | Summary of all docs: specs, PRD analysis, session notes |
