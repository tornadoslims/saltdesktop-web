# Subagents

Subagents are child agent instances spawned from a parent agent. They enable delegation of focused tasks while the parent continues its main conversation.

## Two Modes

### Fresh Subagent

A new agent with zero conversation history. Best for independent tasks.

```python
child = agent.subagent_manager.create_fresh(mode="explore", max_turns=15)
async for event in child.run("Find all API endpoints in this codebase"):
    ...
```

### Fork Subagent

Inherits the parent's conversation context. Best for tasks that need the existing context.

```python
child = agent.subagent_manager.create_fork(max_turns=15)
async for event in child.run("Now refactor the function we just discussed"):
    ...
```

**Prompt cache optimization:** Forks use the exact same system prompt and tool definitions as the parent, byte-for-byte. This ensures Anthropic prompt cache hits on the shared prefix, reducing costs.

## Agent Modes

| Mode | Purpose |
|------|---------|
| `general` | Complete the given task efficiently (default) |
| `explore` | Investigate codebases, read files, search patterns, report findings |
| `verify` | Verification specialist: review code for correctness |
| `worker` | Task-focused: write code, edit files, run tests |

Each mode has a tailored system prompt. The `verify` mode uses a dedicated verification prompt from `salt_agent.prompts.verification`.

## Using via the Agent Tool

The LLM can spawn subagents via the `agent` tool:

```
# The model might output:
I'll spawn a subagent to explore the codebase structure.
[tool_use: agent(prompt="Find all Python files and map the module structure", mode="explore")]
```

The agent tool is async -- it yields the child's events into the parent's stream, so the caller sees everything in one unified stream.

## Legacy API

For backward compatibility, `SubagentManager` also provides `spawn_fresh()` and `fork()` methods that run the child to completion:

```python
result = await agent.subagent_manager.spawn_fresh("Count lines of code", mode="worker")
print(result["result"])  # up to 2000 chars

result = await agent.subagent_manager.fork("Refactor this function")
print(result["result"])
```

## Fork Boilerplate

Forked agents receive a structured boilerplate prompt that instructs them to:

1. Execute the task directly and efficiently
2. Not spawn sub-agents
3. Not ask clarifying questions
4. Report results in a structured format (Scope, Result, Key files, Files changed, Issues)

## Events

| Event | When |
|-------|------|
| `subagent_start` | Child agent spawned (type, mode, prompt) |
| `subagent_end` | Child agent completed (type, mode, result_length) |
| `SubagentSpawned` | Yielded to event stream when agent tool runs |
| `SubagentComplete` | Yielded to event stream when agent tool finishes |

## Configuration

Subagents inherit from the parent:

- Provider and model
- API key
- Working directory
- Tool registry (for forks)

Subagents always have:

- `persist=False` (no session files for children)
- `max_turns=15` (default, configurable per spawn)
