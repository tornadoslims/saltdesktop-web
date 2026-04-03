# Claude Code Internals: Technical Analysis for SaltAgent

> Comprehensive analysis based on: leaked system prompt (v2.1.50), Piebald-AI prompt archive (v2.1.84-2.1.90), Codex static analysis report (1,907 files, 12,920 import edges), learn-claude-code reference implementations, and KODE Agent SDK architecture.
>
> Date: 2026-03-30

---

## 1. System Prompt Analysis

### 1.1 Structure and Composition

Claude Code's system prompt is NOT a single monolithic string. It is **assembled at runtime** from dozens of modular fragments, gated by feature flags, mode state, and session context. The `QueryEngine.submitMessage()` method constructs it from:

- Default system prompt fragments (tone, task management, tool usage policy, security)
- User context (CLAUDE.md files, memory files)
- System context (environment info, git status, date, model info)
- Optional caller-supplied custom system prompt
- Optional append-only prompt text
- Memory-mechanics prompt when auto-memory is active
- Mode-specific injections (plan mode, auto mode, learning mode, buddy mode, minimal mode)

This is a critical insight: **the prompt is a living document that changes every turn**, not a static template.

### 1.2 Core Behavioral Instructions

The system prompt enforces these behavioral rules:

**Identity and Tone:**
- "You are a Claude agent, built on Anthropic's Claude Agent SDK"
- No emojis unless explicitly requested
- Output is for CLI display in monospace font, Github-flavored markdown
- Short, concise responses. Professional objectivity over validation
- Never give time estimates
- Lead with answers, not reasoning

**Task Execution Philosophy:**
- NEVER propose changes to code you haven't read
- Use TodoWrite VERY frequently for task tracking
- Be careful not to introduce security vulnerabilities
- Avoid over-engineering: only make changes directly requested
- Don't add features, refactor code, or make "improvements" beyond what was asked
- Don't add error handling for scenarios that can't happen
- Don't create helpers for one-time operations
- If something is unused, delete it completely

**Tool Usage Policy:**
- Prefer specialized tools over bash (Read over cat, Edit over sed, Grep over grep)
- Call multiple tools in parallel when there are no dependencies
- Use Task tool for file search to reduce context usage
- Use Task/Explore agent for broader codebase exploration

**Safety:**
- Assist with authorized security testing, CTFs, educational contexts
- Refuse destructive techniques, DoS attacks, supply chain compromise
- Never generate or guess URLs unless for programming help
- Git safety: never force push, never skip hooks, never amend unless asked

### 1.3 The "Never Over-Engineer" Philosophy

This is perhaps the most distinctive aspect of the prompt. Claude Code is explicitly told:

> "Don't add features, refactor code, or make 'improvements' beyond what was asked. A bug fix doesn't need surrounding code cleaned up. A simple feature doesn't need extra configurability. Don't add docstrings, comments, or type annotations to code you didn't change."

> "Three similar lines of code is better than a premature abstraction."

This is the opposite of what most developers instinctively do. It makes the agent feel disciplined and focused.

### 1.4 System Reminders

Claude Code uses `<system-reminder>` tags injected into tool results and user messages to provide contextual information. These are explicitly described to the model as "automatically added by the system" with "no direct relation to the specific tool results or user messages in which they appear." This is how the system injects:

- Current date
- Available skills
- Token usage warnings
- Plan mode status
- File modification notifications
- Memory file contents
- Diagnostic information

---

## 2. Agent Loop Architecture

### 2.1 The Core Query Loop (query.ts)

The heart of Claude Code is an iterative assistant/tool loop in `query.ts`. It maintains mutable per-turn state:

```
current messages
tool-use context
max-output recovery counters
auto-compact tracking
pending tool-use summary
turn count
transition state
```

