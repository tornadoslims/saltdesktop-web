# Claude Code System Prompt Analysis

Analysis of all 254 system prompts from Claude Code (ccVersion ~2.1.90), categorized and evaluated for integration into SaltAgent.

## Summary

- **Total prompts analyzed**: 254
- **Integrated as curated prompts**: 14 (directly usable mode prompts in `salt_agent/prompts/`)
- **Integrated in raw catalog**: 254 (all prompts available in subpackages: `fragments/`, `agents/`, `skills/`, `tools/`, `data/`)
- **Skipped for curated set**: 240 (too specific, IDE-dependent, or already covered by catalog)

---

## Category 1: Agent Prompts (34 files)

Role-specific prompts for subagent personalities and behaviors.

| File | Description | Curated? | Notes |
|------|-------------|----------|-------|
| `agent-prompt-explore.md` | Codebase exploration specialist (read-only) | **Yes** → `explore.py` | Core mode. Adapted tool names, removed template vars. |
| `agent-prompt-verification-specialist.md` | Adversarial testing with mandatory probes | **Yes** → `verification.py` | Most valuable prompt. Self-awareness about LLM verification failures is gold. |
| `agent-prompt-worker-fork-execution.md` | Focused task execution with structured output | **Yes** → `worker.py` | Stripped boilerplate tags, kept the 10 rules and output format. |
| `agent-prompt-general-purpose.md` | Multi-purpose search/analyze/edit agent | **Yes** → `general_purpose.py` | Expanded from the template-variable version. |
| `agent-prompt-plan-mode-enhanced.md` | Software architect planning specialist | **Yes** → `plan_mode.py` | Combined with 5-phase plan mode and phase-4 instructions. |
| `agent-prompt-conversation-summarization.md` | Full conversation summarization | **Yes** → `summarization.py` | Merged with context compaction and partial compaction prompts. |
| `agent-prompt-dream-memory-consolidation.md` | 4-phase memory consolidation | **Yes** → `memory.py` | Combined with session memory update and memory description prompts. |
| `agent-prompt-security-monitor-*-first-part.md` | Security classifier (threat model, rules) | **Yes** → `security.py` | Combined both parts. Condensed BLOCK/ALLOW rules. |
| `agent-prompt-security-monitor-*-second-part.md` | Security classifier (BLOCK/ALLOW lists) | **Yes** → `security.py` | Merged into single prompt. |
| `agent-prompt-quick-git-commit.md` | Git commit creation | **Yes** → `commit.py` | Stripped template vars, kept safety protocol. |
| `agent-prompt-quick-pr-creation.md` | PR creation workflow | **Yes** → `pr_creation.py` | Simplified from template-heavy original. |
| `agent-prompt-review-pr-slash-command.md` | Code review | **Yes** → `code_review.py` | Clean adaptation, minimal changes needed. |
| `agent-prompt-webfetch-summarizer.md` | Web content summarization | **Yes** → `webfetch.py` | Removed trusted/untrusted domain branching. |
| `agent-prompt-recent-message-summarization.md` | Partial conversation summarization | Covered | Merged into `summarization.py`. |
| `agent-prompt-session-memory-update-instructions.md` | Session memory file updates | Covered | Key patterns merged into `memory.py`. |
| `agent-prompt-agent-creation-architect.md` | Creates custom agent configurations | Catalog only | Too meta — agent that creates agents. |
| `agent-prompt-agent-hook.md` | Verifies stop conditions in agent runs | Catalog only | Claude Code-specific hook system. |
| `agent-prompt-auto-mode-rule-reviewer.md` | Reviews auto-mode classifier rules | Catalog only | Claude Code auto-mode specific. |
| `agent-prompt-bash-command-description-writer.md` | Generates command descriptions | Catalog only | Utility for Claude Code's UI. |
| `agent-prompt-bash-command-prefix-detection.md` | Risk classification for bash commands | Catalog only | Claude Code permission system. |
| `agent-prompt-batch-slash-command.md` | Orchestrates parallelizable batch changes | Catalog only | Complex orchestration, could be useful later. |
| `agent-prompt-claude-guide-agent.md` | Helps users understand Claude Code | Skip | Claude Code documentation-specific. |
| `agent-prompt-claudemd-creation.md` | Creates CLAUDE.md files | Catalog only | Could be useful as a "project setup" prompt. |
| `agent-prompt-coding-session-title-generator.md` | Generates session titles | Catalog only | UI utility. |
| `agent-prompt-determine-which-memory-files-to-attach.md` | Selects relevant memories for queries | Catalog only | Memory retrieval logic. |
| `agent-prompt-hook-condition-evaluator.md` | Evaluates hook conditions | Skip | Claude Code hook system. |
| `agent-prompt-prompt-suggestion-generator-v2.md` | Suggests next user prompts | Skip | Claude Code UI feature. |
| `agent-prompt-schedule-slash-command.md` | Manages scheduled remote agents | Catalog only | Cloud scheduling specific. |
| `agent-prompt-security-review-slash-command.md` | Comprehensive security code review | Catalog only | Very detailed, specialized. Available in catalog. |
| `agent-prompt-session-search-assistant.md` | Finds relevant past sessions | Catalog only | Session management. |
| `agent-prompt-session-title-and-branch-generation.md` | Session titles + branch names | Catalog only | UI utility. |
| `agent-prompt-status-line-setup.md` | Configures status line display | Skip | Claude Code UI. |

