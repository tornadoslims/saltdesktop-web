# ClawTeam Comprehensive Analysis

**Date**: 2026-03-30
**Version Analyzed**: v0.3.0
**Repository**: https://github.com/HKUDS/ClawTeam
**License**: MIT

---

## 1. What ClawTeam Is

ClawTeam is a **framework-agnostic multi-agent coordination CLI** that enables AI coding agents to self-organize into collaborative teams. Unlike other multi-agent frameworks where humans write orchestration code, ClawTeam is designed to be **used by the AI agents themselves** -- a leader agent spawns workers, assigns tasks, and coordinates via CLI commands.

### Vision

The tagline is "Agent Swarm Intelligence" -- moving from solo AI agents to coordinated swarms. The key insight is that instead of building complex orchestration infrastructure (Docker, Redis, YAML configs), ClawTeam uses just a filesystem and tmux. Agents coordinate through simple CLI commands (`clawteam spawn`, `clawteam task create`, `clawteam inbox send`).

### How It Fits in the Ecosystem

- **Not a model framework** -- it does not wrap LLM APIs or define agent prompts.
- **Not a workflow engine** -- it does not define DAGs or pipelines.
- **It is a coordination layer** -- it provides the shared infrastructure (task boards, messaging, workspace isolation, monitoring) that any CLI agent needs to work in a team.
- Works with Claude Code, Codex, Gemini CLI, Kimi CLI, nanobot, OpenClaw, Cursor, and any custom CLI agent.

### Proven Use Cases

1. **Autonomous ML Research**: 8 agents across 8 H100 GPUs running 2430+ experiments autonomously, achieving a 6.4% val_bpb improvement.
2. **Agentic Software Engineering**: Full-stack app development with 5 parallel agents (architect, backend, frontend, tester), each in its own git worktree.
3. **AI Hedge Fund**: 7-agent investment analysis team launched from a single TOML template.

---

## 2. Architecture

### High-Level Data Flow

```
Human Goal --> Leader Agent --> Team Creation --> Task Assignment --> Worker Spawn
           --> Workers Execute (isolated worktrees) --> Inbox Communication
           --> Task Completion --> Dependency Auto-Unblock --> Merge --> Done
```

### Core Architecture Layers

```
CLI Layer (commands.py)
    |
    v
Team Layer (team/)
    - TeamManager: team CRUD, member management
    - MailboxManager: inter-agent messaging
    - TaskStore: shared kanban board
    - PlanManager: plan approval workflow
    - LifecycleManager: shutdown/idle protocol
    - CostStore: token/cost tracking per agent
    |
    v
Transport Layer (transport/)
    - Transport ABC: deliver/fetch/count/list_recipients
    - FileTransport: filesystem-based (default)
    - P2PTransport: ZeroMQ PUSH/PULL with file fallback
    |
    v
Spawn Layer (spawn/)
    - SpawnBackend ABC: spawn/list_running
    - TmuxBackend: tmux windows per agent
    - SubprocessBackend: fire-and-forget processes
    - WshBackend: WaveTerm/TideTerm terminal blocks
    - NativeCliAdapter: agent-specific command preparation
    - Registry: process liveness tracking
    |
    v
Workspace Layer (workspace/)
    - WorkspaceManager: git worktree isolation
    - Context: cross-agent awareness, file overlap detection
    - Conflicts: detect and auto-notify file overlaps
    |
    v
Harness Layer (harness/)
    - HarnessOrchestrator: phase state machine
    - HarnessConductor: auto-drives through phases
    - PhaseRunner: phase transitions with gates
    - Contracts: sprint contracts with success criteria
    - Roles: planner, executor, evaluator
    |
    v
Event Layer (events/)
    - EventBus: pub-sub for lifecycle events
    - 18+ event types: worker spawn/exit, task create/update, phase transitions
    |
    v
Plugin Layer (plugins/)
    - HarnessPlugin ABC: on_register, contribute_gates, contribute_prompts
    - PluginManager: discovery from entry_points, config, local dirs
```

### Data Persistence

All state is stored as JSON files under `~/.clawteam/`:

```
~/.clawteam/
  config.json              -- Global config (profiles, presets, hooks, plugins)
  teams/{team}/
    config.json            -- Team config (members, leader, budget)
    inboxes/{agent}/       -- Message files (msg-{ts}-{uid}.json)
    events/                -- Event log (persistent, never consumed)
    peers/                 -- P2P peer discovery (agent.json)
    spawn_registry.json    -- Process liveness info
    runtime_state.json     -- Runtime routing state
  tasks/{team}/
    task-{id}.json         -- Individual task files
    .tasks.lock            -- Advisory file lock
  costs/{team}/
    cost-{ts}-{id}.json    -- Cost events
    summary.json           -- Cached cost summary
  workspaces/{team}/
    workspace-registry.json -- Worktree mappings
  sessions/{team}/
    {agent}.json           -- Session state for resume
  plans/{team}/
    {agent}-{planId}.md    -- Plan documents
  harness/{team}/{id}/
    state.json             -- Harness phase state
```

---

## 3. Key Concepts

### Teams
A named group of agents with one leader and zero or more workers. Created with `clawteam team spawn-team`. The leader's identity is tracked via `lead_agent_id`. Multi-user support: members have both a `name` and an optional `user` field, enabling `(user, name)` composite uniqueness.

### Roles
Open strings (not enums) so plugins can define custom roles. Built-in roles:
- **planner**: produces specifications during discuss/plan phases
- **executor**: implements assigned sprint contracts
- **evaluator**: tests implementations against success criteria
- **leader**: coordinates the team

### Tasks
Shared kanban board with four statuses: `pending`, `in_progress`, `completed`, `blocked`. Tasks support:
- **Dependencies**: `blocked_by` chains with automatic unblocking on completion
- **Priority**: low, medium, high, urgent
- **Locking**: when a task moves to `in_progress`, it is locked by the caller agent; stale locks from dead agents are auto-released
- **Duration tracking**: start/complete timestamps with computed duration
- **Cycle detection**: dependency graph is validated for cycles before saving

### Board
Multi-view monitoring dashboard:
- `board show` -- terminal kanban board (Rich)
- `board live` -- auto-refreshing dashboard with conflict auto-notification
- `board attach` -- tiled tmux view of all agent panes
- `board serve` -- Web UI with SSE real-time updates (stdlib HTTP server, no FastAPI)
- `board gource` -- git activity visualization

### Workspace
Git worktree-based isolation. Each spawned agent gets:
- A dedicated git branch: `clawteam/{team}/{agent}`
- A dedicated worktree directory under `~/.clawteam/workspaces/{team}/{agent}`
- OpenClaw-specific workspace slimming (removes unnecessary files, symlinks node_modules/.venv)
- Checkpoint (commit all), merge, and cleanup operations

### Harness
A phase-based orchestration layer with 5 default phases:
```
discuss --> plan --> execute --> verify --> ship
```
Each phase can have:
- **Gates**: conditions that must be met before advancing (artifact required, all tasks complete, human approval)
- **Role affinity**: which agent role works in each phase
- **Sprint contracts**: units of work with testable success criteria

### Spawn
Process management for launching agent processes:
- **tmux**: interactive windows with pane monitoring, workspace trust auto-confirmation
- **subprocess**: fire-and-forget background processes
- **wsh**: WaveTerm/TideTerm terminal blocks
- Spawn registry tracks PIDs and tmux targets for liveness checking
- Lifecycle hooks: `pane-exited` and `pane-died` tmux hooks fire `clawteam lifecycle on-exit/on-crash`

### Store
Abstract task store with file-based implementation. The `BaseTaskStore` ABC defines create/get/update/list_tasks/release_stale_locks. `FileTaskStore` uses per-task JSON files with advisory file locking for concurrency control.

---

## 4. How Agents Work

### Agent Types Supported

| Agent | Command | Special Handling |
|-------|---------|-----------------|
| Claude Code | `claude` | `--dangerously-skip-permissions`, trust prompt auto-confirm, buffer-based prompt injection |
| Codex | `codex` | `--dangerously-bypass-approvals-and-sandbox`, update prompt dismissal |
| Gemini | `gemini` | `--yolo` for skip-permissions, trust folder confirmation |
| Kimi | `kimi` | `--yolo`, `-w` workspace, `--print -p` prompt |
| nanobot | `nanobot` | Normalized to `nanobot agent`, `-w` workspace, `-m` message |
| OpenClaw | `openclaw` | `--local`, `--session-id`, `--message` |
| Qwen | `qwen` | `--yolo` |
| OpenCode | `opencode` | `--yolo` |
| pi | `pi` | Minimal flags |
| Custom | any CLI | Generic `-p` prompt flag |

### How Agents Are Spawned