Each iteration:
1. Start request tracking
2. Prefetch relevant memory and skill-discovery
3. Apply tool-result budgeting / content replacement
4. Apply history snip (when enabled)
5. Apply microcompact
6. Project/apply context collapses (when enabled)
7. Run autocompact if required
8. Update tool use context messages
9. Set up streaming tool execution state
10. Call the model with streaming
11. Yield assistant stream output (unless withheld for recoverable errors)
12. Stream completed tool results opportunistically
13. Handle fallback-model retries if provider triggers fallback
14. Recover from prompt-too-long, media overflow, or max-output situations
15. Execute follow-up tool rounds until the assistant stops requesting tools

**Key insight: Error recovery, tool concurrency, context pressure management, and follow-up prompting all live INSIDE the loop.** Callers never need to implement retry logic, prompt-too-long recovery, or partial-message handling.

### 2.2 Two Execution Surfaces, One Runtime

Claude Code has two major execution paths:

**Interactive path:**
```
main.tsx -> setup.ts -> interactiveHelpers.tsx -> screens/REPL.tsx
  -> processUserInput.ts -> query.ts -> tool execution / hooks / persistence
```

**Headless/SDK path:**
```
main.tsx -> cli/print.ts -> runHeadless() -> QueryEngine.ts
  -> processUserInput.ts -> query.ts -> same core loop
```

Both share the same: prompt assembly, tool registry, model invocation, permission gating, hook dispatch, transcript persistence, compaction, MCP integration, and task/agent infrastructure.

### 2.3 Streaming Tool Execution

When enabled, `query.ts` creates a `StreamingToolExecutor` early in the turn. As streamed assistant messages arrive:
- Tool-use blocks are detected
- Tool executions are **scheduled immediately** (before the full response arrives)
- Completed tool results are emitted as soon as available
- Orphaned tool results are discarded on fallback/retry transitions

This is a major latency optimization: tools start executing while the model is still generating.

### 2.4 Turn Lifecycle

```
User input
  -> processUserInput.ts (classify: prompt / slash command / bash mode)
  -> attachment/context synthesis (files, memory, plans, IDE state, MCP deltas)
  -> message persistence (BEFORE the API call, for resume safety)
  -> query.ts loop
    -> context reduction (budgeting, snip, microcompact, collapse, autocompact)
    -> API streaming
    -> streaming tool execution
    -> follow-up assistant turns
    -> hooks, notifications, persistence updates
    -> optional compaction/recovery
  -> UI or structured output emission
```

### 2.5 How It Decides When It's "Done"

The loop terminates when:
- The model's `stop_reason` is NOT `tool_use` (i.e., the model chose to respond with text only)
- A fatal error occurs that cannot be recovered
- Max turns limit is reached (for subagents: `max_turns` parameter, default 200 for forks)

There is no explicit "done" signal. The model naturally stops calling tools when it believes the task is complete. The TodoWrite system helps the model self-track completion.

---

## 3. Tool Definitions (Complete List with Schemas)

### 3.1 Core Tools

| Tool | Purpose | Key Parameters |
|------|---------|---------------|
| **Bash** | Execute shell commands | `command` (string), `timeout` (ms, max 600000), `description` (string), `run_in_background` (bool), `dangerouslyDisableSandbox` (bool) |
| **Read** | Read files from filesystem | `file_path` (string, absolute), `offset` (number), `limit` (number), `pages` (string, for PDFs) |
| **Edit** | Exact string replacement in files | `file_path` (string), `old_string` (string), `new_string` (string), `replace_all` (bool) |
| **Write** | Write/overwrite files | `file_path` (string, absolute), `content` (string) |
| **Glob** | Fast file pattern matching | `pattern` (string), `path` (string, optional) |
| **Grep** | Content search (ripgrep-based) | `pattern` (regex), `path` (string), `glob` (string), `output_mode` (content/files_with_matches/count), `-A/-B/-C` (context lines), `-i` (case insensitive), `type` (file type), `head_limit`, `offset`, `multiline` |
| **TodoWrite** | Task tracking | `todos` (array of {content, status, activeForm}) |
| **Task** | Launch subagent | `description` (string), `prompt` (string), `subagent_type` (string), `model` (sonnet/opus/haiku), `resume` (agent ID), `run_in_background` (bool), `max_turns` (int), `isolation` ("worktree") |
| **TaskOutput** | Read task output | `task_id` (string), `block` (bool), `timeout` (ms) |
| **TaskStop** | Stop background task | `task_id` (string) |
| **AskUserQuestion** | Interactive Q&A | `questions` (array of {question, header, options[], multiSelect}) |
| **Skill** | Execute a skill | `skill` (string), `args` (string) |
| **WebFetch** | Fetch and summarize URL | `url` (URI), `prompt` (string) |
| **WebSearch** | Search the web | `query` (string), `allowed_domains` (array), `blocked_domains` (array) |
| **NotebookEdit** | Edit Jupyter cells | `notebook_path`, `cell_id`, `new_source`, `cell_type`, `edit_mode` |
| **EnterPlanMode** | Start planning | (no params) |
| **ExitPlanMode** | Submit plan for approval | `allowedPrompts` (array of {tool, prompt}) |
| **ToolSearch** | Fetch deferred tool schemas | `query` (string), `max_results` (number) |

