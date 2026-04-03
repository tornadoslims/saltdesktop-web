# Task and Subagent Tools

## Background Tasks

Background tasks run independent agent instances in daemon threads. Each task gets its own `SaltAgent`, event loop, and conversation context.

### task_create

Create and start a background task.

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `prompt` | string | yes | What the background task should do |

**Returns:** Task ID and confirmation.

### task_list

List all background tasks and their current status.

No parameters.

**Returns:** Formatted list with task IDs, status, and prompt previews.

### task_get

Get detailed information about a specific task.

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `task_id` | string | yes | The task ID to look up |

**Returns:** Task details including status, prompt, timing, and event count.

### task_output

Get the output of a completed task.

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `task_id` | string | yes | The task ID |

**Returns:** Task output text, or status message if still running/failed.

### task_stop

Stop a running background task.

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `task_id` | string | yes | The task ID to stop |

**Returns:** Confirmation or error.

### task_update

Update a task's status.

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `task_id` | string | yes | The task ID |
| `status` | string | no | New status: `pending`, `running`, `completed`, `failed`, `stopped` |

### Task Lifecycle

```
create → PENDING → RUNNING → COMPLETED
                            → FAILED
                            → STOPPED (via task_stop)
```

### Task Hooks

| Event | When |
|-------|------|
| `task_created` | Task created and thread started |
| `task_completed` | Task finished successfully |
| `task_failed` | Task threw an exception |

---

## agent (Subagent Tool)

Spawn a subagent to handle a focused task. The subagent gets its own context and tools but shares the working directory.

### Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `prompt` | string | yes | What the subagent should do |
| `mode` | string | no | Agent mode: `explore`, `verify`, `worker`, `general` (default) |

### Modes

| Mode | System Prompt |
|------|--------------|
| `explore` | Investigation-focused: read files, search patterns, report findings |
| `verify` | Verification specialist: review code for correctness |
| `worker` | Task-focused: write code, edit files, run tests |
| `general` | Default: complete the given task efficiently |

### How It Works

The `agent` tool is an **async tool** -- it yields events from the child agent into the parent's event stream:

1. Parent agent calls the `agent` tool
2. `SubagentManager.create_fresh()` creates a new `SaltAgent` with its own context
3. The child agent runs to completion, yielding events
4. Events flow through the parent's stream (`SubagentSpawned`, child's `TextChunk`/`ToolStart`/`ToolEnd`, then `SubagentComplete`)
5. The final text is returned as the tool result

### Subagent Types

| Method | Description | Use Case |
|--------|-------------|----------|
| `create_fresh(mode)` | Zero-context child | Exploration, verification, focused tasks |
| `create_fork()` | Inherits parent context | Tasks needing conversation history |

**Fork optimization:** Forked children use the exact same system prompt and tool definitions as the parent, enabling Anthropic prompt cache hits on the shared prefix.

### Events

| Event | When |
|-------|------|
| `SubagentSpawned` | Child agent started (mode, prompt) |
| `SubagentComplete` | Child agent finished (mode, result) |
