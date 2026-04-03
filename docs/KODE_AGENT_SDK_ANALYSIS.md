# KODE Agent SDK Analysis

> Comprehensive analysis for Salt Desktop embeddability assessment.
> Analyzed: 2026-03-30 | Repository: `/Users/jimopenclaw/kode-agent-sdk/`
> Package: `@shareai-lab/kode-sdk` v2.7.4 | License: MIT

---

## Executive Summary

KODE SDK is a **TypeScript/Node.js** agent execution framework (NOT Python) that implements a complete agentic loop with built-in tools, multi-provider support, persistence, streaming events, and multi-agent collaboration. It is MIT-licensed, requires no external CLI binaries, and calls LLM APIs directly via HTTP. It is the closest thing to a "drop-in embeddable agent engine" that exists in open source today.

**However, it is TypeScript-only.** Salt Desktop's backend is Python. This SDK cannot be imported as a Python library. It would need to either:
1. Run as a sidecar Node.js process communicating over IPC/HTTP
2. Be rewritten/ported to Python
3. Serve as a reference architecture for building the equivalent in Python

**Bottom line: Excellent reference architecture, but not directly embeddable in a Python backend.**

---

## 1. What Is It?

A **TypeScript library** (npm package) that implements a full agent execution engine. It is NOT a CLI wrapper -- it calls LLM provider APIs directly using `fetch()`. No shelling out to Claude Code, Codex, or any other binary.

Key architectural components:
- **Agent** class: The core execution engine with a 7-stage breakpoint state machine
- **EventBus**: Three-channel event system (progress/control/monitor)
- **Store**: Pluggable persistence layer (JSON files, SQLite, PostgreSQL)
- **Sandbox**: Pluggable execution environment (local, E2B, OpenSandbox)
- **Provider**: LLM adapter layer (Anthropic, OpenAI, Gemini)
- **Tools**: Built-in tool implementations + custom tool definition API + MCP support
- **AgentPool**: Multi-agent management with up to 50 agents per process
- **Room**: Multi-agent collaboration via broadcast/mention messaging

## 2. License

**MIT License** (Copyright 2025 shareAI-lab). Fully permissive for commercial use, modification, bundling, and redistribution. No restrictions on embedding in a commercial app.

## 3. Agent Execution Loop

Yes, it implements a complete agentic loop. The core cycle in `Agent.runStep()`:

```
1. Flush message queue
2. Check context window size, compress if needed
3. Run pre-model hooks
4. Stream LLM response (with real-time chunk events)
5. Parse tool_use blocks from response
6. If tool calls present:
   a. Check permissions (auto-approve, ask user, deny)
   b. Execute tools (with concurrency control, timeouts, abort signals)
   c. Append tool results to messages
   d. Loop back to step 1 (recursive via ensureProcessing)
7. If no tool calls: emit "done" event, save state
```

The loop is driven by an internal state machine with 7 breakpoint states:
`READY -> PRE_MODEL -> STREAMING_MODEL -> TOOL_PENDING -> AWAITING_APPROVAL -> PRE_TOOL -> TOOL_EXECUTING -> POST_TOOL`

Key features:
- **5-minute processing timeout** with automatic restart
- **Context compression** when token count exceeds threshold (default 50k tokens)
- **WAL-protected persistence** at every state transition
- **Crash recovery** via `Agent.resume()` with automatic sealing of incomplete tool calls
- **Interrupt support** with graceful tool abort

## 4. Built-in Tools

| Tool | Name | Description |
|------|------|-------------|
| File Read | `fs_read` | Read file with offset/limit support |
| File Write | `fs_write` | Write file with directory auto-creation |
| File Edit | `fs_edit` | String replacement (single or all occurrences) |
| Multi Edit | `fs_multi_edit` | Multiple edits in a single call |
| Glob | `fs_glob` | Pattern-based file search |
| Grep | `fs_grep` | Content search with regex |
| Bash Run | `bash_run` | Command execution with timeout, background mode |
| Bash Logs | `bash_logs` | Read output from background shells |
| Bash Kill | `bash_kill` | Kill background processes |
| Todo Read | `todo_read` | Read agent todo list |
| Todo Write | `todo_write` | Update agent todo list |
| Task Run | `task_run` | Delegate work to sub-agents |

Tools are defined using Zod schemas and execute within a sandboxed context. The sandbox enforces:
- Path boundary checking (files must be within workDir or allowPaths)
- Dangerous command blocking (rm -rf /, sudo, fork bombs, etc.)
- Configurable timeouts (default 120s for bash)

Additionally supports:
- **MCP tools** via `@modelcontextprotocol/sdk` (stdio, SSE, HTTP transports)
- **Custom tools** via `defineTool()` / `tool()` API with Zod parameter schemas
- **ToolKit classes** with `@toolMethod` decorators