### 3.2 Additional Tools (context-dependent)

| Tool | Purpose |
|------|---------|
| **SendMessage** | Send message to teammates in swarm mode |
| **EnterWorktree** | Create isolated git worktree |
| **ExitWorktree** | Leave worktree |
| **Computer** | Computer use (screenshots, clicks) |
| **LSP** | Language Server Protocol integration |
| **Sleep** | Explicit sleep with justification |
| **CronCreate** | Create scheduled tasks |
| **Config** | Modify Claude Code settings |
| **TeammateTool** | Create/manage teammate agents |
| **TeamDelete** | Remove teammate |
| **TaskCreate/TaskList** | Persistent task management |

### 3.3 How File Editing Works

**Edit is string-replacement based, NOT diff-based.** The tool requires:
1. An `old_string` that must be UNIQUE in the file (or use `replace_all`)
2. A `new_string` to replace it with
3. The model MUST have Read the file first (enforced by the harness)

The uniqueness constraint is critical: if `old_string` appears multiple times, the edit fails. The model is instructed to provide more surrounding context to make it unique.

This design was chosen over diff-based editing because:
- It's more robust to line number drift
- It forces the model to read and understand the surrounding context
- It prevents the model from making changes to code it hasn't seen

### 3.4 How Bash Execution Works

- Commands execute with the user's shell profile
- Working directory persists between commands; shell state does not
- Default timeout: 120 seconds (max 10 minutes)
- Output truncated at 30,000 characters
- Sandboxed by default (can be disabled with `dangerouslyDisableSandbox`)
- Background execution supported via `run_in_background`
- A `description` parameter is required for user-facing clarity

**Sandbox details:**
- Default to sandbox mode for all commands
- Network failures, access denied, operation not permitted are sandbox evidence
- User can be prompted to adjust sandbox settings
- Mandatory sandbox mode exists for stricter environments

### 3.5 Tool Orchestration

`toolOrchestration.ts` partitions tool calls into serial and concurrent batches based on tool metadata. `toolExecution.ts` handles:
- Permission checks
- Hook execution around tool use (pre/post)
- Telemetry and tracing
- Result conversion into internal messages
- MCP-specific tool invocation

Tools have typed metadata: `read-only`, `destructive`, `concurrency-safe`. This enables intelligent batching.

---

## 4. Context Management Strategies

### 4.1 The Context Pressure Pipeline

Claude Code applies **progressively stronger** context reduction strategies. This is the single most important architectural difference from simpler agents:

```
Stage 1: Tool Result Budgeting
  -> Trim oversized tool payloads before the next request

Stage 2: History Snip
  -> Targeted history trimming for low-value older context

Stage 3: Microcompact
  -> Lightweight summarization before the provider call

Stage 4: Context Collapse
  -> Replace detail with projected repo/commit views (feature-gated)

Stage 5: Autocompact
  -> Full summary compaction when token thresholds are crossed

Stage 6: Provider Call
  -> Most turns complete here

REACTIVE (if provider rejects):
Stage 7: Post-Compact Restore
  -> Reinject critical files, plans, skills, agent context
  -> Context collapse can drain staged collapses after overflow
  -> Reactive compact can retry with reduced window
```