1. **Team creation**: `clawteam team spawn-team myteam -n leader` creates the team, registers leader as member, creates inbox directory
2. **Workspace creation**: If in a git repo and workspace mode is enabled, `WorkspaceManager.create_workspace()` creates a dedicated git worktree with branch `clawteam/{team}/{agent}`
3. **Command preparation**: `NativeCliAdapter.prepare_command()` normalizes the command with agent-specific flags (skip-permissions, workspace path, prompt injection method)
4. **Process launch**: The spawn backend (tmux/subprocess/wsh) launches the process with identity env vars (`CLAWTEAM_AGENT_ID`, `CLAWTEAM_AGENT_NAME`, `CLAWTEAM_TEAM_NAME`, etc.)
5. **Trust confirmation**: For tmux, auto-confirms workspace trust dialogs and skip-permissions dialogs
6. **Prompt injection**: The coordination prompt is injected via `tmux load-buffer/paste-buffer` (avoids shell escaping issues) or CLI flags
7. **Registry**: Agent is registered in `spawn_registry.json` with backend type, tmux target, PID, spawn time
8. **Lifecycle hooks**: tmux `pane-exited`/`pane-died` hooks call `clawteam lifecycle on-exit/on-crash`

### How Agents Communicate

Agents communicate through **mailbox-based messaging**:

```
Agent A --> clawteam inbox send myteam agentB "message"
         --> MailboxManager.send()
         --> Transport.deliver("agentB", json_bytes)
         --> File written: teams/myteam/inboxes/agentB/msg-{ts}-{uid}.json

Agent B --> clawteam inbox receive myteam --agent agentB
         --> MailboxManager.receive()
         --> Transport.fetch("agentB", consume=True)
         --> File read + deleted (claimed message pattern)
```

Messages are typed (`TeamMessage` Pydantic model) with types including: message, broadcast, join_request/approved/rejected, plan_approval_request/approved/rejected, shutdown_request/approved/rejected, idle.

### Coordination Prompt

When an agent is spawned, it receives an auto-generated prompt (from `spawn/prompt.py`) that teaches it how to:
- Check its tasks: `clawteam task list {team} --owner {name}`
- Update status: `clawteam task update {team} {id} --status in_progress/completed`
- Message the leader: `clawteam inbox send {team} {leader} "message"`
- Report idle: `clawteam lifecycle idle {team}`
- Report costs: `clawteam cost report {team} --input-tokens N --output-tokens N`
- Save session: `clawteam session save {team} --session-id {id}`
- Worker loop: keep checking tasks/inbox after initial task, don't exit

### Runtime Message Injection

For tmux-based agents, ClawTeam supports **live runtime injection** -- pushing messages directly into the agent's tmux pane while it's running. The `RuntimeRouter` normalizes inbox messages into `RuntimeEnvelope` objects, the `DefaultRoutingPolicy` applies throttling (30s same-pair), and `TmuxBackend.inject_runtime_message()` pastes the notification via tmux buffers.

---

## 5. The Team Model

### Team Structure

```python
TeamConfig:
    name: str                    # e.g. "webapp-team"
    description: str
    lead_agent_id: str           # UUID of leader
    members: list[TeamMember]    # All members including leader
    budget_cents: float          # Cost budget

TeamMember:
    name: str                    # Logical name (e.g. "backend-dev")
    user: str                    # Multi-user support (e.g. "alice")
    agent_id: str                # UUID
    agent_type: str              # e.g. "backend-developer"
    joined_at: str               # ISO timestamp
```

### Templates (TOML)

Teams can be launched from TOML template files that define the entire team structure:

```toml
[template]
name = "software-dev"
description = "Multi-agent full-stack development"
command = ["claude"]
backend = "tmux"

[template.leader]
name = "tech-lead"
type = "tech-lead"
task = "You are the Technical Lead... {goal}"

[[template.agents]]
name = "backend-dev"
type = "backend-developer"
task = "You are a Backend Developer... {goal}"

[[template.agents]]
name = "frontend-dev"
type = "frontend-developer"
task = "You are a Frontend Developer... {goal}"

[[template.tasks]]
subject = "Design and implement backend API endpoints"
owner = "backend-dev"
```

Built-in templates: `software-dev`, `hedge-fund`, `code-review`, `research-paper`, `strategy-room`, `harness-default`.

Variable substitution: `{goal}`, `{team_name}`, `{agent_name}` are replaced at launch time.

### Profiles and Presets

**Presets** are provider templates (e.g., `moonshot-cn`, `openrouter`, `deepseek`) that define how to connect to different AI providers. They contain client overrides for different CLI agents.