## 5. External Binary Dependencies

**None.** The SDK is pure TypeScript + npm dependencies. It calls LLM APIs directly via `fetch()` (using `undici` for proxy support). No dependency on:
- Claude Code CLI
- OpenAI Codex
- Any shell-based AI tool

The only system dependency is Node.js >= 18.

npm dependencies of note:
- `@modelcontextprotocol/sdk` - MCP protocol support
- `better-sqlite3` - Native SQLite bindings (optional, for SqliteStore)
- `pg` - PostgreSQL client (optional, for PostgresStore)
- `e2b` - E2B cloud sandbox (optional)
- `@alibaba-group/opensandbox` - OpenSandbox (optional)
- `zod` - Schema validation for tool parameters
- `ajv` - JSON Schema validation
- `fast-glob` - File pattern matching

## 6. LLM Provider Support

| Provider | Class | Streaming | Tools | Reasoning/Thinking | File Upload |
|----------|-------|-----------|-------|--------------------|-------------|
| Anthropic | `AnthropicProvider` | Yes (SSE) | Yes | Extended Thinking | Yes (Files API) |
| OpenAI | `OpenAIProvider` | Yes (SSE) | Yes | Reasoning tokens | Yes |
| Gemini | `GeminiProvider` | Yes (SSE) | Yes | ThinkingBudget/Level | Yes (GCS URIs) |

OpenAI-compatible services (DeepSeek, GLM, Qwen, Minimax, OpenRouter) work via `OpenAIProvider` with custom `baseURL`. The OpenAI provider has special handling for:
- DeepSeek's `reasoning_content` field
- GLM's thinking parameter
- Minimax's `reasoning_details` array format
- Qwen's `enable_thinking` parameter
- GPT-5.x Responses API vs Chat Completions API

All providers implement the same `ModelProvider` interface:
```typescript
interface ModelProvider {
  complete(messages: Message[], opts?: CompletionOptions): Promise<ModelResponse>;
  stream(messages: Message[], opts?: CompletionOptions): AsyncIterable<ModelStreamChunk>;
  uploadFile?(input: UploadFileInput): Promise<UploadFileResult | null>;
  toConfig(): ModelConfig;
}
```

## 7. Can It Be Imported as a Library?

**Yes, but only in Node.js/TypeScript projects.** The package exports a clean API surface:

```typescript
import {
  Agent, AgentPool, Room, Scheduler,
  AnthropicProvider, OpenAIProvider, GeminiProvider,
  JSONStore, SqliteStore, PostgresStore,
  LocalSandbox, E2BSandbox, OpenSandbox,
  builtin, defineTool, tool, ToolKit,
  EventBus, HookManager, ContextManager,
  // ... 100+ exports
} from '@shareai-lab/kode-sdk';
```

The core usage pattern:
```typescript
const agent = await Agent.create({
  templateId: 'my-template',
  sandbox: { kind: 'local', workDir: '/path' },
}, dependencies);

const result = await agent.complete('Do the thing');
// or stream:
for await (const event of agent.stream('Do the thing')) { ... }
```

**NOT importable from Python.** There is no Python wrapper, no gRPC/REST API built in (though the architecture supports adding one -- the README shows a worker microservice pattern).

## 8. Streaming Support

**Excellent streaming support** via three mechanisms:

### a) AsyncIterable Streaming
```typescript
for await (const envelope of agent.stream('Hello')) {
  if (envelope.event.type === 'text_chunk') {
    process.stdout.write(envelope.event.delta);
  }
  if (envelope.event.type === 'tool:start') { /* tool executing */ }
  if (envelope.event.type === 'done') break;
}
```

### b) Three-Channel Event Subscription
```typescript
for await (const envelope of agent.subscribe(['progress', 'control', 'monitor'])) {
  // Progress: text chunks, thinking chunks, tool start/end, done
  // Control: permission_required, permission_decided
  // Monitor: state changes, errors, token usage, compression, etc.
}
```

### c) Event-Based Hooks
```typescript
agent.on('permission_required', (evt) => { evt.respond('allow'); });
agent.on('error', (evt) => { console.error(evt.message); });
agent.on('token_usage', (evt) => { track(evt.totalTokens); });
```

The event types are comprehensive (30+ distinct event types across the three channels), covering every phase of agent execution.

## 9. Multi-Agent / Parallel Execution

**Yes, with multiple mechanisms:**

### AgentPool (up to 50 agents per process)
```typescript
const pool = new AgentPool({ dependencies, maxAgents: 50 });
const agent1 = await pool.create('agent-1', config1);
const agent2 = await pool.create('agent-2', config2);
// Graceful shutdown with state persistence
await pool.gracefulShutdown({ timeout: 30000, saveRunningList: true });
// Resume all agents after restart
await pool.resumeFromShutdown(configFactory);
```