**These layers compose.** A single turn may pass through budgeting, snip, microcompact, AND collapse before autocompact ever triggers.

### 4.2 Compaction (Full and Partial)

When compaction triggers, the system generates a structured summary. The prompt for this is detailed (from `system-prompt-context-compaction-summary.md`):

```
Write a continuation summary that will allow you to resume work efficiently.
Include:
1. Task Overview (core request, success criteria, constraints)
2. Current State (what's completed, files modified, artifacts produced)
3. Important Discoveries (constraints, decisions, errors, failed approaches)
4. Next Steps (specific actions, blockers, priority order)
5. Context to Preserve (user preferences, domain details, promises made)
```

For partial compaction (user-triggered), the summary is even more thorough:
```
1. Primary Request and Intent
2. Key Technical Concepts
3. Files and Code Sections (with full code snippets)
4. Errors and fixes
5. Problem Solving
6. All user messages (verbatim, non-tool)
7. Pending Tasks
8. Work Completed
9. Context for Continuing Work
```

### 4.3 Post-Compact Restoration

After compaction, the runtime reinjects:
- Critical files (recently modified/referenced)
- Active plans
- Active skills
- Async agent context
- Team/teammate state

This prevents compaction from severing the agent's connection to its work.

### 4.4 Memory System

Claude Code has a multi-layered memory system:

1. **CLAUDE.md files** -- Project-specific instructions, checked into repos
2. **Memory directory** (`~/.claude/memory/`) -- Persistent cross-session memories
3. **Session memory** -- Per-session extracted learnings
4. **Team memory** -- Shared across teammate agents
5. **Dream consolidation** -- A reflective pass that merges recent signal into durable topic files

The memory system explicitly avoids bloat:
- Index files stay under 25KB
- Each index entry is one line under ~150 characters
- Contradicted facts are deleted at the source
- Relative dates are converted to absolute dates

### 4.5 Relevant Memory Surfacing

Memory is NOT loaded statically at session start. `findRelevantMemories.ts` surfaces memory files **per-turn** based on the current query context. This means memory stays relevant without polluting every turn with everything ever remembered.

---

## 5. Error Recovery Patterns

### 5.1 Provider-Level Recovery

The query loop handles these automatically:
- **Prompt too long**: triggers compaction, retries with reduced context
- **Max output reached**: recovery counters track retries, adjusts output caps
- **Media overflow**: removes problematic content, retries
- **Fallback model**: seamlessly switches to a backup model if primary fails
- **Rate limiting**: retry with backoff (handled at API layer)

### 5.2 Tool-Level Recovery

- Tool timeouts (120s default, 600s max) produce error results that go back to the model
- Tool permission denials are tracked and reported
- Hook failures can block tool execution (the model is told to adapt)
- Sandbox failures produce specific evidence the model can reason about

### 5.3 Session-Level Recovery

- Transcripts are persisted BEFORE API calls (resume safety)
- Orphaned tool calls are sealed on resume
- File history snapshots enable rewind
- Session metadata enables search and hydration

### 5.4 Self-Correction Patterns

The system prompt doesn't explicitly say "if you're stuck, try X." Instead, self-correction emerges from:

1. **TodoWrite as a progress anchor** -- The model tracks its own progress and can see when tasks are incomplete
2. **Read-before-edit enforcement** -- Prevents changes to unseen code
3. **Test-after-change convention** -- Worker instructions say "run tests, if they fail, fix them"
4. **Verification specialist** -- A dedicated adversarial subagent that catches the model's natural tendency to skip verification
5. **The "simplify" skill** -- Automatically invoked after implementation to review and clean up changes

---