**Profiles** are the final runtime objects used by `spawn`. Generated from presets via `clawteam preset generate-profile moonshot-cn claude --name claude-kimi`.

Built-in presets cover: Anthropic, OpenAI, Google AI Studio, Moonshot, DeepSeek, Zhipu, Bailian, MiniMax, OpenRouter, Gemini Vertex.

---

## 6. Transport

### File-Based Transport (Default)

- Each message is a JSON file: `teams/{team}/inboxes/{agent}/msg-{ts}-{uid}.json`
- Atomic writes: write to `.tmp-{uid}.json`, then `os.replace()` to final name
- Claimed message pattern: `msg-*.json` renamed to `msg-*.consumed` during processing, then deleted on ack or moved to `dead_letters/` on quarantine
- Advisory file locking (`fcntl.flock` on Unix, `msvcrt.locking` on Windows) prevents concurrent reads
- Messages sorted by filename (timestamp-ordered)

### ZeroMQ P2P Transport (Optional)

- Requires `pip install clawteam[p2p]` (pyzmq)
- Each agent binds a ZMQ PULL socket on a random port
- Peer discovery via shared filesystem: `teams/{team}/peers/{agent}.json` containing `{host, port, pid, heartbeatAtMs, leaseDurationMs, leaseExpiresAtMs}`
- Background heartbeat thread writes peer file every 1 second
- Lease-based liveness: remote peers checked via lease freshness, local peers checked via PID
- **Offline fallback**: if ZMQ delivery fails (peer unreachable), falls back to FileTransport automatically
- On receive: drains ZMQ PULL socket first (non-blocking), then checks file fallback for remaining messages

### Transport Selection

```
CLAWTEAM_TRANSPORT env var > config file transport field > default "file"
```

Custom transports can be registered via `register_transport(name, cls)`.

---

## 7. Board

The board provides multiple monitoring views:

### Terminal Board (`board show`)
Rich-rendered kanban with:
- Team header (leader, members, creation date, cost)
- Members table (name, type, joined, inbox count)
- 4-column kanban: PENDING | IN PROGRESS | COMPLETED | BLOCKED
- Conflict warnings panel (file overlap detection between worktrees)

### Live Dashboard (`board live`)
Auto-refreshing version of the terminal board with periodic conflict auto-notification to agents.

### Tiled View (`board attach`)
Merges all tmux windows into one tiled pane layout, then attaches to the session. Allows watching all agents working simultaneously.

### Web UI (`board serve`)
HTTP server (stdlib only, no FastAPI) with:
- SSE (Server-Sent Events) for real-time updates
- Dark theme kanban board
- Multi-team overview
- Message history with member-aware aliases
- GitHub README proxy for template discovery
- Static file serving from `board/static/`

### Gource Visualization (`board gource`)
Generates Gource activity visualization from cross-branch git logs.

---

## 8. MCP Integration

ClawTeam provides a FastMCP server (`clawteam-mcp` entry point) with 26 tools:

**Team Tools**: `team_list`, `team_get`, `team_members_list`, `team_create`, `team_member_add`

**Task Tools**: `task_list`, `task_get`, `task_stats`, `task_create`, `task_update`

**Mailbox Tools**: `mailbox_send`, `mailbox_broadcast`, `mailbox_receive`, `mailbox_peek`, `mailbox_peek_count`

**Plan Tools**: `plan_submit`, `plan_get`, `plan_approve`, `plan_reject`

**Board Tools**: `board_overview`, `board_team`

**Cost Tools**: `cost_summary`

**Workspace Tools**: `workspace_agent_diff`, `workspace_file_owners`, `workspace_cross_branch_log`, `workspace_agent_summary`

The MCP server enables any MCP-compatible client (like Claude Desktop) to interact with ClawTeam teams, tasks, and messaging programmatically.

---

## 9. CLI Commands

The CLI is built with Typer and has these command groups:

