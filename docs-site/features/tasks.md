# Background Tasks

Background tasks run independent agent instances in daemon threads. Unlike subagents (which block the parent), tasks run concurrently and can be checked later.

## How It Works

1. The agent calls `task_create` with a prompt
2. A new `SaltAgent` is created in a daemon thread with its own event loop
3. The main agent continues working while the task runs
4. The task collects events and output as it executes
5. When complete, hooks fire and callbacks are invoked

## Task Lifecycle

```
task_create → PENDING → RUNNING → COMPLETED
                                → FAILED
                                → STOPPED (via task_stop)
```

## Tools

| Tool | Description |
|------|-------------|
| `task_create` | Create and start a background task |
| `task_list` | List all tasks and their status |
| `task_get` | Get detailed task information |
| `task_output` | Get a task's output text |
| `task_stop` | Stop a running task |
| `task_update` | Update a task's status |

## Programmatic Usage

```python
agent = create_agent(provider="openai")

# Create tasks
task1 = agent.task_manager.create_task("Analyze test coverage")
task2 = agent.task_manager.create_task("Find all TODO comments")

# Check status
for task in agent.task_manager.list_tasks():
    print(f"{task.id}: {task.status.value}")

# Get output when done
output = agent.task_manager.get_output(task1.id)

# Register completion callback
agent.task_manager.on_complete(lambda task: print(f"Task {task.id} done!"))
```

## Task Data

```python
@dataclass
class Task:
    id: str                # Short UUID (8 chars)
    prompt: str            # What the task should do
    status: TaskStatus     # pending/running/completed/failed/stopped
    output: str            # Final output text
    error: str             # Error message (if failed)
    created_at: str        # ISO timestamp
    started_at: str        # ISO timestamp
    completed_at: str      # ISO timestamp
    events: list[dict]     # All events from the task's agent
```

## Events

| Event | Data |
|-------|------|
| `task_created` | `task_id`, `prompt` |
| `task_completed` | `task_id`, `output_length` |
| `task_failed` | `task_id`, `error` |

## Comparison to Subagents

| Feature | Subagents | Tasks |
|---------|-----------|-------|
| Execution | Inline (blocks parent turn) | Background (daemon thread) |
| Context | Can fork parent context | Always fresh |
| Events | Yielded to parent stream | Collected in task object |
| Max turns | Configurable per spawn | Fixed at 15 |
| Persistence | No | No |
| Use case | Focused work within a turn | Long-running parallel work |