## 6. Multi-Agent Patterns

### 6.1 Subagent Types

Claude Code has a rich taxonomy of subagents:

| Type | Model | Tools | Purpose |
|------|-------|-------|---------|
| **Explore** | Haiku | Read-only (Glob, Grep, Read, Bash read-only) | Fast codebase exploration |
| **general-purpose** | Inherit | All tools (*) | Research and multi-step tasks |
| **Plan** | Inherit | Read-only | Design implementation plans |
| **Bash** | Inherit | Bash only | Command execution |
| **fork** | Inherit | All tools (*) | Context-inheriting clone of parent |
| **Verification** | Inherit | Bash, WebFetch, browser tools | Adversarial testing |
| **Worker** | Inherit | All tools (*) | Implementation in worktrees |

### 6.2 Fork vs. Fresh Subagent

This is a crucial distinction:

**Fork (omit `subagent_type`):**
- Inherits full conversation context
- Shares the parent's prompt cache (huge cost savings)
- Prompt is a directive ("what to do"), not a briefing ("what the situation is")
- Best for research and implementation that needs context
- Don't set `model` on a fork (breaks cache sharing)

**Fresh subagent (specify `subagent_type`):**
- Starts with zero context
- Brief it like "a smart colleague who just walked into the room"
- Explain what, why, what you've learned, what you've ruled out
- Best for independent, self-contained tasks

### 6.3 Subagent Prompt Writing Guidelines

From `system-prompt-writing-subagent-prompts.md`:

> "Brief the agent like a smart colleague who just walked into the room -- it hasn't seen this conversation, doesn't know what you've tried, doesn't understand why this task matters."

> "**Never delegate understanding.** Don't write 'based on your findings, fix the bug.' Write prompts that prove you understood: include file paths, line numbers, what specifically to change."

### 6.4 Fork Usage Rules

- "Don't peek" -- Don't read the fork's output file mid-flight. Trust the completion notification.
- "Don't race" -- Never fabricate or predict fork results. If the user asks before it's done, say it's still running.
- Forks are cheap because they share the prompt cache.
- Launch parallel forks in one message for independent questions.

### 6.5 Teammate/Swarm Communication

For multi-agent teams:
- `SendMessage` tool with `to: "<name>"` for directed messages
- `to: "*"` for broadcasts (used sparingly)
- Regular text output is NOT visible to teammates
- Work is coordinated through task system and messaging

### 6.6 Worker Fork Execution

Workers are forked with strict rules:
```
1. Do NOT spawn sub-agents (you ARE the fork)
2. Do NOT converse or ask questions
3. USE tools directly
4. Commit changes before reporting
5. Stay within your directive's scope
6. Keep report under 500 words
7. Response MUST begin with "Scope:"
```

Output format:
```
Scope: <one sentence>
Result: <key findings>
Key files: <paths>
Files changed: <with commit hash>
Issues: <if any>
```

### 6.7 Worktree Isolation

Subagents can run in `isolation: "worktree"` mode:
- Creates a temporary git worktree
- Agent works on an isolated copy of the repo
- Worktree auto-cleaned if no changes
- If changes were made, worktree path and branch are returned

---

## 7. Key Insights for SaltAgent

### 7.1 What Makes Claude Code GOOD

It's not the prompts. It's not the model. It's the **integration of runtime concerns into the turn loop**:

1. **Context assembly is the product.** Every turn gets curated context: files, memory, plans, IDE state, MCP deltas, agent state. The model never operates in a vacuum.

2. **Compaction is a first-class concern.** Long sessions don't degrade because context pressure is managed at 6+ layers, from budgeting through reactive recovery. This is the biggest gap in simpler agents.

3. **Persistence enables continuity.** Transcripts are saved before API calls. File history is snapshotted. Sessions can be resumed, rewound, searched. This makes the agent feel reliable.

4. **Tools are a platform, not callbacks.** Typed contracts, concurrency semantics, permissions, hook points, progress channels, structured result storage. This enables intelligent batching and policy enforcement.