| Group | Commands |
|-------|----------|
| `team` | `spawn-team`, `discover`, `status`, `request-join`, `approve-join`, `cleanup`, `snapshot`, `restore` |
| `inbox` | `send`, `broadcast`, `receive`, `peek`, `watch` |
| `task` | `create`, `get`, `update`, `list`, `wait` |
| `board` | `show`, `overview`, `live`, `attach`, `serve`, `gource` |
| `spawn` | `[backend] [command]` (positional: tmux/subprocess, claude/codex/etc.) |
| `launch` | Launch from TOML template |
| `lifecycle` | `request-shutdown`, `approve-shutdown`, `idle`, `on-exit`, `on-crash` |
| `plan` | `submit`, `approve`, `reject` |
| `context` | `diff`, `files`, `conflicts`, `log`, `inject` |
| `workspace` | `create`, `checkpoint`, `merge`, `cleanup`, `list` |
| `config` | `show`, `set`, `get`, `health` |
| `profile` | `list`, `show`, `set`, `test`, `wizard`, `doctor` |
| `preset` | `list`, `show`, `generate-profile`, `bootstrap` |
| `cost` | `report`, `summary` |
| `session` | `save`, `load`, `list`, `clear` |
| `identity` | `show`, `set` |
| `plugin` | `list`, `info`, `load` |
| `harness` | `start`, `status`, `advance`, `approve`, `conduct` |

All commands support `--json` for machine-readable output.

---

## 10. How Salt Desktop Could Use ClawTeam

### The BUILD Phase Integration

Salt Desktop needs to orchestrate multiple coding agents working in parallel during the BUILD phase. ClawTeam is purpose-built for exactly this. Here is how the integration could work:

### Architecture Overview

```
Salt Desktop (Swift macOS app)
    |
    v
JBCP Runtime (Python backend, port 8718)
    |
    v
ClawTeam (Python library, used as dependency)
    |
    v
Agent Processes (tmux windows: Claude Code, Codex, etc.)
```

### Integration Points

#### 1. Team Creation from JBCP Components

When JBCP decomposes a mission into components, each component maps to a ClawTeam task with dependency chains:

```python
from clawteam.team.manager import TeamManager
from clawteam.store.file import FileTaskStore

# Create team from JBCP mission
team = TeamManager.create_team(
    name=f"mission-{mission_id}",
    leader_name="orchestrator",
    leader_id=uuid4().hex[:12],
    description=mission_description,
)

# Create tasks from JBCP components
store = FileTaskStore(team.name)
for component in components:
    store.create(
        subject=component.name,
        description=component.description,
        owner="",  # assigned when agent spawns
        blocked_by=[dep_task_id for dep in component.dependencies],
    )
```

#### 2. Agent Spawning for Parallel Execution

JBCP can use ClawTeam's spawn infrastructure to launch multiple agents:

```python
from clawteam.spawn import get_backend
from clawteam.spawn.prompt import build_agent_prompt
from clawteam.workspace.manager import WorkspaceManager

backend = get_backend("tmux")
ws_mgr = WorkspaceManager(repo_path=workspace_path)

for component in parallel_components:
    # Create isolated workspace
    ws = ws_mgr.create_workspace(
        team_name=team.name,
        agent_name=component.name,
        agent_id=uuid4().hex[:12],
    )
    
    # Spawn agent in isolated worktree
    backend.spawn(
        command=["claude"],
        agent_name=component.name,
        agent_id=ws.agent_id,
        agent_type="builder",
        team_name=team.name,
        prompt=build_prompt_for_component(component),
        cwd=ws.worktree_path,
        skip_permissions=True,
    )
```

#### 3. Progress Monitoring via Board/Events

Salt Desktop's frontend can monitor build progress through:

- **ClawTeam Board API**: `BoardCollector.collect_team()` returns full team state as JSON
- **Event Bus**: Subscribe to `TaskCompleted`, `AgentIdle`, `WorkerExit` events for real-time updates
- **Task Store**: Poll `TaskStore.list_tasks()` for status changes
- **Workspace Context**: `agent_diff()` and `file_owners()` for git-level progress

#### 4. The Harness for Structured Builds

ClawTeam's harness layer maps perfectly to JBCP's mission phases:

| JBCP Phase | ClawTeam Phase | What Happens |
|------------|---------------|--------------|
| Planning | discuss + plan | Planner agent produces spec.md and sprint contracts |
| Building | execute | Multiple executor agents work on components in parallel |
| Testing | verify | Evaluator agent tests against success criteria |
| Deploying | ship | (Custom gate/phase for deployment) |

The `HarnessConductor` can auto-drive through these phases with automatic agent spawning and health monitoring.

#### 5. Cross-Agent Context Awareness

ClawTeam's context layer (`workspace/context.py`) provides exactly what parallel builders need:
- **File overlap warnings**: Detects when multiple agents modify the same file
- **Cross-branch log**: Unified commit history across all agent worktrees
- **Context injection**: Automatically injects relevant teammate activity into each agent's prompt
- **Conflict auto-notification**: During `board live`, automatically alerts agents about overlaps