---

## Category 2: System Prompt Fragments (107 files)

Behavioral instructions that compose the main system prompt.

### Doing Tasks (11 files) — ALL INTEGRATED into `system_prompt.py`

| File | Key Insight | Integrated? |
|------|-------------|-------------|
| `doing-tasks-software-engineering-focus.md` | Interpret instructions as software engineering tasks | **Yes** |
| `doing-tasks-read-before-modifying.md` | Read and understand code before editing | **Yes** |
| `doing-tasks-no-unnecessary-additions.md` | Don't add features beyond what was asked | **Yes** |
| `doing-tasks-no-premature-abstractions.md` | Three lines > premature abstraction | **Yes** |
| `doing-tasks-no-unnecessary-error-handling.md` | Only validate at system boundaries | **Yes** |
| `doing-tasks-no-compatibility-hacks.md` | Delete unused code, no shims | **Yes** |
| `doing-tasks-minimize-file-creation.md` | Prefer editing over creating files | **Yes** |
| `doing-tasks-security.md` | Avoid OWASP top 10 vulnerabilities | **Yes** |
| `doing-tasks-no-time-estimates.md` | Don't estimate task duration | **Yes** |
| `doing-tasks-ambitious-tasks.md` | Allow users to attempt complex tasks | **Yes** |
| `doing-tasks-help-and-feedback.md` | Help/feedback channel info | Skipped (Claude Code specific) |

### Tone and Style (2 files) — INTEGRATED into `system_prompt.py`

| File | Key Insight |
|------|-------------|
| `tone-and-style-concise-output-short.md` | "Your responses should be short and concise." |
| `tone-and-style-code-references.md` | Include file_path:line_number in code references. |

### Output Efficiency (1 file) — INTEGRATED into `system_prompt.py`

| File | Key Insight |
|------|-------------|
| `output-efficiency.md` | Lead with answers, not reasoning. Focus on decisions/status/errors. |

### Executing Actions (1 file) — INTEGRATED into `system_prompt.py`

| File | Key Insight |
|------|-------------|
| `executing-actions-with-care.md` | Consider reversibility/blast radius. Confirm risky actions. |

### Auto Mode (1 file) — INTEGRATED into `build_mode.py`

| File | Key Insight |
|------|-------------|
| `auto-mode.md` | Execute immediately, minimize interruptions, prefer action. |

### Worker Instructions (1 file) — INTEGRATED into `build_mode.py`

| File | Key Insight |
|------|-------------|
| `worker-instructions.md` | Simplify, run tests, verify e2e, commit and push, report. |

### Context/Compaction (3 files) — INTEGRATED into `summarization.py`

| File | Key Insight |
|------|-------------|
| `context-compaction-summary.md` | 5-section continuation summary format. |
| `partial-compaction-instructions.md` | 9-section detailed summary for partial compaction. |
| `agent-thread-notes.md` | Absolute paths, no emojis, no colon before tool calls. |

### Memory (3 files) — INTEGRATED into `memory.py`

| File | Key Insight |
|------|-------------|
| `agent-memory-instructions.md` | Domain-specific memory instructions per agent type. |
| `description-part-of-memory-instructions.md` | User memories: role, goals, preferences. |
| `memory-description-of-user-feedback.md` | Record from both failure AND success. |

### Fork/Subagent (3 files) — CONCEPTS integrated, prompts in catalog