5. **The model is one subsystem inside an operating environment.** The prompt says it best: "The app is a terminal-native operating environment for model-driven software work, and the assistant is one subsystem inside that environment rather than the whole product."

### 7.2 Specific Patterns Worth Adopting

1. **Edit via string replacement, not line numbers.** Forces the model to read context, survives line drift, prevents blind edits.

2. **Streaming tool execution.** Start tools before the model finishes generating. Major latency win.

3. **TodoWrite for self-tracking.** The model tracks its own progress explicitly. This creates a feedback loop that prevents task amnesia.

4. **Read-before-edit enforcement.** The tool literally refuses to edit a file the model hasn't read. Simple, effective.

5. **Subagent prompt guidelines.** "Never delegate understanding" -- require the parent to synthesize before delegating. This prevents shallow work.

6. **Verification specialist.** A dedicated adversarial agent that explicitly acknowledges its own tendencies to skip verification. The self-awareness prompt is remarkable:
   > "You are Claude, and you are bad at verification. You read code and write PASS instead of running it."

7. **Compaction preserves work state.** Post-compact restoration reinjects critical files, plans, and agent context. Compaction isn't information loss.

8. **Memory is per-turn, not per-session.** Relevant memories are surfaced based on the current query, not loaded at startup.

9. **Hooks as a policy layer.** PreToolUse, PostToolUse, PermissionRequest hooks enable external systems to intercept, block, or augment any tool execution.

10. **Security monitor for autonomous mode.** A separate classifier evaluates every autonomous action against block/allow rules, protecting against prompt injection, scope creep, and accidental damage.

### 7.3 What NOT to Copy

1. **The giant SCC.** 1,435 files in one strongly connected component. Integration is good; coupling this tight is a maintenance risk.
2. **Feature flag complexity.** Three-layer gating (build-time, runtime GrowthBook, settings) is overkill for SaltAgent.
3. **5,000-line orchestration files.** Keep modules focused.

---

## 8. Recommended SaltAgent Architecture

Based on everything learned from Claude Code, KODE SDK, and learn-claude-code, here is the recommended architecture for SaltAgent.

### 8.1 Design Principles

1. **Own the engine.** Use the Anthropic SDK directly. The loop is trivial. The value is in what surrounds it.
2. **Context assembly is the product.** Invest heavily in curating what the model sees each turn.
3. **Compaction is not optional.** Build it from day one, not as an afterthought.
4. **Tools are typed platform entities.** Not ad-hoc functions.
5. **Persistence enables reliability.** Save state before API calls. Support resume.
6. **Subagents are cheap forks.** Share the prompt cache. Delegate with context.

### 8.2 Core Architecture

```
SaltAgent
  |
  +-- AgentLoop (query loop with streaming tool execution)
  |     |-- ContextAssembler (files, memory, component state, build output)
  |     |-- ContextPressureManager (budgeting, microcompact, autocompact)
  |     |-- StreamingToolExecutor (parallel tool execution during model streaming)
  |     |-- ErrorRecovery (prompt-too-long, timeout, fallback)
  |     +-- TurnPersistence (save before API call, resume on crash)
  |
  +-- ToolRegistry
  |     |-- BashTool (sandboxed, timeout, background)
  |     |-- ReadTool (file read with offset/limit)
  |     |-- EditTool (string replacement, requires prior read)
  |     |-- WriteTool (create/overwrite, requires prior read for existing)
  |     |-- GlobTool (fast pattern matching)
  |     |-- GrepTool (ripgrep-based search)
  |     |-- TodoTool (self-tracking task list)
  |     +-- ComponentTools (Salt Desktop specific: build, test, deploy, preview)
  |
  +-- SubagentManager
  |     |-- Fork (context-inheriting, cache-sharing)
  |     |-- FreshAgent (zero-context specialist: explore, plan, verify)
  |     |-- WorktreeIsolation (git worktree per agent)
  |     +-- AgentCommunication (message passing between agents)
  |
  +-- ContextManager
  |     |-- MemorySystem (project memory, session memory, cross-session)
  |     |-- CompactionStack (6-layer progressive reduction)
  |     |-- PostCompactRestore (reinject critical state after compaction)
  |     +-- RelevantMemorySurfacing (per-turn, query-based)
  |
  +-- EventBus (three-channel: progress, control, monitor)
  |     |-- Progress: text_chunk, tool_start, tool_end, done
  |     |-- Control: permission_required, permission_decided
  |     +-- Monitor: state_changed, error, token_usage, compaction
  |
  +-- HookEngine
  |     |-- PreToolUse / PostToolUse
  |     |-- PermissionRequest
  |     |-- Stop / SessionStart
  |     +-- PreCompact / PostCompact
  |
  +-- SessionPersistence
        |-- TranscriptStorage (save before API call)
        |-- FileHistory (snapshot modified files)
        |-- Resume (hydrate from saved state)
        +-- Search (find past sessions by content)
```

