# Repo Understanding

This is my own code-reading document for the current `saltdesktop` repo.

## What This Repo Is

Salt Desktop is being built in two layers:

- This repo is the backend/runtime plus a temporary browser-based proving ground.
- The long-term product is a native Swift macOS app that will consume the same APIs, event streams, and interaction patterns.

The repo is not just a CRUD backend. It is a local multi-agent control plane with:

- planning chat
- plan generation
- mission/task orchestration
- component and graph modeling
- build dispatch through Claude Code CLI
- deployment/service records
- pipeline generation and execution
- real-time event streaming
- connector/credential awareness

The `webui-v2/` app is explicitly a test harness for future Swift UX, not the final product.

## Core Object Model

The backend revolves around these entities:

- Workspace: exposed by the API, backed by `companies`
- Mission: one buildable agent/app goal with planning/build/deploy lifecycle
- Task: queue item created from approved mission items
- Component: logical software building block in a mission graph
- Connection: edge between components
- Service: deployed/runnable artifact for a mission
- Service run: execution record for a service
- Connector: metadata about external service connections
- Signal: low-level activity/event telemetry
- Event: durable product-level event log
- Chat message: planning conversation history

The main lifecycle is:

1. Create workspace
2. Create mission in `planning`
3. Chat with the planner
4. Generate preview graph
5. Generate full plan
6. Approve mission
7. Create components + enqueue tasks
8. Build tasks into code
9. Mark mission complete
10. Promote/deploy into a service

## Backend Architecture

### 1. Shared foundations

`[runtime/jb_common.py](/Users/jimopenclaw/saltdesktop/runtime/jb_common.py)` defines:

- repo-relative `BASE_DIR`, `DATA_DIR`, `LOG_DIR`
- UTC timestamp helpers
- `JsonStore`, which survives as backward-compat scaffolding

`[runtime/jb_database.py](/Users/jimopenclaw/saltdesktop/runtime/jb_database.py)` is now the primary persistence layer:

- SQLite with WAL mode
- per-connection init and schema creation
- tables for companies, missions, tasks, components, connections, services, runs, connectors, signals, events, and chat messages
- helpers for signals, events, and planning chat history

Important transition note:

- The system is mid-migration from JSON files to SQLite.
- Most real CRUD now goes through SQLite.
- Some compatibility paths and a few health/debug helpers still read legacy JSON files.

### 2. CRUD/runtime modules

`[runtime/jb_companies.py](/Users/jimopenclaw/saltdesktop/runtime/jb_companies.py)`

- creates workspaces/companies
- manages focused mission
- creates per-company and per-mission context markdown files under `data/companies/...`

`[runtime/jb_missions.py](/Users/jimopenclaw/saltdesktop/runtime/jb_missions.py)`

- mission CRUD and normalization
- planning items
- mission status transitions
- approval flow that turns plan items into queue tasks and component records
- deployment markers

`[runtime/jb_queue.py](/Users/jimopenclaw/saltdesktop/runtime/jb_queue.py)`

- queue CRUD
- statuses from `pending` through `complete`/`failed`
- retry handling
- optional subagent/external-process tracking fields

`[runtime/jb_components.py](/Users/jimopenclaw/saltdesktop/runtime/jb_components.py)`

- component registry
- connection registry
- graph derivation
- contract metadata and lifecycle helpers

`[runtime/jb_services.py](/Users/jimopenclaw/saltdesktop/runtime/jb_services.py)`

- service records
- run history
- lifecycle transitions like start/pause/resume/stop
- simple port allocation

### 3. Planning and build path

`[runtime/jb_plan_generate.py](/Users/jimopenclaw/saltdesktop/runtime/jb_plan_generate.py)` is the planning brain:

- reads chat history from SQLite
- builds generation prompts
- asks OpenAI or Anthropic directly
- supports lightweight preview graph generation
- stores previous drafts for regeneration diffing
- writes generated items/components/connections back onto the mission

This module is a major bridge between “chatting about what to build” and “creating an executable graph.”