#### 6. Communication Between JBCP and ClawTeam

Two options:

**Option A: Library Integration** -- Import ClawTeam modules directly in JBCP:
```python
# In JBCP orchestrator
from clawteam.team.manager import TeamManager
from clawteam.store.file import FileTaskStore
from clawteam.spawn import get_backend
```

**Option B: MCP Integration** -- Use ClawTeam's MCP server:
```python
# JBCP as MCP client, ClawTeam as MCP server
# Team/task/inbox operations via MCP tool calls
```

**Option C: CLI Integration** -- Shell out to `clawteam` CLI (similar to current JBCP plugin approach):
```python
subprocess.run(["clawteam", "spawn", "tmux", "claude",
    "--team", team_name, "--agent-name", agent_name,
    "--task", task_description])
```

### Recommended Approach

**Library integration (Option A)** is the best fit because:
1. JBCP and ClawTeam are both Python -- no serialization overhead
2. Direct access to event bus for real-time monitoring
3. Can customize spawn behavior (custom adapters, transport backends)
4. Can inject JBCP-specific context into agent prompts
5. Can register custom plugins via the plugin system

### What ClawTeam Provides That JBCP Currently Lacks

| Capability | JBCP Today | With ClawTeam |
|-----------|------------|---------------|
| Parallel agent execution | Single agent via OpenClaw bridge | Multiple agents in tmux with git isolation |
| Agent communication | N/A | Mailbox-based messaging with typed messages |
| Task dependencies | Basic task queue | Full dependency graph with auto-unblock |
| Workspace isolation | N/A | Git worktrees per agent, merge/checkpoint |
| Cross-agent awareness | N/A | File overlap detection, context injection |
| Process monitoring | Basic watchdog | Spawn registry, liveness checks, zombie detection |
| Agent-type flexibility | OpenClaw only | Claude Code, Codex, Gemini, Kimi, nanobot, any CLI |
| Cost tracking | N/A | Per-agent token/cost tracking with cached summaries |
| Phase management | N/A | Harness with gates, contracts, roles |

---

## 11. Key Files and Their Purposes

### Root Configuration
| File | Purpose |
|------|---------|
| `clawteam/__init__.py` | Version: 0.3.0 |
| `clawteam/__main__.py` | Module entry point |
| `clawteam/config.py` | Config system: ClawTeamConfig (Pydantic), AgentProfile, AgentPreset, HookDef. Env var overrides, config file at `~/.clawteam/config.json` |
| `clawteam/paths.py` | Identifier validation (alphanum + `._-`), path escape prevention |
| `clawteam/identity.py` | AgentIdentity dataclass, built from `CLAWTEAM_*` or `CLAUDE_CODE_*` env vars |
| `clawteam/fileutil.py` | `atomic_write_text()` (mkstemp + replace), `file_locked()` (advisory lock context manager) |
| `clawteam/timefmt.py` | Timezone-aware timestamp formatting |

### CLI (`cli/`)
| File | Purpose |
|------|---------|
| `commands.py` | ~2000-line Typer CLI with all command groups. Global `--json`/`--data-dir`/`--transport` flags |

### Team (`team/`)
| File | Purpose |
|------|---------|
| `models.py` | Pydantic models: TeamConfig, TeamMember, TeamMessage, TaskItem, enums (TaskStatus, TaskPriority, MessageType) |
| `manager.py` | TeamManager: CRUD, member management, inbox resolution, cleanup |
| `mailbox.py` | MailboxManager: send/receive/peek/broadcast via pluggable Transport |
| `tasks.py` | Compatibility shim, re-exports FileTaskStore as TaskStore |
| `plan.py` | PlanManager: plan submission, approval, rejection workflow |
| `lifecycle.py` | LifecycleManager: shutdown protocol, idle notification, team cleanup |
| `costs.py` | CostStore: per-agent cost tracking with file-locked rolling summary cache |
| `router.py` | RuntimeRouter: normalize messages, apply routing policy, dispatch to tmux |
| `routing_policy.py` | DefaultRoutingPolicy: throttled same-pair injection (30s), aggregate flush, retry |
| `watcher.py` | InboxWatcher: polling loop for `inbox watch`, supports `--exec` callback and runtime routing |
| `snapshot.py` | Team snapshot/restore |
| `waiter.py` | Task wait (poll until all tasks complete) |

