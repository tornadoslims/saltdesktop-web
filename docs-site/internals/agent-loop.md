# Agent Loop

The core of SaltAgent is the `run()` method on `SaltAgent`. It implements an iterative loop that alternates between LLM calls and tool execution.

## Entry Point

```python
async def run(self, prompt: str) -> AsyncIterator[AgentEvent]:
```

The method is an async generator that yields `AgentEvent` objects as the agent works. The caller iterates over events to observe progress.

## Step-by-Step

### 1. Session Initialization

- Fire `session_start` hook
- Update state: `status="thinking"`, session ID, mode flags
- Lazy-start MCP servers (first run only)

### 2. Message Append

The user prompt is appended to `_conversation_messages`, the persistent conversation history. In interactive mode, this accumulates across multiple `run()` calls.

### 3. Turn Loop

For each turn (up to `max_turns`):

#### 3a. Loop Detection

Check the last 6+ tool call signatures for repeating patterns of length 1-4. If a pattern repeats 3+ times:

- First detection: inject a warning message telling the model to reassess
- Second detection: hard stop with `AgentError`

Signatures are `tool_name:md5(input)[:8]` strings.

#### 3b. Compaction Pipeline

Five layers fire in order:

1. **Microcompact** (every turn) -- truncate old tool results, cached to avoid reprocessing
2. **History snip** (60%) -- trim old assistant text
3. **Context collapse** (70%) -- fold tool call/result pairs
4. **Autocompact** (80%) -- LLM summarization
5. **Emergency truncate** (95%) -- drop old messages

#### 3c. System Prompt Rebuild

Reassemble from scratch each turn:

- Project instructions (`SALT.md` / `CLAUDE.md`)
- User-supplied system prompt
- Dynamic context: date/time, working directory, todo state, plan mode

#### 3d. System-Reminder Injection

The `AttachmentAssembler` generates per-turn `<system-reminder>` blocks:

- Date/time
- Todo state
- Plan mode instructions
- Available skills (first turn)
- Git status (if in a git repo)
- Background task notifications
- File mentions from the current message
- Deferred tool lists

These are injected into a **copy** of messages (not saved to history).

#### 3e. Memory Surfacing

An LLM side-query ranks memory files against the current message. Relevant memories are injected as system-reminders.

#### 3f. Checkpoint

Save conversation to JSONL before the API call (crash recovery).

#### 3g. Budget Check

If `max_budget_usd` is set and exceeded, stop with `AgentError`.

#### 3h. LLM Stream

Call the provider's `stream_response()`. Events are processed as they arrive:

- `TextChunk` -- accumulate text, yield to caller
- `ToolUse` -- submit to `StreamingToolExecutor` (safe tools start immediately)
- `AgentError` -- handle prompt-too-long by emergency truncating

#### 3i. Tool Execution

After the stream:

1. Execute remaining queued tools
2. For each tool:
   - Fire `pre_tool_use` hook (can block)
   - Execute the tool (sync or async)
   - Fire `post_tool_use` hook
   - Yield `ToolStart` and `ToolEnd` events
3. Assemble tool results into messages

#### 3j. Token Budget Update

Record real token usage from the provider's `last_usage` data.

#### 3k. Stop Hooks

Post-turn processing:

- Memory extraction (every 5 turns)
- Session title generation (first turn)
- Turn stats logging
- Memory consolidation
- Follow-up suggestion generation

#### 3l. Continue or Stop

- If no tool calls in this turn: yield `AgentComplete`, update state to "idle", fire hooks, return
- If tools were used: append results, continue to next turn

### 4. Turn Limit

If `max_turns` is reached without completion, yield `AgentComplete` with whatever text the model generated.

## Prompt-Too-Long Recovery

If the LLM returns a "prompt too long" error:

1. Emergency truncate messages to 50% of context window
2. Retry the turn
3. If it fails again, yield `AgentError`

## Interactive Mode

In interactive mode, `_conversation_messages` persists between `run()` calls. Each new `run()` appends the user message and continues from the existing history. This is what enables multi-turn conversations.

## Conversation Flow

```
run("Fix the bug")
  └─ messages: [user: "Fix the bug"]
  └─ turn 1: model reads file → messages: [user, assistant+tool_use, tool_result]
  └─ turn 2: model edits file → messages: [..., assistant+tool_use, tool_result]
  └─ turn 3: model says "Done" → AgentComplete

run("Now add tests")
  └─ messages: [...previous..., user: "Now add tests"]
  └─ turn 1: model writes test → ...
  └─ ...
```