### 8.3 The Agent Loop (Python)

```python
class SaltAgent:
    async def run(self, prompt: str) -> AgentResult:
        messages = self.context_assembler.build_messages(prompt)
        
        while True:
            # Context pressure management
            messages = self.pressure_manager.reduce(messages)
            
            # Persist before API call (crash safety)
            await self.persistence.save_checkpoint(messages)
            
            # Stream from model
            response = await self.client.messages.create(
                model=self.model,
                system=self.context_assembler.system_prompt(),
                messages=messages,
                tools=self.tool_registry.schemas(),
                max_tokens=self.max_tokens,
                stream=True,
            )
            
            # Process streamed response
            assistant_message, tool_calls = await self.process_stream(response)
            messages.append(assistant_message)
            
            # Emit progress events
            self.event_bus.emit("progress", assistant_message)
            
            if not tool_calls:
                return AgentResult(messages=messages, final=assistant_message)
            
            # Execute tools (streaming: start as soon as detected)
            tool_results = await self.tool_executor.run_batch(tool_calls)
            messages.append({"role": "user", "content": tool_results})
            
            # Post-tool hooks
            for result in tool_results:
                await self.hooks.run("PostToolUse", result)
```

### 8.4 Context Assembly for Salt Desktop

Salt Desktop has unique context needs beyond generic coding:

```python
class SaltContextAssembler:
    def build_context(self, prompt: str) -> list:
        attachments = []
        
        # Component state (what's being built)
        attachments += self.get_component_state()
        
        # Build output (last test/build results)
        attachments += self.get_build_state()
        
        # Project memory (CLAUDE.md equivalent)
        attachments += self.get_project_instructions()
        
        # Relevant memories (query-based, not all)
        attachments += self.find_relevant_memories(prompt)
        
        # File context (recently modified, currently open)
        attachments += self.get_file_context()
        
        # Graph context (component dependencies, connections)
        attachments += self.get_graph_context()
        
        return attachments
```

### 8.5 Compaction Strategy

Adopt Claude Code's 6-layer approach, simplified for v1:

| Layer | When | What |
|-------|------|------|
| **Tool result budgeting** | Every turn | Trim tool outputs > 10KB to summary + key lines |
| **History snip** | Token count > 60% | Remove oldest assistant+tool turns (keep user messages) |
| **Microcompact** | Token count > 75% | Summarize old tool results in-place |
| **Autocompact** | Token count > 85% | Full summary generation, post-compact restore |
| **Reactive compact** | Provider rejects | Emergency compaction with retry |
| **Post-compact restore** | After any compact | Reinject: current component state, active plan, build output |

### 8.6 Key Differences from Claude Code

SaltAgent is purpose-built for Salt Desktop's component workflow, not general coding:

| Aspect | Claude Code | SaltAgent |
|--------|------------|-----------|
| Scope | General software engineering | Component building for Salt Desktop |
| Input | User prompt in terminal | Component spec + user prompt |
| Context | Arbitrary codebase | Component graph, build state, test output |
| Output | Code changes + terminal output | Component artifacts + event stream |
| Success criteria | User says it's done | Tests pass, build succeeds, component renders |
| Verification | Optional adversarial agent | Built-in test-verify loop |
| Persistence | File-based session storage | Event stream to Swift frontend |

### 8.7 Implementation Priority

1. **Week 1: Core loop + tools.** Agent loop with streaming, Bash/Read/Edit/Write/Glob/Grep tools, basic error recovery. This gets a working agent.
2. **Week 1: Event bus.** Three-channel events so the Swift frontend can display progress.
3. **Week 2: Context assembly.** Component state, build output, project memory injection.
4. **Week 2: Compaction.** Tool result budgeting + autocompact + post-compact restore.
5. **Week 3: Subagents.** Fork with context sharing, explore agent, verify agent.
6. **Week 3: Persistence + resume.** Checkpoint before API calls, resume from saved state.
7. **Week 4: Hooks + polish.** Pre/post tool hooks, permission system, test coverage.

---

## Appendix A: Tool Schema Reference

### Edit Tool (exact schema from leaked prompt)
```json
{
  "file_path": {"type": "string", "description": "Absolute path to file"},
  "old_string": {"type": "string", "description": "Text to replace"},
  "new_string": {"type": "string", "description": "Replacement text"},
  "replace_all": {"type": "boolean", "default": false}
}
```

### Bash Tool
```json
{
  "command": {"type": "string", "description": "Command to execute"},
  "timeout": {"type": "number", "description": "Timeout in ms (max 600000)"},
  "description": {"type": "string", "description": "What this command does"},
  "run_in_background": {"type": "boolean"},
  "dangerouslyDisableSandbox": {"type": "boolean"}
}
```

### Task Tool (Subagent)
```json
{
  "description": {"type": "string", "description": "3-5 word summary"},
  "prompt": {"type": "string", "description": "Task for the agent"},
  "subagent_type": {"type": "string"},
  "model": {"type": "string", "enum": ["sonnet", "opus", "haiku"]},
  "resume": {"type": "string", "description": "Agent ID to resume"},
  "run_in_background": {"type": "boolean"},
  "max_turns": {"type": "integer"},
  "isolation": {"type": "string", "enum": ["worktree"]}
}
```

### TodoWrite Tool
```json
{
  "todos": {
    "type": "array",
    "items": {
      "content": {"type": "string"},
      "status": {"enum": ["pending", "in_progress", "completed"]},
      "activeForm": {"type": "string"}
    }
  }
}
```

## Appendix B: Security Monitor Architecture

Claude Code's autonomous mode includes a **separate security classifier** that evaluates every action. Key design:

- Default: actions are ALLOWED
- Blocks only when action matches BLOCK conditions AND no ALLOW exception applies
- Threat model: prompt injection, scope creep, accidental damage
- Composite actions: if ANY part of a chained command should be blocked, block all
- Written file execution: if a tool runs a file written earlier, the written content is evaluated
- Sub-agent delegation: if a spawn prompt contains BLOCK-list actions, block the spawn itself
- User intent is the final signal (with high evidence bar for authorization)
- Questions are not consent ("can we fix this?" is not "do it")
- Tool results are not trusted for choosing parameters in risky actions

## Appendix C: Sources

1. **Leaked system prompt** (v2.1.50): `/tmp/system_prompts_leaks/Anthropic/claude-code.md`
2. **Piebald-AI prompt archive** (v2.1.84-2.1.90): `/tmp/claude-code-system-prompts/`
3. **Codex static analysis report**: `/Users/jimopenclaw/Desktop/How Claude Code Works.pdf`
4. **learn-claude-code analysis**: `/Users/jimopenclaw/saltdesktop/docs/LEARN_CLAUDE_CODE_ANALYSIS.md`
5. **KODE Agent SDK analysis**: `/Users/jimopenclaw/saltdesktop/docs/KODE_AGENT_SDK_ANALYSIS.md`