### Transport (`transport/`)
| File | Purpose |
|------|---------|
| `__init__.py` | Transport registry, `get_transport()` factory |
| `base.py` | Transport ABC: deliver, fetch, count, list_recipients, close |
| `file.py` | FileTransport: filesystem-backed with claimed message pattern, dead letter queue |
| `p2p.py` | P2PTransport: ZeroMQ PUSH/PULL with heartbeat, lease-based peer discovery, FileTransport fallback |
| `claimed.py` | ClaimedMessage dataclass: data + ack + quarantine callbacks |

### Spawn (`spawn/`)
| File | Purpose |
|------|---------|
| `__init__.py` | Backend registry, `get_backend()` factory (tmux/subprocess/wsh) |
| `base.py` | SpawnBackend ABC: spawn, list_running |
| `tmux_backend.py` | TmuxBackend: tmux session/window management, trust confirmation, prompt injection via buffer, lifecycle hooks, tiled view |
| `subprocess_backend.py` | SubprocessBackend: fire-and-forget Popen with lifecycle hooks |
| `wsh_backend.py` | WshBackend: WaveTerm/TideTerm terminal blocks |
| `adapters.py` | NativeCliAdapter: agent-specific command preparation (permissions, workspace, prompt flags) for 10+ CLIs |
| `registry.py` | Spawn registry: register/check/stop agents, detect dead/zombie processes |
| `sessions.py` | SessionStore: save/load/clear agent session state for resume |
| `profiles.py` | Profile resolution: load, save, apply to command/env |
| `presets.py` | Built-in provider presets (15+), preset CRUD, profile generation |
| `prompt.py` | Agent prompt builder: identity + task + context + coordination protocol |
| `command_validation.py` | Validate spawn commands (PATH check, executable existence) |
| `cli_env.py` | Build spawn PATH, resolve clawteam executable |
| `wsh_rpc.py` | WaveTerm RPC helpers |

### Board (`board/`)
| File | Purpose |
|------|---------|
| `collector.py` | BoardCollector: aggregates team/task/inbox/cost/conflict data into plain dicts |
| `renderer.py` | BoardRenderer: Rich-based terminal rendering (kanban, overview, live) |
| `server.py` | HTTP server for Web UI with SSE, GitHub README proxy, static files |
| `gource.py` | Gource activity visualization from cross-branch git logs |

### Harness (`harness/`)
| File | Purpose |
|------|---------|
| `orchestrator.py` | HarnessOrchestrator: phase state machine, artifact registration, load/save |
| `conductor.py` | HarnessConductor: auto-drives harness through phases with health checks |
| `phases.py` | PhaseState (Pydantic), PhaseRunner, PhaseGate ABC, built-in gates (ArtifactRequired, AllTasksComplete, HumanApproval) |
| `roles.py` | RoleConfig: planner/executor/evaluator with system prompt addons and phase affinity |
| `contracts.py` | SprintContract: units of work with testable SuccessCriteria |
| `contract_executor.py` | Creates tasks from sprint contracts |
| `strategies.py` | Strategy ABCs: SpawnStrategy, RespawnStrategy, HealthStrategy, ExitNotifier, AssignmentStrategy |
| `spawner.py` | PhaseRoleSpawner: default SpawnStrategy, spawns by phase-role mapping |
| `prompts.py` | Harness-specific system prompts |
| `artifacts.py` | ArtifactStore: file-based artifact persistence |
| `exit_journal.py` | FileExitJournal: cross-process exit notification via JSONL |
| `context.py` | HarnessContext: unified capability interface for plugins (bus, tasks, spawner, sessions, artifacts) |
| `context_recovery.py` | Recovery helpers |

### Workspace (`workspace/`)
| File | Purpose |
|------|---------|
| `__init__.py` | `get_workspace_manager()` helper |
| `manager.py` | WorkspaceManager: create/checkpoint/merge/cleanup git worktrees |
| `context.py` | Cross-agent context: agent_diff, file_owners, cross_branch_log, inject_context |
| `conflicts.py` | Detect file overlaps between agent worktrees, auto-notify via mailbox |
| `git.py` | Git command wrappers: repo_root, create_worktree, remove_worktree, merge_branch, etc. |
| `models.py` | WorkspaceInfo, WorkspaceRegistry (Pydantic) |

