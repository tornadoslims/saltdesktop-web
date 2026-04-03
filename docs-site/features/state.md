# State Management

SaltAgent uses a centralized reactive state store (`StateStore`) that tracks all dynamic agent state. External consumers can subscribe to changes in real-time.

## AgentState Fields

```python
@dataclass
class AgentState:
    # Session
    session_id: str = ""
    session_title: str = ""
    turn_count: int = 0

    # Conversation
    message_count: int = 0
    estimated_tokens: int = 0

    # Agent status
    status: str = "idle"  # idle, thinking, executing_tool, compacting, error
    current_tool: str = ""
    current_tool_input: dict = {}

    # Budget
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost: float = 0.0
    budget_remaining: float = 0.0

    # Active subagents/tasks
    active_tasks: list[str] = []
    active_subagents: int = 0

    # Mode
    auto_mode: bool = False
    plan_mode: bool = False
    coordinator_mode: bool = False

    # Files
    files_read: list[str] = []
    files_written: list[str] = []
    files_modified_externally: list[str] = []

    # Memory
    memory_files_count: int = 0
    memories_surfaced_this_turn: int = 0

    # MCP
    mcp_servers: list[str] = []
    mcp_tools_count: int = 0
```

## Subscribing to Changes

```python
def on_state_change(field_name: str, new_value):
    print(f"{field_name} changed to {new_value}")

agent.state.subscribe(on_state_change)
```

The callback receives the field name and new value whenever a state field changes. Only actual changes trigger notifications (setting a field to its current value is a no-op).

## Reading State

```python
# Single field
status = agent.state.get("status")

# Full snapshot
snapshot = agent.state.snapshot()
print(snapshot["turn_count"])
print(snapshot["total_cost"])
```

## Updating State

The agent loop updates state at key points:

```python
# Agent updates state during the loop
agent.state.update(status="thinking", turn_count=turn + 1)
agent.state.update(status="executing_tool", current_tool="bash")
agent.state.update(total_cost=0.05, total_input_tokens=5000)
```

## Use Cases

### Progress Display

```python
agent.state.subscribe(lambda field, val:
    update_progress_bar(val) if field == "turn_count" else None
)
```

### Cost Monitoring

```python
def check_budget(field, value):
    if field == "total_cost" and value > 1.0:
        print("Warning: cost exceeded $1.00")

agent.state.subscribe(check_budget)
```

### Status Dashboard

```python
def update_dashboard(field, value):
    dashboard.update({field: value})

agent.state.subscribe(update_dashboard)
```

## Safety

- Subscriber callbacks must never crash the agent -- exceptions are silently caught
- State updates are synchronous (no async)
- The state store is not thread-safe -- it's designed for use within the agent's async loop
