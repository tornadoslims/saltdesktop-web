# Context Assembly

Each turn, SaltAgent assembles the full context that is sent to the LLM. This includes the system prompt, conversation history, and per-turn dynamic injections.

## Components

### 1. System Prompt

Built from:

1. **Project instructions** -- `SALT.md` / `CLAUDE.md` from the working directory (and parents)
2. **User-supplied system prompt** -- the `system_prompt` parameter from `AgentConfig`
3. **Dynamic context** -- date/time, working directory, todo state, plan mode

The system prompt is rebuilt from scratch every turn to reflect current state.

### 2. Conversation Messages

The persistent `_conversation_messages` list contains the full conversation history in Anthropic message format:

- `{"role": "user", "content": "..."}` -- user messages
- `{"role": "assistant", "content": [...]}` -- assistant responses (text + tool calls)
- `{"role": "user", "content": [...]}` -- tool results

### 3. System-Reminders (AttachmentAssembler)

Per-turn dynamic context injected as `<system-reminder>` blocks appended to the last user message. These are injected into a **copy** of messages -- never saved to the persistent history.

The `AttachmentAssembler` generates up to 15 types of reminders:

1. **Date/time** -- current UTC date and time
2. **Todo state** -- current todo list content
3. **Plan mode** -- instructions about planning requirements
4. **Skills list** -- available skills (first turn only)
5. **Git status** -- current branch and changed files
6. **Task notifications** -- completed/failed background tasks
7. **File mentions** -- content from files mentioned in the current message
8. **Deferred tools** -- list of tools available via `tool_search`
9. **External modifications** -- files modified outside the agent since last read
10. **Budget warnings** -- cost warnings if approaching budget limit

### 4. Memory Injections

Relevant memories from past sessions, also injected as system-reminders:

```xml
<system-reminder>
Relevant memory (testing_prefs.md):
User prefers pytest -v for all test runs.
</system-reminder>
```

## Assembly Order

The LLM sees context in this order:

```
System prompt:
  1. Project instructions (SALT.md / CLAUDE.md)
  2. User system prompt
  3. Dynamic context (date, cwd, todo, plan mode)

Messages:
  1. Previous conversation history (compacted as needed)
  2. Current user message + system-reminders + memories
```

## Key Design Decisions

### System-reminders are ephemeral

System-reminders are injected into a copy of messages sent to the API but are NOT saved to `_conversation_messages`. This prevents:

- Accumulation of stale context across turns
- Compaction processing of transient information
- Bloated conversation history

### Project instructions have highest priority

Project instructions appear first in the system prompt, before any user-supplied prompt. This ensures project-specific rules (coding standards, test commands) are always applied.

### Compaction preserves structure

The compaction pipeline operates on the persistent `_conversation_messages`, not the ephemeral copy with reminders. This ensures compaction summaries capture actual conversation content, not transient context.

## ContextManager

The `ContextManager` class tracks:

- `system_prompt` -- the current system prompt text
- `_files_read` / `_files_written` -- file access tracking
- `context_window` / `max_tool_result_chars` -- size limits

It provides:

- `estimate_tokens(text)` -- rough token count (~4 chars/token)
- `truncate_tool_result(result)` -- per-result truncation
- `manage_pressure(messages)` -- no-op (compaction handles this now)