### Room (Multi-Agent Collaboration)
```typescript
const room = new Room(pool);
room.join('researcher', 'agent-1');
room.join('writer', 'agent-2');
await room.say('researcher', 'I found the data @writer please write the report');
// Directed @mention or broadcast to all members
```

### Sub-Agent Delegation (task_run tool)
```typescript
// Parent agent can delegate tasks to child agents
// with configurable recursion depth, template restrictions, and model overrides
const result = await agent.delegateTask({
  templateId: 'code-reviewer',
  prompt: 'Review this PR',
  model: { provider: 'anthropic', model: 'claude-sonnet-4-20250514' },
});
```

### Fork (Explore Different Trajectories)
```typescript
const snapshotId = await agent.snapshot('before-risky-change');
const fork = await agent.fork(snapshotId);
// fork is independent -- different conversation branches
```

## 10. Comparison: KODE SDK vs Building Our Own SaltAgent

### What KODE SDK Gets Right (and we should learn from)

| Feature | KODE SDK | Our learn-claude-code Approach |
|---------|----------|-------------------------------|
| **Agent loop** | Complete with breakpoints, timeouts, crash recovery | Would need to build from scratch |
| **Tool execution** | Sandboxed, concurrent, with abort/timeout | Would need to build |
| **Event streaming** | Three-channel system, 30+ event types | Would need to design |
| **Persistence** | WAL-protected JSON, SQLite, PostgreSQL | Would need to build |
| **Context management** | Auto-compression with history windows | Would need to build |
| **Permission system** | Auto/ask/deny modes with approval workflow | Would need to build |
| **Multi-provider** | Anthropic, OpenAI, Gemini with reasoning support | We only need Anthropic |
| **Multi-agent** | Pool, Room, sub-agents, fork | Nice to have |
| **MCP integration** | Built-in stdio/SSE/HTTP | Would be nice |

### What KODE SDK Lacks (for our use case)

| Gap | Impact |
|-----|--------|
| **TypeScript only** | Cannot embed in Python backend |
| **No Python SDK** | No way to call from our FastAPI/Python stack |
| **No REST API** | Would need to wrap in a web server |
| **Chinese comments in source** | Minor readability issue for our team |
| **Heavy dependencies** | better-sqlite3, pg, e2b, opensandbox all bundled |
| **No built-in auth** | Would need to add user isolation |

### Recommendation

**Use KODE SDK as the reference architecture, but build SaltAgent in Python.**

The key patterns to adopt:
1. **7-stage breakpoint state machine** for the agent loop
2. **Three-channel event system** (progress/control/monitor)
3. **WAL-protected persistence** with crash recovery
4. **Sandboxed tool execution** with boundary enforcement
5. **Permission system** with auto/ask/deny modes
6. **Context compression** with history windows
7. **Zod-like parameter schemas** (use Pydantic in Python)

## 11. Is This the "Standalone Library" We Were Looking For?

**Partially.** It is:
- A standalone library (npm package, no external binaries)
- Embeddable in Node.js backends
- No per-user process overhead (AgentPool handles 50 agents in one process)
- Clean API surface for programmatic use

It is NOT:
- Embeddable in Python backends (TypeScript only)
- A Python library
- Something we can `pip install` and use

**If Salt Desktop were a Node.js/TypeScript backend**, this would be a near-perfect fit. Since we're Python, it's an excellent reference architecture but not a direct dependency.

---

## Architecture Diagram (from source analysis)

```
Agent.create(config, deps)
    |
    v
+-------------------+
|    Agent          |
|  State Machine    |  READY -> PRE_MODEL -> STREAMING -> TOOL_PENDING -> ...
|                   |
|  +-- EventBus ----+---> progress channel (text_chunk, tool:start, done)
|  |                +---> control channel (permission_required)
|  |                +---> monitor channel (state_changed, error, token_usage)
|  |                |
|  +-- Model -------+---> AnthropicProvider.stream() -> SSE -> chunks
|  |                |     OpenAIProvider.stream()
|  |                |     GeminiProvider.stream()
|  |                |
|  +-- Sandbox -----+---> LocalSandbox (exec, fs.read, fs.write, glob)
|  |                |     E2BSandbox (remote cloud sandbox)
|  |                |     OpenSandbox (self-hosted)
|  |                |
|  +-- Tools -------+---> fs_read, fs_write, fs_edit, bash_run, ...
|  |                |     MCP tools (stdio/SSE/HTTP)
|  |                |     Custom tools (defineTool/tool API)
|  |                |
|  +-- Store -------+---> JSONStore (.kode/ directory, WAL-protected)
|  |                |     SqliteStore (better-sqlite3)
|  |                |     PostgresStore (pg)
|  |                |
|  +-- Context -----+---> Token counting, auto-compression
|  |   Manager      |     History windows, recovered files
|  |                |
|  +-- Permissions --+---> auto | ask | deny
|  |   Manager      |     Hook-based approval workflow
|  |                |
|  +-- Hooks -------+---> preModel, postModel, preTool, postTool
|                   |
+-------------------+
        |
        v
AgentPool (up to 50 agents)
Room (multi-agent collaboration)
Scheduler (cron, step-based, time-based triggers)
```