| File | Key Insight |
|------|-------------|
| `fork-usage-guidelines.md` | Don't peek at fork output mid-flight. Don't fabricate results. |
| `writing-subagent-prompts.md` | Brief like a smart colleague. Never delegate understanding. |
| `subagent-delegation-examples.md` | Example delegation patterns. |

### Plan Mode (2 files) — INTEGRATED into `plan_mode.py`

| File | Key Insight |
|------|-------------|
| `phase-four-of-plan-mode.md` | 40-line hard limit. No prose. File paths with changes. |
| `remote-plan-mode-ultraplan.md` | Diagram-rich plans with mermaid. Explore before planning. |

### Other System Prompts (15+ files) — Catalog only or Skipped

| File | Status | Reason |
|------|--------|--------|
| `buddy-mode.md` | Skip | Personality companion, not relevant |
| `chrome-browser-mcp-tools.md` | Skip | Browser automation specific |
| `claude-in-chrome-browser-automation.md` | Skip | Browser automation |
| `git-status.md` | Catalog | Git status display format |
| `hooks-configuration.md` | Skip | Claude Code hooks system |
| `how-to-use-the-sendusermessage-tool.md` | Skip | Claude Code tool specific |
| `insights-*.md` (5 files) | Skip | Claude Code analytics |
| `learning-mode*.md` (2 files) | Skip | Claude Code learning mode |
| `mcp-tool-result-truncation.md` | Catalog | Useful truncation patterns |
| `minimal-mode.md` | Skip | Claude Code feature flag |
| `option-previewer.md` | Skip | UI preview feature |
| `scratchpad-directory.md` | Catalog | Temp directory patterns |
| `skillify-current-session.md` | Skip | Claude Code skill creation |
| `censoring-assistance-with-malicious-activities.md` | Catalog | Security filtering |
| `teammate-communication.md` | Skip | Claude Code teams feature |
| `team-memory-content-display.md` | Skip | Claude Code teams feature |

---

## Category 3: System Reminders (35 files)

Short contextual messages injected during specific states.

| Pattern | Count | Status | Reason |
|---------|-------|--------|--------|
| `plan-mode-is-active-*.md` (3) | 3 | Key concepts in `plan_mode.py` | 5-phase, iterative, subagent variants |
| `hook-*.md` (4) | 4 | Skip | Claude Code hook system |
| `file-*.md` (4) | 4 | Skip | IDE integration |
| `memory-*.md` (2) | 2 | Concepts in `memory.py` | Memory file display |
| `team-*.md` (2) | 2 | Skip | Claude Code teams |
| Others (20) | 20 | Skip | State notifications, UI reminders |

---

## Category 4: Tool Descriptions (74 files)

Detailed usage instructions for each tool.

| Group | Count | Status | Notes |
|-------|-------|--------|-------|
| `bash-*.md` (30+) | 30+ | Catalog | Bash usage rules: sandboxing, git, parallel, sleep |
| `edit.md` | 1 | Key concepts in `system_prompt.py` | Edit tool usage patterns |
| `readfile.md` | 1 | Key concepts in `system_prompt.py` | Read before edit |
| `write.md` | 1 | Key concepts in `system_prompt.py` | Prefer edit over write |
| `grep.md` | 1 | Key concepts in `system_prompt.py` | Regex search patterns |
| `agent-*.md` (3) | 3 | Catalog | When to launch subagents |
| `computer.md` | 1 | Skip | Computer use / screenshot tool |
| `webfetch.md` / `websearch.md` | 2 | Catalog | Web tools |
| IDE-specific (10+) | 10+ | Skip | LSP, notebook, config, sleep |

---

## Category 5: Skills (15 files)

Complex multi-step workflows.

| File | Status | Notes |
|------|--------|-------|
| `skill-debugging.md` | Catalog | Debugging methodology |
| `skill-simplify.md` | Catalog | Code simplification review |
| `skill-agent-design-patterns.md` | Catalog | Agent architecture patterns |
| `skill-verify-skill.md` | Catalog | Verification workflow |
| `skill-build-with-claude-api*.md` (2) | Catalog | API usage patterns |
| `skill-computer-use-mcp.md` | Skip | Computer use specific |
| `skill-create-verifier-skills.md` | Catalog | Verifier creation |
| `skill-init-claudemd-*.md` | Skip | Claude Code setup |
| `skill-loop-slash-command.md` | Catalog | Recurring task execution |
| `skill-stuck-slash-command.md` | Catalog | Getting unstuck methodology |
| `skill-update-*.md` (3) | Skip | Claude Code config |