### Events (`events/`)
| File | Purpose |
|------|---------|
| `bus.py` | EventBus: sync pub-sub, priority-ordered handlers, async emit via ThreadPoolExecutor |
| `types.py` | 18 event types: BeforeWorkerSpawn, AfterWorkerSpawn, WorkerExit, WorkerCrash, BeforeTaskCreate, AfterTaskUpdate, TaskCompleted, BeforeInboxSend, AfterInboxReceive, BeforeWorkspaceMerge, AfterWorkspaceCleanup, TeamLaunch, TeamShutdown, AgentIdle, HeartbeatTimeout, PhaseTransition, TransportFallback, BoardAttach |
| `hooks.py` | Shell hook execution from config |
| `global_bus.py` | Singleton event bus |

### Plugins (`plugins/`)
| File | Purpose |
|------|---------|
| `base.py` | HarnessPlugin ABC: on_register, on_unregister, contribute_gates, contribute_prompts |
| `manager.py` | PluginManager: discover from entry_points/config/local dirs, load, unload |
| `ralph_loop_plugin.py` | Example plugin: respawn-on-exit loop |

### MCP (`mcp/`)
| File | Purpose |
|------|---------|
| `server.py` | FastMCP server with auto-registered tools |
| `tools/__init__.py` | 26 tool functions registry |
| `tools/team.py` | Team CRUD tools |
| `tools/task.py` | Task CRUD tools |
| `tools/mailbox.py` | Messaging tools |
| `tools/plan.py` | Plan approval tools |
| `tools/board.py` | Board overview/detail tools |
| `tools/cost.py` | Cost summary tool |
| `tools/workspace.py` | Git context tools |
| `helpers.py` | Error translation, validation helpers |

### Templates (`templates/`)
| File | Purpose |
|------|---------|
| `__init__.py` | TOML template loader, variable substitution, TemplateDef model |
| `software-dev.toml` | 5-agent dev team (tech-lead, backend, frontend, QA, devops) |
| `hedge-fund.toml` | 7-agent investment analysis team |
| `code-review.toml` | Code review team template |
| `research-paper.toml` | Research paper writing team |
| `strategy-room.toml` | Strategy analysis team |
| `harness-default.toml` | Default harness template |

### Skills (`skills/clawteam/`)
| File | Purpose |
|------|---------|
| `SKILL.md` | Claude Code / Codex skill definition -- teaches AI agents how to use all ClawTeam commands |
| `references/cli-reference.md` | Complete CLI reference |
| `references/workflows.md` | Multi-agent workflow patterns |
| `agents/openai.yaml` | OpenAI agent config |

### Tests (`tests/`)
37 test files covering all major modules. Key test files include:
`test_adapters.py`, `test_board.py`, `test_cli_commands.py`, `test_config.py`, `test_context.py`, `test_costs.py`, `test_event_bus.py`, `test_fileutil.py`, `test_gource.py`, `test_harness.py`, `test_identity.py`, `test_inbox_routing.py`, `test_lifecycle.py`, `test_mailbox.py`, `test_manager.py`, `test_mcp_server.py`, `test_mcp_tools.py`, `test_models.py`, `test_plan_storage.py`, `test_presets.py`, `test_profiles.py`, `test_prompt.py`, `test_registry.py`, `test_runtime_routing.py`, `test_snapshots.py`, `test_spawn_backends.py`, `test_spawn_cli.py`, `test_store.py`, `test_task_store_locking.py`, `test_tasks.py`, `test_templates.py`, `test_timefmt.py`, `test_waiter.py`, `test_workspace_manager.py`, `test_wsh_backend.py`

---

## Summary

ClawTeam is a well-architected, thoroughly tested framework for multi-agent coordination. Its design philosophy of "agents coordinate themselves via CLI" is a natural fit for Salt Desktop's BUILD phase. The key architectural strengths for our use case are:

1. **Git worktree isolation** -- each agent gets a real branch, preventing merge conflicts during parallel work
2. **Dependency-aware task board** -- tasks auto-unblock when dependencies complete, enabling wave-based parallel execution
3. **Agent-agnostic spawn** -- supports 10+ CLI agents with agent-specific command preparation
4. **Cross-agent context** -- file overlap detection and context injection keep agents aware of each other's work
5. **Pluggable transport** -- file-based for single machine, ZeroMQ for future distributed use
6. **Phase-gated harness** -- structured progression through discuss/plan/execute/verify/ship with gates and contracts
7. **Event bus** -- enables real-time monitoring and plugin-based extensibility
8. **MCP server** -- 26 tools for programmatic access from any MCP client

The recommended integration path is **Python library import** (`from clawteam.xxx import ...`), using ClawTeam's team/task/spawn/workspace modules directly from JBCP's orchestrator and API server.
