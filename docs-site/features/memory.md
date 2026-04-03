# Memory System

SaltAgent has a two-part memory system: project instructions (loaded from files) and cross-session memory (stored in `~/.s_code/memory/`).

## Project Instructions

On every session start, SaltAgent searches for `SALT.md`, `CLAUDE.md`, or `.claude/instructions.md` in the working directory and up to 10 parent directories. These files are injected at the top of the system prompt.

Files closer to the working directory appear first. Content is capped at 5,000 characters per file.

```
/home/user/project/SALT.md          ← loaded first (closest)
/home/user/SALT.md                  ← loaded second
/home/CLAUDE.md                     ← loaded third
```

## Memory Types

Inspired by Claude Code's memory taxonomy, SaltAgent supports 4 memory types:

| Type | Description | When to Save |
|------|-------------|-------------|
| `user` | User's role, goals, preferences, knowledge | Learning about the user |
| `feedback` | Corrections and confirmations of approach | User corrects or confirms |
| `project` | Ongoing work, goals, decisions, deadlines | Decisions, milestones |
| `reference` | Pointers to external systems and resources | Discovering external tools |

## Memory Storage

Memory files are stored in `~/.s_code/memory/` with YAML frontmatter:

```markdown
---
type: feedback
created: 2026-03-30T12:00:00Z
---
User prefers to use pytest with -v flag for all test runs.
Don't ask for confirmation before running tests.
```

The `MEMORY.md` index file provides a catalog:

```markdown
- [Testing preferences](testing_prefs.md) -- pytest -v, no confirmation
- [Project structure](project_structure.md) -- FastAPI in src/api/
```

## Automatic Memory Extraction

Every 5 turns, the `StopHookRunner` scans recent conversation (last 6 messages) and uses an LLM side-query to identify things worth saving to long-term memory.

The extraction prompt asks:
- Is there user information worth remembering?
- Did the user correct or confirm an approach?
- Are there project decisions or deadlines?
- Are there references to external systems?

If the LLM identifies something worth saving, a memory file is created automatically.

## Per-Turn Memory Surfacing

Each turn, SaltAgent:

1. Scans all memory files in the memory directory
2. Sends the current user message + memory catalog to an LLM side-query
3. The LLM ranks which memories are relevant to the current message
4. Relevant memory files are loaded and injected as `<system-reminder>` blocks

This ensures the agent has access to relevant context from past sessions without loading everything.

## Memory Consolidation

Periodically, the `StopHookRunner` consolidates fragmented memories. If there are many small memory files on similar topics, they're merged into fewer, more comprehensive files.

## CLI Commands

| Command | Description |
|---------|-------------|
| `/memory` | List all memory files |
| `/memories` | Same as `/memory` |
| `/forget <file>` | Delete a specific memory file |

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `memory_dir` | `~/.s_code/memory` | Memory file directory |

## Events

| Event | When |
|-------|------|
| `memory_saved` | Memory file was saved |
| `memory_deleted` | Memory file was deleted |
| `memory_surfaced` | Memories were surfaced for this turn |
