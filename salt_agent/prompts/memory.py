"""Memory management prompt for SaltAgent.

Adapted from Claude Code's dream memory consolidation, session memory update,
and memory description prompts. Governs what to remember, what to forget,
and how to persist knowledge across sessions.
"""

MEMORY_PROMPT = """You are performing a memory consolidation pass. Synthesize what you have learned recently into durable, well-organized memories so that future sessions can orient quickly.

## Phase 1 — Orient

- List the memory directory to see what already exists.
- Read the index file to understand the current memory structure.
- Skim existing topic files so you improve them rather than creating duplicates.

## Phase 2 — Gather Recent Signal

Look for new information worth persisting. Sources in priority order:

1. Daily logs and activity records if present.
2. Existing memories that have drifted — facts that contradict the current state of the codebase.
3. Recent session context — search narrowly for specific details, do not exhaustively read transcripts.

## Phase 3 — Consolidate

For each thing worth remembering, write or update a memory file. Focus on:

- Merging new signal into existing topic files rather than creating near-duplicates.
- Converting relative dates ("yesterday", "last week") to absolute dates so they remain interpretable after time passes.
- Deleting contradicted facts — if today's investigation disproves an old memory, fix it at the source.

### What to Remember

- User preferences and how they approach work (both what to avoid and what to keep doing).
- Key architectural decisions and their rationale.
- Code patterns, style conventions, and common issues in the codebase.
- File paths and function locations for frequently referenced code.
- Errors encountered and their resolutions.
- Domain-specific terminology and conventions.

### What NOT to Remember

- Transient operational details (specific command outputs, temporary error messages).
- Information that is already documented in project config files or README.
- Speculative or uncertain information — only record confirmed facts.
- Negative judgments about the user that are not relevant to the work.

### How to Write Memories

- Write concise, actionable notes. Each memory should be one clear fact or guideline.
- Include enough context that the memory is useful without the original conversation.
- Group related memories into topic files.
- Record from both failure AND success: if you only save corrections, you will avoid past mistakes but drift away from validated approaches.

## Phase 4 — Prune and Index

Update the index so it stays compact. It is an index, not a dump — each entry should be one line with a brief hook. Never write memory content directly into the index.

- Remove pointers to memories that are now stale, wrong, or superseded.
- Add pointers to newly important memories.
- Resolve contradictions — if two files disagree, fix the wrong one.
"""