---

## Source File Inventory

### Core (`src/core/`) - 17 files
- `agent.ts` - Main Agent class (~1300 lines), the heart of the system
- `agent/breakpoint-manager.ts` - 7-stage state machine
- `agent/message-queue.ts` - Internal message queue with flush control
- `agent/permission-manager.ts` - Permission evaluation and approval
- `agent/todo-manager.ts` - Todo list management
- `agent/tool-runner.ts` - Concurrent tool execution with throttling
- `config.ts` - Configurable mixin
- `context-manager.ts` - Token counting, compression, history windows
- `errors.ts` - Resume errors, validation errors
- `events.ts` - EventBus with three channels, subscriber system
- `file-pool.ts` - File access tracking and change detection
- `hooks.ts` - Pre/post model and tool hooks
- `permission-modes.ts` - Permission mode registry
- `pool.ts` - AgentPool with graceful shutdown
- `room.ts` - Multi-agent Room with @mentions
- `scheduler.ts` - Cron, step-based, time-based scheduling
- `skills/` - Skills system (6 files)
- `template.ts` - Agent template registry
- `todo.ts` - Todo service
- `types.ts` - All TypeScript type definitions (~490 lines)

### Infrastructure (`src/infra/`) - 16 files
- `provider.ts` - Re-exports from providers/
- `providers/anthropic.ts` - Anthropic API adapter (~400 lines)
- `providers/openai.ts` - OpenAI/compatible adapter (~800 lines estimated)
- `providers/gemini.ts` - Gemini API adapter
- `providers/types.ts` - Provider interfaces
- `providers/utils.ts` - Shared utilities (proxy, formatting, normalization)
- `providers/core/` - Error handling, retry, usage tracking, fork utilities
- `sandbox.ts` - LocalSandbox with boundary enforcement (~300 lines)
- `sandbox-factory.ts` - Factory for creating sandboxes
- `store.ts` - Re-exports
- `store/json-store.ts` - JSON file store with WAL (~700 lines)
- `store/types.ts` - Store interface definition (~420 lines)
- `store/factory.ts` - Store factory
- `db/sqlite/sqlite-store.ts` - SQLite store implementation
- `db/postgres/postgres-store.ts` - PostgreSQL store implementation
- `e2b/` - E2B cloud sandbox (4 files)
- `opensandbox/` - OpenSandbox integration (4 files)

### Tools (`src/tools/`) - 24 files
- 9 built-in tools (fs_read, fs_write, fs_edit, fs_multi_edit, fs_glob, fs_grep, bash_run, bash_logs, bash_kill)
- 3 agent tools (todo_read, todo_write, task_run)
- `define.ts` - Tool definition API
- `tool.ts` - Enhanced tool definition with Zod
- `toolkit.ts` - Class-based toolkit with decorators
- `registry.ts` - Global tool registry
- `mcp.ts` - MCP protocol integration
- `builtin.ts` - Built-in tool groups
- `skills.ts` - Skills tool
- `scripts.ts` - Scripts tool
- `type-inference.ts` - Schema builder utilities

### Tests - 16+ test files
- Unit tests, integration tests, E2E tests, security tests
- Mock provider for testing without API calls

---

## Key Takeaways for Salt Desktop

1. **Language mismatch is the dealbreaker.** This is TypeScript. We need Python.

2. **The architecture is excellent.** The 7-stage breakpoint system, three-channel events, WAL persistence, and sandboxed tool execution are exactly what we need.

3. **The tool definitions match Claude Code patterns.** FsRead, FsEdit, BashRun, etc. are implemented almost identically to what we see in learn-claude-code.

4. **The provider abstraction is clean.** A single `ModelProvider` interface with `complete()` and `stream()` methods. We can replicate this trivially with the Anthropic Python SDK.

5. **Consider a hybrid approach:** Use KODE SDK as a Node.js sidecar for actual agent execution, with our Python backend handling orchestration, auth, and business logic. Communication via HTTP or Unix sockets.

6. **Or build SaltAgent in Python** using this as the definitive reference. The patterns are clear, the interfaces are well-defined, and we already understand the Claude Code tool contracts from learn-claude-code.

**Recommended path: Build `SaltAgent` in Python, using KODE SDK's architecture as the blueprint and learn-claude-code's tool implementations as the reference.**