---

## Category 6: Data/Reference (27 files)

API references, SDK patterns, and documentation data.

| Group | Count | Status | Notes |
|-------|-------|--------|-------|
| `data-claude-api-reference-*.md` (8) | 8 | Catalog | API refs for 8 languages |
| `data-agent-sdk-*.md` (4) | 4 | Catalog | Python + TypeScript SDK patterns/refs |
| `data-files-api-reference-*.md` (2) | 2 | Catalog | Files API |
| `data-streaming-reference-*.md` (2) | 2 | Catalog | Streaming APIs |
| `data-tool-use-*.md` (3) | 3 | Catalog | Tool use patterns |
| `data-message-batches-*.md` (1) | 1 | Catalog | Batch API |
| `data-prompt-caching-*.md` (1) | 1 | Catalog | Prompt caching |
| `data-http-error-codes-*.md` (1) | 1 | Catalog | Error codes |
| `data-github-*.md` (2) | 2 | Skip | GitHub Actions/App specific |
| `data-live-documentation-sources.md` (1) | 1 | Skip | Claude Code doc URLs |
| `data-session-memory-template.md` (1) | 1 | Catalog | Memory file template |
| `data-claude-model-catalog.md` (1) | 1 | Catalog | Model names and capabilities |

---

## Curated Prompts Summary

14 curated prompts created at `/Users/jimopenclaw/saltdesktop/salt_agent/prompts/`:

| # | File | Mode Key | Chars | Source Prompts Merged |
|---|------|----------|-------|---------------------|
| 1 | `system_prompt.py` | `default` | 4,485 | 12 doing-tasks fragments + tone/style + output efficiency + executing-actions |
| 2 | `plan_mode.py` | `plan` | 2,029 | plan-mode-enhanced + 5-phase plan + phase-4 + ultraplan concepts |
| 3 | `build_mode.py` | `build` | 1,889 | worker-instructions + auto-mode + doing-tasks rules |
| 4 | `verification.py` | `verify` | 3,692 | verification-specialist (nearly verbatim — it's that good) |
| 5 | `explore.py` | `explore` | 2,005 | explore subagent |
| 6 | `summarization.py` | `summarize` | 2,196 | conversation-summarization + context-compaction + partial-compaction |
| 7 | `memory.py` | `memory` | 2,660 | dream-memory-consolidation + session-memory-update + memory descriptions |
| 8 | `security.py` | `security` | 3,787 | security-monitor parts 1 + 2 (condensed BLOCK/ALLOW) |
| 9 | `worker.py` | `worker` | 1,064 | worker-fork-execution |
| 10 | `general_purpose.py` | `general` | 1,337 | general-purpose subagent |
| 11 | `commit.py` | `commit` | 1,150 | quick-git-commit |
| 12 | `pr_creation.py` | `pr` | 1,074 | quick-pr-creation |
| 13 | `code_review.py` | `review` | 1,142 | review-pr-slash-command |
| 14 | `webfetch.py` | `webfetch` | 687 | webfetch-summarizer |

## Key Design Decisions

1. **Verification prompt kept nearly verbatim** — The self-awareness section ("You are bad at verification") and rationalization-recognition are uniquely valuable. This is the most important behavioral prompt in the collection.

2. **System prompt synthesized from 12+ fragments** — Rather than importing fragments individually, the core behavioral rules are baked into one coherent prompt. This is what gets sent every turn, so it needs to be tight.

3. **Security prompt condensed** — The original is 2 files totaling ~8000 words. Condensed to the essential BLOCK/ALLOW rules. The full evaluation rules and edge case handling are available in the catalog.

4. **Memory prompt combines 3 sources** — Dream consolidation (the 4-phase process), session memory updates (what to record), and memory descriptions (how to structure user/feedback memories).

5. **Tool names genericized** — Removed `${GLOB_TOOL_NAME}` template variables. SaltAgent tools are: `bash`, `read`, `write`, `edit`, `glob`, `grep`, `list_files`.

6. **Two systems coexist** — The curated prompts (14 directly usable strings) and the catalog system (254 prompts in subpackages) both export from `__init__.py`. Use `get_mode_prompt()` for curated, `assemble_system_prompt()` for composed.