`[runtime/jb_builder.py](/Users/jimopenclaw/saltdesktop/runtime/jb_builder.py)` is the code builder:

- spawns `claude` CLI in a component directory
- passes a focused build prompt plus a system prompt
- expects `main.py`, `contract.py`, and `test_main.py`
- marks task/component states based on output files

The builder writes generated component code under top-level `components/<slug>/`.

### 4. Orchestration and compaction

`[runtime/jb_orchestrator.py](/Users/jimopenclaw/saltdesktop/runtime/jb_orchestrator.py)` runs the five-phase loop:

- retry failed tasks
- dispatch pending tasks
- reconcile stuck running/dispatched tasks
- check mission lifecycle
- compact mission context after newly completed work

`[runtime/jb_compaction.py](/Users/jimopenclaw/saltdesktop/runtime/jb_compaction.py)` updates mission context and lifecycle state after work finishes.

### 5. Pipelines and deployment path

`[runtime/jb_pipeline.py](/Users/jimopenclaw/saltdesktop/runtime/jb_pipeline.py)` turns a mission graph into executable Python:

- topological sort
- contract validation
- generated `pipeline.py` + `config.json`
- in-process execution with `summary_chain`
- optional service run tracking

This is the backend’s strongest “graph becomes code” implementation.

### 6. Real-time and UX translation

`[runtime/jb_event_bus.py](/Users/jimopenclaw/saltdesktop/runtime/jb_event_bus.py)`

- in-memory pub/sub for SSE

`[runtime/jb_events.py](/Users/jimopenclaw/saltdesktop/runtime/jb_events.py)`

- append-only JSONL event log

`[runtime/jb_labels.py](/Users/jimopenclaw/saltdesktop/runtime/jb_labels.py)`

- user-facing labels/icons for mission, service, component, and worker states

`[runtime/jb_ceo_translator.py](/Users/jimopenclaw/saltdesktop/runtime/jb_ceo_translator.py)`

- converts low-level signals and task state into executive-friendly UI activity text

`[runtime/jb_swarm.py](/Users/jimopenclaw/saltdesktop/runtime/jb_swarm.py)`

- read-only join layer for “who is building what right now”

### 7. Commands and credentials

`[runtime/jb_commands.py](/Users/jimopenclaw/saltdesktop/runtime/jb_commands.py)`

- handles slash commands like `/mission generate`, `/mission approve`, `/status`

`[runtime/jb_credentials.py](/Users/jimopenclaw/saltdesktop/runtime/jb_credentials.py)`

- reads credential JSON files from `~/.missionos/credentials`
- exposes service catalog metadata
- can refresh Google OAuth tokens and write the refreshed token back

This matches the intended split where the native app owns connection UX and this backend consumes the resulting credentials.

## API Surface

`[runtime/jb_api.py](/Users/jimopenclaw/saltdesktop/runtime/jb_api.py)` is the single large FastAPI surface.

Broad endpoint families:

- health, settings, reference, live, usage
- workspaces and missions
- plan generation and preview
- approval/build/cancel/retry
- chat and chat history
- memory/context inspection
- components, graphs, pipelines
- services and runs
- dashboard/swarm helper endpoints
- SSE event streaming
- connectors
- static web app serving for `/` and `/v2`

Important behavioral split:

- planning chat calls LLMs directly from the API layer
- build execution goes through Claude Code CLI
- SSE is the real-time bridge between backend mutations and frontend state

## Frontend Test Web App

The browser app lives in `[webui-v2/app.js](/Users/jimopenclaw/saltdesktop/webui-v2/app.js)` plus per-view files.

It is a plain JS single-page app with:

- hash router
- global in-memory state store
- direct fetch client
- SSE subscription
- sidebar workspace/agent navigation
- canvas graph renderer

Main views:

- `[webui-v2/views/dashboard.js](/Users/jimopenclaw/saltdesktop/webui-v2/views/dashboard.js)`: executive overview of running/building/planning work
- `[webui-v2/views/company.js](/Users/jimopenclaw/saltdesktop/webui-v2/views/company.js)`: workspace-level grouping of agents
- `[webui-v2/views/mission.js](/Users/jimopenclaw/saltdesktop/webui-v2/views/mission.js)`: the most important screen; adapts across planning, building, complete, and live phases
- `[webui-v2/views/connectors.js](/Users/jimopenclaw/saltdesktop/webui-v2/views/connectors.js)`: connector inventory/status UI
- `[webui-v2/views/library.js](/Users/jimopenclaw/saltdesktop/webui-v2/views/library.js)`: built component inventory
- `[webui-v2/views/settings.js](/Users/jimopenclaw/saltdesktop/webui-v2/views/settings.js)`: mock mode and planning model controls

The mission screen is the clearest expression of the future product:

- planning = chat + live draft graph
- lock-it-in = full structured generation
- building = graph + swarm/progress
- complete = ready to deploy
- live = service health + controls

## Prototype / Example Vertical Apps

This repo also contains vertical example logic outside the core Salt runtime:

- CryptoDash: fetch/history/render/alerts runner
- Email digest bot: Gmail fetch, summarization, Slack delivery

These modules look like proof-of-concept agent outputs or sample reference implementations rather than the core control plane itself.

## Persistence and Filesystem Layout

Key directories:

- `data/`: SQLite DB plus compatibility JSON files and workspace context files
- `logs/`: JSONL event logs and orchestrator logs
- `components/`: generated component code
- `pipelines/`: generated pipeline code and last-run artifacts
- `memory/`: memory/state scratch area
- `webui-v2/`: temporary web UI
- `tests/`: broad test suite

One architectural wrinkle I noticed:

- generated components are built under top-level `components/<slug>/`
- but pipeline scaffold/validation helpers also reference `data/companies/<workspace>/components/<slug>/`

That means there are currently two component-directory conventions in the codebase. It is worth resolving before packaging everything into a contained macOS app.

## Test Suite Shape

The tests are broad and mostly repo-internal rather than browser-level.

They cover:

- companies, missions, queue, services, components
- plan generation and regeneration diffing
- pipeline generation/execution
- orchestrator and retry behavior
- lifecycle transitions
- labels and CEO translation
- swarm view projection
- credentials
- end-to-end mission lifecycle
- API flow against a live local server

Useful anchor files:

- `[tests/conftest.py](/Users/jimopenclaw/saltdesktop/tests/conftest.py)`: temp DB/store isolation pattern
- `[tests/test_end_to_end.py](/Users/jimopenclaw/saltdesktop/tests/test_end_to_end.py)`: full mission lifecycle
- `[tests/test_pipeline.py](/Users/jimopenclaw/saltdesktop/tests/test_pipeline.py)`: graph-to-code behavior
- `[tests/test_plan_generate.py](/Users/jimopenclaw/saltdesktop/tests/test_plan_generate.py)`: regeneration/idempotence model
- `[tests/test_api_flow.py](/Users/jimopenclaw/saltdesktop/tests/test_api_flow.py)`: live API expectations

## What I Think The Repo Is Optimizing For

The system is trying to prove that non-technical users can:

- describe an agent in normal language
- see the architecture emerge visually
- approve a concrete plan
- watch multi-agent building activity
- deploy the result as a durable service

The repo is already strong on:

- local-first architecture
- concrete mission/task/component/service model
- graph-based planning representation
- direct API surface for the eventual native app
- test coverage around core runtime behavior

The repo is still evolving in:

- consistency between legacy JSON compatibility and SQLite-first design
- consistency of component filesystem conventions
- separation between core Salt control-plane code and prototype/sample verticals
- slimming down the very large `jb_api.py` into clearer route domains over time

## Bottom Line

This codebase is not “just a backend for a web app.”

It is an early local operating system for user-created multi-agent software:

- the runtime models the work
- the planner turns chat into architecture
- the builder turns architecture into code
- the pipeline layer turns graphs into execution
- the web app proves the flows and visuals
- the future Swift app will replace the browser shell, not the core ideas
