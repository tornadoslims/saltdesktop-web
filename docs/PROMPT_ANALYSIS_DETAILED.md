# SaltAgent Prompt System — Detailed Analysis

**Generated:** 2026-03-30
**Scope:** 254 prompt files across 5 directories (fragments, agents, skills, tools, data)
**Source:** `/Users/jimopenclaw/saltdesktop/salt_agent/prompts/`

---

## Table of Contents

1. [Fragment Analysis (105 fragments)](#section-1-fragment-analysis)
2. [Agent Prompt Analysis (32 agent prompts)](#section-2-agent-prompt-analysis)
3. [Skill Prompt Analysis (15 skills)](#section-3-skill-prompt-analysis)
4. [Tool Prompt Analysis (75 tool prompts)](#section-4-tool-prompt-analysis)
5. [Data Prompt Analysis (27 data files)](#section-5-data-prompt-analysis)
6. [Cross-Model Compatibility Report](#section-6-cross-model-compatibility-report)
7. [Prompt Optimization Recommendations](#section-7-prompt-optimization-recommendations)
8. [Assembly Guide](#section-8-assembly-guide)

---

## Section 1: Fragment Analysis

Fragments are behavioral instructions injected into the system prompt. They shape how the agent acts, communicates, and uses tools. The assembler (`assembler.py`) includes 13 "core" fragments by default and can selectively include others.

### Group A: Doing Tasks (11 fragments)

#### doing_tasks_software_engineering_focus
- **Purpose:** Ensures the agent interprets instructions in a software engineering context.
- **Key instructions:** (1) Treat ambiguous instructions as code-related. (2) When told to rename something, find and modify it in code, don't just return the renamed string. (3) Consider the current working directory as context.
- **Cross-model compatibility:** Universal. All models benefit from task-framing.
- **Suggested modifications:** GPT-5.x: add "You are a coding assistant" preamble. Gemini: works as-is.

#### doing_tasks_read_before_modifying
- **Purpose:** Prevents blind edits by requiring the agent to read code before proposing changes.
- **Key instructions:** (1) Do not propose changes to unread code. (2) Read files before modifying. (3) Understand existing code first.
- **Cross-model compatibility:** Universal and critical. All models tend to hallucinate code structure.
- **Suggested modifications:** GPT-5.x: reinforce with "IMPORTANT:" prefix. Gemini: works as-is.

#### doing_tasks_no_unnecessary_additions
- **Purpose:** Prevents gold-plating and scope creep.
- **Key instructions:** (1) Don't add features beyond what's asked. (2) Bug fixes don't need surrounding cleanup. (3) Don't add docstrings/comments to unchanged code.
- **Cross-model compatibility:** High. Claude and GPT both tend to over-improve; this counteracts it.
- **Suggested modifications:** Grok: add explicit "stay on task" since Grok's personality can lead to tangents.

#### doing_tasks_no_premature_abstractions
- **Purpose:** Prevents over-engineering with unnecessary helpers and utilities.
- **Key instructions:** (1) Don't create abstractions for one-time operations. (2) Three similar lines beat a premature abstraction. (3) Don't design for hypothetical future requirements.
- **Cross-model compatibility:** High. All models benefit but Claude already tends to follow this well.
- **Suggested modifications:** GPT-5.x: consider adding concrete examples since GPT sometimes interprets abstractly.

#### doing_tasks_no_unnecessary_error_handling
- **Purpose:** Prevents defensive coding where it's not needed.
- **Key instructions:** (1) Don't handle impossible scenarios. (2) Trust internal code guarantees. (3) Only validate at system boundaries.
- **Cross-model compatibility:** Moderate. GPT tends to add try/catch everywhere; needs stronger emphasis there.
- **Suggested modifications:** GPT-5.x: add "Do NOT wrap internal function calls in try/catch blocks."

#### doing_tasks_no_compatibility_hacks
- **Purpose:** Prevents dead-code preservation through shims.
- **Key instructions:** (1) Don't rename unused variables with underscore. (2) Don't re-export removed types. (3) Delete unused code completely.
- **Cross-model compatibility:** High. Universal instruction.
- **Suggested modifications:** None needed.

#### doing_tasks_minimize_file_creation
- **Purpose:** Prevents file bloat.
- **Key instructions:** (1) Don't create files unless necessary. (2) Prefer editing existing files.
- **Cross-model compatibility:** High. GPT-5.x and Claude both tend to create new files when editing would suffice.
- **Suggested modifications:** None needed.

#### doing_tasks_security
- **Purpose:** Prevents introduction of security vulnerabilities.
- **Key instructions:** (1) Avoid command injection, XSS, SQL injection. (2) Follow OWASP top 10. (3) Fix insecure code immediately.
- **Cross-model compatibility:** Universal. All models need this.
- **Suggested modifications:** None needed.

#### doing_tasks_no_time_estimates
- **Purpose:** Prevents unreliable time estimates.
- **Key instructions:** (1) Don't estimate task duration. (2) Focus on what, not how long.
- **Cross-model compatibility:** High. GPT especially tends to give time estimates when asked.
- **Suggested modifications:** None needed.

#### doing_tasks_ambitious_tasks
- **Purpose:** Encourages the agent to tackle large tasks rather than refusing.
- **Key instructions:** (1) Allow users to attempt ambitious tasks. (2) Defer to user judgment on scope.
- **Cross-model compatibility:** High. Gemini tends to be cautious; this counteracts that.
- **Suggested modifications:** Gemini: reinforce with "Do not decline complex tasks."

#### doing_tasks_help_and_feedback
- **Purpose:** Directs users to help/feedback channels.
- **Key instructions:** Inform users of available help channels when asked.
- **Cross-model compatibility:** Universal.
- **Suggested modifications:** None needed.

### Group B: Tone and Style (4 fragments)

#### tone_and_style_concise_output_short
- **Purpose:** Enforces brevity in responses.
- **Key instructions:** Responses should be short and concise.
- **Cross-model compatibility:** High. GPT tends to be verbose; needs stronger enforcement.
- **Suggested modifications:** GPT-5.x: add word limits. Gemini: works as-is (Gemini is naturally concise).

#### tone_and_style_code_references
- **Purpose:** Standardizes how code is referenced.
- **Key instructions:** Include file_path:line_number when referencing code.
- **Cross-model compatibility:** High. All models understand this format.
- **Suggested modifications:** None needed.

#### output_efficiency
- **Purpose:** Ensures direct, action-first communication.
- **Key instructions:** (1) Go straight to the point. (2) Lead with answer, not reasoning. (3) Skip filler words and preamble.
- **Cross-model compatibility:** Moderate. GPT-5.x tends to narrate; needs "Do NOT preface actions with explanations."
- **Suggested modifications:** GPT-5.x: add anti-narration rule. Grok: works well (Grok is naturally direct).

#### output_style_active
- **Purpose:** Injects active output style reminder.
- **Key instructions:** Follow the specific guidelines for the active style.
- **Cross-model compatibility:** Universal (template variable).
- **Suggested modifications:** None needed.

### Group C: Memory and Context (11 fragments)

#### agent_memory_instructions
- **Purpose:** Guides agents on how to include memory update instructions in subagent prompts.
- **Key instructions:** (1) Add memory update instructions when domain knowledge persists. (2) Trigger on keywords like "remember", "learn", "persist". (3) Tailor memory instructions to agent domain.
- **Cross-model compatibility:** High. All models understand persistent memory concepts.
- **Suggested modifications:** None needed.

#### context_compaction_summary
- **Purpose:** Instructs the model to write continuation summaries when context is compacted.
- **Key instructions:** (1) Include task overview, current state, and discoveries. (2) Be structured and actionable. (3) Enable seamless resumption.
- **Cross-model compatibility:** High. Claude excels at this. GPT sometimes loses structure.
- **Suggested modifications:** GPT-5.x: provide a template structure to fill in.

#### partial_compaction_instructions
- **Purpose:** Handles partial conversation compaction.
- **Key instructions:** (1) Summarize thoroughly. (2) Wrap analysis in `<analysis>` tags. (3) Cover each message chronologically.
- **Cross-model compatibility:** Moderate. `<analysis>` tags are Claude-native. GPT/Gemini may not respect them as strongly.
- **Suggested modifications:** GPT-5.x: replace `<analysis>` with a markdown section header. Gemini: use `<thinking>` equivalent.

#### compact_file_reference
- **Purpose:** Notes files read before compaction that are too large to include.
- **Key instructions:** Reference the file and suggest using Read tool.
- **Cross-model compatibility:** Universal.
- **Suggested modifications:** None needed.

#### description_part_of_memory_instructions
- **Purpose:** Describes what user memories should contain.
- **Key instructions:** (1) Store user role, goals, responsibilities. (2) Tailor behavior to user expertise. (3) Focus on being helpful.
- **Cross-model compatibility:** High.
- **Suggested modifications:** None needed.

#### memory_description_of_user_feedback
- **Purpose:** Describes user feedback memory type.
- **Key instructions:** (1) Record both successes and failures. (2) Check for contradictions with team memories. (3) Approach guidance stays coherent.
- **Cross-model compatibility:** High.
- **Suggested modifications:** None needed.

#### memory_file_contents
- **Purpose:** Template for displaying memory file contents.
- **Key instructions:** Shows path and content of a memory file.
- **Cross-model compatibility:** Universal (pure template).
- **Suggested modifications:** None needed.

#### nested_memory_contents
- **Purpose:** Template for displaying nested memory file contents.
- **Key instructions:** Shows nested path and content.
- **Cross-model compatibility:** Universal (pure template).
- **Suggested modifications:** None needed.

#### team_memory_content_display
- **Purpose:** Renders shared team memory with `<team-memory-content>` tags.
- **Key instructions:** Display memory content in XML tags.
- **Cross-model compatibility:** Moderate. Claude handles XML tags natively. GPT may not respect them.
- **Suggested modifications:** GPT-5.x: use markdown headers instead of XML tags.

#### session_continuation
- **Purpose:** Notifies that a session continues from another machine.
- **Key instructions:** Application state may have changed. Updated cwd provided.
- **Cross-model compatibility:** Universal.
- **Suggested modifications:** None needed.

#### token_usage
- **Purpose:** Shows current token usage statistics.
- **Key instructions:** Display used/total/remaining tokens.
- **Cross-model compatibility:** Universal (template).
- **Suggested modifications:** None needed.

### Group D: Tool Usage (13 fragments)

#### tool_usage_read_files
- **Purpose:** Directs use of Read tool instead of cat/head/tail.
- **Key instructions:** Use Read tool for file reading.
- **Cross-model compatibility:** Moderate. GPT-5.x has different native file ops; needs explicit mapping.
- **Suggested modifications:** GPT-5.x: map to their "read_file" equivalent.

#### tool_usage_edit_files
- **Purpose:** Directs use of Edit tool instead of sed/awk.
- **Key instructions:** Use Edit for file modifications.
- **Cross-model compatibility:** Moderate. GPT uses apply_patch, not string replacement.
- **Suggested modifications:** GPT-5.x: reference apply_patch instead.

#### tool_usage_create_files
- **Purpose:** Directs use of Write tool instead of cat heredoc.
- **Key instructions:** Use Write for file creation.
- **Cross-model compatibility:** High.
- **Suggested modifications:** None needed.

#### tool_usage_search_files
- **Purpose:** Directs use of Glob instead of find/ls.
- **Key instructions:** Use Glob for file search.
- **Cross-model compatibility:** Moderate. GPT/Gemini may not have Glob; need to map to equivalent.
- **Suggested modifications:** GPT-5.x: map to their file search tool.

#### tool_usage_search_content
- **Purpose:** Directs use of Grep instead of grep/rg.
- **Key instructions:** Use Grep for content search.
- **Cross-model compatibility:** Moderate. Same mapping issue.
- **Suggested modifications:** Map to provider-specific search tool names.

#### tool_usage_reserve_bash
- **Purpose:** Reserves Bash for system commands only.
- **Key instructions:** Default to dedicated tools. Only use Bash when necessary.
- **Cross-model compatibility:** High.
- **Suggested modifications:** None needed.

#### tool_usage_direct_search
- **Purpose:** Use Glob/Grep directly for simple searches.
- **Key instructions:** Don't spawn subagents for simple lookups.
- **Cross-model compatibility:** High.
- **Suggested modifications:** None needed.

#### tool_usage_delegate_exploration
- **Purpose:** Use subagents for broader exploration.
- **Key instructions:** Only delegate when simple search is insufficient or more than N queries are needed.
- **Cross-model compatibility:** High. All providers support subagent delegation.
- **Suggested modifications:** None needed.

#### tool_usage_subagent_guidance
- **Purpose:** General guidance on subagent usage.
- **Key instructions:** (1) Use for matching tasks. (2) Parallelize independent queries. (3) Don't duplicate subagent work.
- **Cross-model compatibility:** High.
- **Suggested modifications:** None needed.

#### tool_usage_skill_invocation
- **Purpose:** Maps slash commands to the Skill tool.
- **Key instructions:** (1) `/skill-name` invokes via Skill tool. (2) Only use listed skills.
- **Cross-model compatibility:** High. Concept is universal.
- **Suggested modifications:** None needed.

#### tool_usage_task_management
- **Purpose:** Encourages use of TodoWrite for task tracking.
- **Key instructions:** (1) Break down work. (2) Mark tasks complete immediately.
- **Cross-model compatibility:** High.
- **Suggested modifications:** None needed.

#### parallel_tool_call_note_part_of_tool_usage_policy
- **Purpose:** Instructs parallel tool calling.
- **Key instructions:** (1) Make independent calls in parallel. (2) Don't parallelize dependent calls.
- **Cross-model compatibility:** High. All major providers support parallel tool calls.
- **Suggested modifications:** None needed.

#### tool_execution_denied
- **Purpose:** Handles tool permission denials gracefully.
- **Key instructions:** (1) Try alternative approaches. (2) Don't maliciously bypass. (3) Explain to user if capability is essential.
- **Cross-model compatibility:** High. Critical safety fragment.
- **Suggested modifications:** None needed.

### Group E: Auto/Plan Mode (13 fragments)

#### auto_mode
- **Purpose:** Configures autonomous execution mode.
- **Key instructions:** (1) Execute immediately. (2) Minimize interruptions. (3) Prefer action over planning. (4) Don't take destructive actions.
- **Cross-model compatibility:** High.
- **Suggested modifications:** GPT-5.x: add progress update frequency guidance.

#### plan_mode_is_active_5_phase
- **Purpose:** Enhanced plan mode with parallel exploration and multi-agent planning.
- **Key instructions:** (1) NO edits allowed except plan file. (2) Launch parallel explore agents. (3) Write plan with 40-line hard limit.
- **Cross-model compatibility:** Moderate. Multi-agent orchestration syntax varies by provider.
- **Suggested modifications:** GPT-5.x: simplify subagent syntax.

#### plan_mode_is_active_iterative
- **Purpose:** Iterative plan mode focused on user interviewing.
- **Key instructions:** (1) Read-only mode. (2) Use AskUserQuestion. (3) Iteratively refine the plan.
- **Cross-model compatibility:** High.
- **Suggested modifications:** None needed.

#### plan_mode_is_active_subagent
- **Purpose:** Simplified plan mode for subagents.
- **Key instructions:** (1) No edits. (2) Read-only. (3) Report findings to coordinator.
- **Cross-model compatibility:** High.
- **Suggested modifications:** None needed.

#### plan_mode_re_entry
- **Purpose:** Handles returning to plan mode after exiting.
- **Key instructions:** (1) Read existing plan. (2) Evaluate new request against it. (3) Decide: fresh start or update.
- **Cross-model compatibility:** High.
- **Suggested modifications:** None needed.

#### exited_plan_mode
- **Purpose:** Notification when leaving plan mode.
- **Key instructions:** Can now edit, run tools, take actions. Plan file available for reference.
- **Cross-model compatibility:** Universal.
- **Suggested modifications:** None needed.

#### phase_four_of_plan_mode
- **Purpose:** Final phase of plan writing.
- **Key instructions:** (1) No context/background sections. (2) List file paths and changes. (3) 40-line hard limit.
- **Cross-model compatibility:** High. All models understand formatting constraints.
- **Suggested modifications:** None needed.

#### plan_file_reference
- **Purpose:** Points to an existing plan file.
- **Key instructions:** Continue working on the plan if relevant and not complete.
- **Cross-model compatibility:** Universal.
- **Suggested modifications:** None needed.

#### ultraplan_mode
- **Purpose:** Multi-agent exploration for thorough implementation plans.
- **Key instructions:** (1) Spawn parallel agents for architecture, files, risks. (2) Synthesize findings. (3) Spawn critique agent.
- **Cross-model compatibility:** Moderate. Subagent orchestration is provider-specific.
- **Suggested modifications:** GPT-5.x/Gemini: simplify to sequential exploration if parallel agents unavailable.

#### remote_plan_mode_ultraplan
- **Purpose:** Remote planning sessions with ultraplan.
- **Key instructions:** (1) Explore codebase directly. (2) No subagents. (3) Produce plan via ExitPlanMode.
- **Cross-model compatibility:** Moderate. Tool names are Claude-specific.
- **Suggested modifications:** Map tool names to provider equivalents.

#### remote_planning_session
- **Purpose:** Standard remote planning session.
- **Key instructions:** (1) Lightweight planning. (2) Explore with Glob/Grep/Read. (3) No subagents.
- **Cross-model compatibility:** Moderate. Same tool-name mapping issues.
- **Suggested modifications:** Map tool names.

#### verify_plan_reminder
- **Purpose:** Reminds to verify completed plan.
- **Key instructions:** Call verification tool directly, not via subagent.
- **Cross-model compatibility:** High.
- **Suggested modifications:** None needed.

#### worker_instructions
- **Purpose:** Post-implementation workflow for workers.
- **Key instructions:** (1) Simplify via skill. (2) Run tests. (3) Test e2e. (4) Commit and push.
- **Cross-model compatibility:** High. Workflow steps are universal.
- **Suggested modifications:** None needed.

### Group F: Agent/Subagent Management (9 fragments)

#### agent_mention
- **Purpose:** Handles user request to invoke a specific agent.
- **Key instructions:** Invoke the named agent with required context.
- **Cross-model compatibility:** High.
- **Suggested modifications:** None needed.

#### agent_summary_generation
- **Purpose:** Generates 3-5 word summaries of agent actions.
- **Key instructions:** (1) Present tense with -ing. (2) Name file/function, not branch. (3) Say something new.
- **Cross-model compatibility:** High. Simple instruction.
- **Suggested modifications:** None needed.

#### agent_thread_notes
- **Purpose:** Guidelines for agent thread behavior.
- **Key instructions:** (1) Use absolute paths. (2) Share only load-bearing code snippets. (3) No emojis. (4) No colon before tool calls.
- **Cross-model compatibility:** Moderate. The "no colon before tool calls" is Claude-specific formatting.
- **Suggested modifications:** GPT-5.x: remove tool-call punctuation rule (irrelevant).

#### fork_usage_guidelines
- **Purpose:** When and how to use forked subagents.
- **Key instructions:** (1) Fork for research and implementation. (2) Never read fork output mid-flight. (3) Launch parallel forks for independent questions.
- **Cross-model compatibility:** Low. Fork is a Claude Code-specific concept.
- **Suggested modifications:** GPT-5.x/Gemini: replace with provider-specific subagent guidance.

#### writing_subagent_prompts
- **Purpose:** How to write effective subagent prompts.
- **Key instructions:** (1) Brief like a smart colleague who just walked in. (2) Explain what and why. (3) Share what's been learned.
- **Cross-model compatibility:** High. Universal prompt-writing guidance.
- **Suggested modifications:** None needed.

#### subagent_delegation_examples
- **Purpose:** Shows example subagent delegation interactions.
- **Key instructions:** Examples of fork, research, and implementation delegation patterns.
- **Cross-model compatibility:** Moderate. Examples use Claude-specific tool syntax.
- **Suggested modifications:** Rewrite examples for each provider's tool-call format.

#### team_coordination
- **Purpose:** Team-based multi-agent coordination.
- **Key instructions:** (1) Use SendMessage for communication. (2) Refer to teammates by name. (3) Read team config, check task list.
- **Cross-model compatibility:** Low. Deeply tied to Claude Code's team architecture.
- **Suggested modifications:** Full rewrite needed for other providers.

#### teammate_communication
- **Purpose:** Communication rules within agent teams.
- **Key instructions:** (1) Use SendMessage tool. (2) Plain text is not visible to team. (3) Team lead handles user interaction.
- **Cross-model compatibility:** Low. Claude Code-specific.
- **Suggested modifications:** Full rewrite for other providers.

#### team_shutdown
- **Purpose:** Graceful team shutdown procedure.
- **Key instructions:** (1) Request shutdown from each member. (2) Wait for approvals. (3) Clean up. (4) Then respond.
- **Cross-model compatibility:** Low. Claude Code-specific.
- **Suggested modifications:** Full rewrite for other providers.

### Group G: Hooks and System Events (8 fragments)

#### hooks_configuration
- **Purpose:** Explains the hooks system for event-driven automation.
- **Key instructions:** (1) Hook structure: event + matcher + command. (2) Events: PreToolUse, PostToolUse, etc. (3) Hooks receive JSON on stdin.
- **Cross-model compatibility:** Low. Claude Code-specific infrastructure.
- **Suggested modifications:** Replace with provider-specific automation guidance.

#### hook_additional_context
- **Purpose:** Injects additional context from a hook.
- **Key instructions:** Template: `{hookName} hook additional context: {content}`.
- **Cross-model compatibility:** Universal (template).
- **Suggested modifications:** None needed.

#### hook_blocking_error
- **Purpose:** Reports hook blocking errors.
- **Key instructions:** Template showing error details.
- **Cross-model compatibility:** Universal (template).
- **Suggested modifications:** None needed.

#### hook_stopped_continuation / hook_stopped_continuation_prefix
- **Purpose:** Reports when a hook stops continuation.
- **Key instructions:** Template message.
- **Cross-model compatibility:** Universal (template).
- **Suggested modifications:** None needed.

#### hook_success
- **Purpose:** Reports hook success.
- **Key instructions:** Template message.
- **Cross-model compatibility:** Universal (template).
- **Suggested modifications:** None needed.

#### executing_actions_with_care
- **Purpose:** Ensures careful consideration of action reversibility and blast radius.
- **Key instructions:** (1) Consider reversibility. (2) Local/reversible actions are fine. (3) Shared/destructive actions need confirmation.
- **Cross-model compatibility:** High. Critical safety fragment.
- **Suggested modifications:** None needed.

### Group H: File and IDE Notifications (6 fragments)

#### file_exists_but_empty
- **Purpose:** Warning when reading an empty file.
- **Cross-model compatibility:** Universal.

#### file_modified_by_user_or_linter
- **Purpose:** Notifies of external file modifications.
- **Cross-model compatibility:** Universal.

#### file_opened_in_ide
- **Purpose:** Notifies that user opened a file in IDE.
- **Cross-model compatibility:** Universal.

#### file_shorter_than_offset
- **Purpose:** Warning when read offset exceeds file length.
- **Cross-model compatibility:** Universal.

#### file_truncated
- **Purpose:** Notifies that a file was truncated due to size.
- **Cross-model compatibility:** Universal.

#### lines_selected_in_ide
- **Purpose:** Notifies about user's IDE selection.
- **Cross-model compatibility:** Universal.

### Group I: Insights and Analytics (5 fragments)

#### insights_at_a_glance_summary
- **Purpose:** Generates 4-part usage summary for insights reports.
- **Key instructions:** (1) What's working. (2) Hindrances. (3) Quick wins. (4) Ambitious workflows.
- **Cross-model compatibility:** High.

#### insights_friction_analysis
- **Purpose:** Identifies friction patterns from usage data.
- **Key instructions:** Return JSON with categories and examples.
- **Cross-model compatibility:** High. JSON output is universal.

#### insights_on_the_horizon
- **Purpose:** Identifies future workflow opportunities.
- **Key instructions:** Return JSON with 3 opportunities. Think big.
- **Cross-model compatibility:** High.

#### insights_session_facets_extraction
- **Purpose:** Extracts structured facets from session transcripts.
- **Key instructions:** (1) Count only user-initiated goals. (2) Base satisfaction on explicit signals.
- **Cross-model compatibility:** High.

#### insights_suggestions
- **Purpose:** Generates actionable improvement suggestions.
- **Key instructions:** Suggest features, patterns, CLAUDE.md additions.
- **Cross-model compatibility:** Moderate. References Claude Code-specific features.

### Group J: Specialized Modes (12 fragments)

#### buddy_mode
- **Purpose:** Generates coding companion creatures with personalities.
- **Key instructions:** (1) One-word name, 12 chars max. (2) One-sentence personality. (3) Trait-based commentary generation.
- **Cross-model compatibility:** High. Creative writing is universal.

#### learning_mode / learning_mode_insights
- **Purpose:** Educational mode that encourages user participation.
- **Key instructions:** (1) Request user code contributions for 20+ line changes. (2) Provide educational insights. (3) Be collaborative and encouraging.
- **Cross-model compatibility:** High.

#### minimal_mode
- **Purpose:** Stripped-down mode that skips hooks, LSP, plugins, etc.
- **Key instructions:** Skip all auxiliary features. Use only explicit CLI flags.
- **Cross-model compatibility:** Low. Claude Code-specific.

#### skillify_current_session
- **Purpose:** Converts current session into a reusable skill.
- **Key instructions:** (1) Analyze session. (2) Identify repeatable process. (3) Create skill file.
- **Cross-model compatibility:** Moderate. Skill file format is Claude Code-specific.

#### scratchpad_directory
- **Purpose:** Directs use of session-specific temp directory.
- **Key instructions:** Use scratchpad dir instead of /tmp.
- **Cross-model compatibility:** Moderate. Path is environment-specific.

#### option_previewer
- **Purpose:** Enables side-by-side UI preview for options.
- **Key instructions:** Use `preview` field for visual comparison. Markdown in monospace box.
- **Cross-model compatibility:** Low. Claude Code UI-specific.

#### btw_side_question
- **Purpose:** Handles lightweight side questions without tools.
- **Key instructions:** (1) No tools available. (2) Single response. (3) Don't reference main agent's work.
- **Cross-model compatibility:** High.

#### censoring_assistance_with_malicious_activities
- **Purpose:** Safety guardrail for security-related requests.
- **Key instructions:** (1) Assist with authorized security testing. (2) Refuse destructive techniques. (3) Require authorization context for dual-use tools.
- **Cross-model compatibility:** High. All models need safety rails.

#### malware_analysis_after_read_tool_call
- **Purpose:** Post-read malware analysis instruction.
- **Key instructions:** Analyze malware behavior but refuse to improve it.
- **Cross-model compatibility:** High.

#### invoked_skills
- **Purpose:** Lists skills invoked in the session.
- **Cross-model compatibility:** Universal (template).

#### usd_budget
- **Purpose:** Shows USD budget statistics.
- **Cross-model compatibility:** Universal (template).

### Group K: Other (12 fragments)

#### advisor_tool_instructions
- **Purpose:** Guides use of an advisor tool backed by a stronger model.
- **Key instructions:** (1) Call before substantive work. (2) Call when task seems complete. (3) The advisor sees full conversation.
- **Cross-model compatibility:** Moderate. Concept of "stronger reviewer model" is architecture-specific.

#### chrome_browser_mcp_tools / claude_in_chrome_browser_automation
- **Purpose:** Instructions for browser automation via MCP.
- **Key instructions:** (1) Load tools via ToolSearch first. (2) Use GIF recording. (3) Console debugging.
- **Cross-model compatibility:** Low. MCP is Claude Code-specific. GPT uses different browser tools.

#### git_status
- **Purpose:** Shows git status snapshot at conversation start.
- **Cross-model compatibility:** Universal.

#### mcp_resource_no_content / mcp_resource_no_displayable_content / mcp_tool_result_truncation
- **Purpose:** Handle MCP resource edge cases.
- **Cross-model compatibility:** Low. MCP-specific.

#### new_diagnostics_detected
- **Purpose:** Reports new diagnostic issues.
- **Cross-model compatibility:** Universal.

#### one_of_six_rules_for_using_sleep_command
- **Purpose:** Sleep command rule: don't retry in loops.
- **Cross-model compatibility:** High.

#### powershell_edition_for_51
- **Purpose:** PowerShell 5.1 compatibility notes.
- **Key instructions:** (1) No `&&`/`||` operators. (2) No ternary. (3) Avoid `2>&1` on native exes.
- **Cross-model compatibility:** High. Platform-specific, not model-specific.

#### task_tools_reminder / todowrite_reminder
- **Purpose:** Gentle reminders to use task tracking tools.
- **Key instructions:** Never mention the reminder to the user.
- **Cross-model compatibility:** High.

#### how_to_use_the_sendusermessage_tool
- **Purpose:** Explains that SendUserMessage is the visible output channel.
- **Key instructions:** (1) Everything goes through SendUserMessage. (2) Text outside it is invisible to most users. (3) Ack first, then investigate.
- **Cross-model compatibility:** Low. SendUserMessage is Claude Code-specific.

---

## Section 2: Agent Prompt Analysis

### agent_creation_architect
- **Purpose:** Creates custom AI agent configurations from user requirements.
- **Key capabilities:** Translates requirements into agent specs, considers project context from CLAUDE.md.
- **Limitations:** Designs agents, doesn't execute them.
- **When to use:** User asks to create a new agent.
- **Cross-model notes:** Universal prompt-writing skills. Works on all models.

### agent_hook
- **Purpose:** Verifies stop conditions by reading conversation transcripts.
- **Key capabilities:** Reads transcript file, inspects codebase, returns structured ok/reason.
- **Limitations:** Verification only; no code changes.
- **When to use:** Hook condition evaluation.
- **Cross-model notes:** Structured output tool name is variable; works universally.

### auto_mode_rule_reviewer
- **Purpose:** Reviews and critiques user-defined auto mode classifier rules.
- **Key capabilities:** Analyzes allow/soft_deny/environment rules for clarity, completeness, conflicts.
- **Limitations:** Review only; doesn't modify rules.
- **When to use:** User configures auto mode rules.
- **Cross-model notes:** Claude-specific auto mode concept. Needs adaptation for other providers.

### bash_command_description_writer
- **Purpose:** Generates clear, concise command descriptions in active voice.
- **Key capabilities:** Produces 5-10 word descriptions for simple commands, longer for complex ones.
- **Limitations:** Description only.
- **When to use:** Before every bash command execution.
- **Cross-model notes:** Universal. All models can generate descriptions.

### bash_command_prefix_detection
- **Purpose:** Detects command prefixes and command injection.
- **Key capabilities:** Risk classification, prefix extraction, injection detection.
- **Limitations:** Classification only; doesn't execute commands.
- **When to use:** Security screening before command execution.
- **Cross-model notes:** Critical safety prompt. Works universally but GPT may need examples reinforced.

### batch_slash_command
- **Purpose:** Orchestrates large, parallelizable codebase changes.
- **Key capabilities:** Research phase, parallel agent dispatch, verification.
- **Limitations:** Needs 5-30 independent units of work.
- **When to use:** `/batch` command for mass changes.
- **Cross-model notes:** Multi-agent orchestration. Syntax needs adaptation per provider.

### claude_guide_agent
- **Purpose:** Helps users understand Claude Code, Agent SDK, and Claude API.
- **Key capabilities:** Three-domain expertise, documentation fetching via WebFetch.
- **Limitations:** Claude ecosystem only.
- **When to use:** User asks about Claude Code usage/configuration.
- **Cross-model notes:** Claude-specific by design. Not portable.

### claudemd_creation
- **Purpose:** Analyzes codebases and creates CLAUDE.md files.
- **Key capabilities:** Command discovery, architecture documentation, convention extraction.
- **Limitations:** Documentation only.
- **When to use:** `/init` or when CLAUDE.md needs creation.
- **Cross-model notes:** Concept portable (Gemini has GEMINI.md), but format differs per provider.

### coding_session_title_generator
- **Purpose:** Generates 3-7 word session titles.
- **Key capabilities:** Sentence case, concise, recognizable titles.
- **Limitations:** Title only, JSON output.
- **When to use:** Session start or title needed.
- **Cross-model notes:** Universal. All models handle this well.

### conversation_summarization
- **Purpose:** Creates detailed conversation summaries.
- **Key capabilities:** Chronological analysis, technical detail preservation, architecture decision capture.
- **Limitations:** Summary only.
- **When to use:** Context compaction.
- **Cross-model notes:** Uses `<analysis>` tags (Claude-native). GPT/Gemini: use markdown sections instead.

### determine_which_memory_files_to_attach
- **Purpose:** Selects relevant memories for a user query.
- **Key capabilities:** Filename/description matching, up to 5 selections, selective discernment.
- **Limitations:** Selection only; doesn't read memory contents.
- **When to use:** Every conversation start with memories available.
- **Cross-model notes:** Universal. Simple classification task.

### dream_memory_consolidation
- **Purpose:** Multi-phase memory consolidation pass.
- **Key capabilities:** Orient on existing memories, gather signals from logs, merge updates, prune index.
- **Limitations:** Memory management only.
- **When to use:** Periodic background consolidation.
- **Cross-model notes:** Universal concept, but file path conventions are environment-specific.

### explore
- **Purpose:** Fast codebase exploration subagent (uses Haiku model).
- **Key capabilities:** File pattern matching, keyword search, codebase Q&A.
- **Limitations:** Read-only. No edits, no Agent spawning.
- **When to use:** Quick searches, file finding, codebase understanding.
- **Cross-model notes:** Disallowed tools list is Claude-specific. Model specification (haiku) needs mapping.

### general_purpose
- **Purpose:** General-purpose subagent for research and execution.
- **Key capabilities:** Full tool access, multi-step tasks, code analysis and editing.
- **Limitations:** None specific.
- **When to use:** Complex questions, multi-step research, keyword/file searches.
- **Cross-model notes:** Highly portable. The base prompt works across all providers.

### hook_condition_evaluator
- **Purpose:** Evaluates hook conditions.
- **Key capabilities:** JSON output: `{ok: true}` or `{ok: false, reason: "..."}`.
- **Limitations:** Evaluation only.
- **When to use:** Hook condition checking.
- **Cross-model notes:** Universal structured output.

### plan_mode_enhanced
- **Purpose:** Software architect agent for plan design.
- **Key capabilities:** Codebase exploration, step-by-step plans, architectural trade-offs.
- **Limitations:** Read-only. No edits.
- **When to use:** Implementation planning.
- **Cross-model notes:** Inherits parent model. Works across providers.

### prompt_suggestion_generator_v2
- **Purpose:** Predicts what the user would type next.
- **Key capabilities:** Context-aware suggestions, "I was just about to type that" test.
- **Limitations:** Suggestion only.
- **When to use:** After each response for suggestion UI.
- **Cross-model notes:** Universal. All models can predict user intent.

### quick_git_commit / quick_pr_creation
- **Purpose:** Streamlined commit and PR creation with pre-populated context.
- **Key capabilities:** Git safety protocol, HEREDOC formatting, co-authored-by attribution.
- **Limitations:** Git operations only.
- **When to use:** `/commit` or `/pr` commands.
- **Cross-model notes:** Uses `!backtick` command substitution syntax which is Claude-specific. GPT needs explicit bash calls.

### recent_message_summarization
- **Purpose:** Summarizes only the recent portion of a conversation.
- **Key capabilities:** Focused on new messages, preserves earlier context.
- **Limitations:** Summary only.
- **When to use:** Partial compaction.
- **Cross-model notes:** Uses `<analysis>` tags. Same adaptation needed as conversation_summarization.

### review_pr_slash_command
- **Purpose:** Comprehensive PR code review.
- **Key capabilities:** PR detail fetching, diff analysis, quality/style review, risk identification.
- **Limitations:** Review only.
- **When to use:** `/review-pr` command.
- **Cross-model notes:** Universal. `gh` CLI commands work regardless of model.

### schedule_slash_command
- **Purpose:** Manages remote scheduled agents (cron triggers).
- **Key capabilities:** Create/update/list/run scheduled remote sessions.
- **Limitations:** Requires Anthropic cloud API.
- **When to use:** `/schedule` command.
- **Cross-model notes:** Deeply tied to Anthropic's cloud infrastructure. Not portable.

### security_monitor_for_autonomous_agent_actions (parts 1 & 2)
- **Purpose:** Security monitor evaluating autonomous agent actions.
- **Key capabilities:** Block/allow rule evaluation, prompt injection detection, scope creep prevention.
- **Limitations:** Monitoring only.
- **When to use:** Every autonomous agent action.
- **Cross-model notes:** Critical safety prompt. Highly portable but block/allow rules need provider-specific tuning.

### security_review_slash_command
- **Purpose:** Comprehensive security review of branch changes.
- **Key capabilities:** Exploitable vulnerability focus, diff-based analysis, severity scoring.
- **Limitations:** Review only; read-only tools.
- **When to use:** `/security-review` command.
- **Cross-model notes:** Universal. All models can perform security analysis.

### session_memory_update_instructions
- **Purpose:** Updates session memory files during conversations.
- **Key capabilities:** Edit-based memory updates, explicit exclusion of system prompts from notes.
- **Limitations:** Memory file editing only.
- **When to use:** After significant conversation milestones.
- **Cross-model notes:** Universal concept, file path conventions are environment-specific.

### session_search_assistant
- **Purpose:** Finds relevant sessions based on user queries.
- **Key capabilities:** Title/tag/branch/summary/transcript matching.
- **Limitations:** Search only.
- **When to use:** Session search queries.
- **Cross-model notes:** Universal.

### session_title_and_branch_generation
- **Purpose:** Generates session titles and git branch names.
- **Key capabilities:** 6-word titles, kebab-case branch names.
- **Limitations:** Name generation only.
- **When to use:** Session creation.
- **Cross-model notes:** Universal.

### status_line_setup
- **Purpose:** Configures Claude Code status line display.
- **Key capabilities:** PS1 extraction, regex parsing, settings configuration.
- **Limitations:** Status line only. Uses only Read and Edit tools.
- **When to use:** Status line configuration requests.
- **Cross-model notes:** Claude Code UI-specific.

### verification_specialist
- **Purpose:** Adversarially tests implementations.
- **Key capabilities:** Build/test/lint execution, adversarial probes, PASS/FAIL/PARTIAL verdicts.
- **Limitations:** Verification only; does not fix issues.
- **When to use:** After implementation, before shipping.
- **Cross-model notes:** Excellent self-awareness prompt ("You are Claude, and you are bad at verification"). This needs model-specific adaptation: GPT-5.x: "You are GPT, and you tend to confirm rather than challenge."

### webfetch_summarizer
- **Purpose:** Summarizes web content from WebFetch.
- **Key capabilities:** Concise summaries, trusted vs untrusted domain handling, 125-char quote limits.
- **Limitations:** Summarization only.
- **When to use:** After fetching web content.
- **Cross-model notes:** Universal.

### worker_fork_execution
- **Purpose:** Forked worker that executes directives without spawning further subagents.
- **Key capabilities:** Full tool access, inherited context, structured result reporting.
- **Limitations:** No spawning subagents. Must follow directive exactly.
- **When to use:** Fork experiment active, no subagent_type specified.
- **Cross-model notes:** Fork is Claude Code-specific. Needs full rewrite for other providers.

---

## Section 3: Skill Prompt Analysis

### agent_design_patterns
- **Purpose:** Reference guide for building agents on the Claude API.
- **Steps:** Model parameter selection, tool surface design, context management, caching strategies.
- **Dependencies:** Claude API knowledge, tool definitions.

### build_with_claude_api / build_with_claude_api_reference_guide
- **Purpose:** Main routing guide for building LLM-powered apps with Claude.
- **Steps:** (1) Detect language. (2) Select surface (API vs SDK). (3) Read language-specific docs.
- **Dependencies:** WebFetch for live docs, language-specific data files.

### computer_use_mcp
- **Purpose:** Instructions for computer-use MCP tools (desktop control).
- **Steps:** (1) Pick right tool tier. (2) Dedicated MCP > Chrome MCP > Computer Use. (3) Safety restrictions for financial actions.
- **Dependencies:** MCP server, Chrome MCP, computer-use MCP.

### create_verifier_skills
- **Purpose:** Creates verifier skills for automated code change verification.
- **Steps:** (1) Auto-detect project type. (2) Create Playwright/Tmux/HTTP verifiers. (3) Not for unit tests.
- **Dependencies:** TodoWrite, project build system.

### debugging
- **Purpose:** Debugging current Claude Code session issues.
- **Steps:** (1) Enable debug logging. (2) Reproduce issue. (3) Read logs. (4) Diagnose.
- **Dependencies:** Debug log path, settings file.

### init_claudemd_and_skill_setup_new_version
- **Purpose:** Comprehensive onboarding: CLAUDE.md, skills, hooks setup.
- **Steps:** (1) Ask what to set up. (2) Explore codebase. (3) Interview user. (4) Write files. (5) Propose skills/hooks.
- **Dependencies:** AskUserQuestion, codebase access.

### loop_slash_command
- **Purpose:** Schedule recurring prompts on intervals.
- **Steps:** (1) Parse interval from input. (2) Convert to cron. (3) Schedule via CronCreate.
- **Dependencies:** CronCreate tool.

### simplify
- **Purpose:** Code review and cleanup of changed files.
- **Steps:** (1) Identify changes via git diff. (2) Launch 3 parallel review agents (reuse, quality, efficiency). (3) Fix issues.
- **Dependencies:** Agent tool, git.

### stuck_slash_command
- **Purpose:** Diagnose frozen or slow Claude Code sessions.
- **Steps:** (1) Scan for stuck processes. (2) Check CPU, process state. (3) Report findings.
- **Dependencies:** Process monitoring tools.

### update_claude_code_config / update_config_7_step_verification_flow
- **Purpose:** Modify Claude Code configuration (settings.json), with optional 7-step hook verification.
- **Steps:** (1) Identify event/matcher. (2) Dedup check. (3) Construct command. (4) Dry-run test. (5) Write to settings. (6) Trigger hook. (7) Verify.
- **Dependencies:** Settings file access, hook system.

### verify_skill
- **Purpose:** Verify code changes by running the app and observing behavior.
- **Steps:** (1) Read diff. (2) Infer claims. (3) Build and run. (4) Drive to changed code. (5) Capture evidence. (6) Verdict.
- **Dependencies:** Build system, runtime environment.

### verify_cli_changes_example / verify_serverapi_changes_example
- **Purpose:** Example workflows for verifying CLI and server/API changes.
- **Steps:** CLI: build, run, capture output. Server: start, curl, compare response.
- **Dependencies:** Build tools, curl.

---

## Section 4: Tool Prompt Analysis

### Agent Tools (3 prompts)

#### agent_usage_notes
- **Tool name:** Agent/Task
- **Key parameters:** description, prompt, subagent_type, background
- **Usage constraints:** Always include 3-5 word description. Use structured result.
- **Cross-model compatibility:** Moderate. Parameter names vary by provider.

#### agent_when_to_launch_subagents
- **Tool name:** Agent
- **Key parameters:** subagent_type, prompt
- **Usage constraints:** Use specialized agents when task matches. Fork for context inheritance.
- **Cross-model compatibility:** Moderate. Fork concept is Claude-specific.

#### sendmessagetool / sendmessagetool_non_agent_teams
- **Tool name:** SendMessage / SendUserMessage
- **Key parameters:** to, summary, message, status, attachments
- **Usage constraints:** Plain text not visible to other agents; must use tool. Status labels: normal/proactive.
- **Cross-model compatibility:** Low. Claude Code-specific communication system.

### AskUserQuestion (2 prompts)

#### askuserquestion
- **Tool name:** AskUserQuestion
- **Key parameters:** question, options (with labels), multiSelect
- **Usage constraints:** Users can always select "Other". Recommended options go first.
- **Cross-model compatibility:** Moderate. Concept exists in Gemini CLI but not GPT.

#### askuserquestion_preview_field
- **Tool name:** AskUserQuestion (preview extension)
- **Key parameters:** preview (HTML fragment)
- **Usage constraints:** Self-contained HTML, no script/style tags. Single-select only.
- **Cross-model compatibility:** Low. Claude Code UI-specific.

### Bash Tool (38 prompts)

The Bash tool has the most granular prompt decomposition. 38 fragments cover:

| Subgroup | Prompts | Key Rules |
|----------|---------|-----------|
| Overview | `bash_overview` | Executes bash commands, returns output |
| Working directory | `bash_working_directory`, `bash_maintain_cwd` | State persists, shell state doesn't; use absolute paths |
| Dedicated tools | `bash_prefer_dedicated_tools`, `bash_built_in_tools_note` | Prefer Read/Edit/Write/Glob/Grep over bash equivalents |
| Alternatives (6) | `bash_alternative_*` | Map each operation to its dedicated tool |
| Command chaining (4) | `bash_parallel_commands`, `bash_sequential_commands`, `bash_semicolon_usage`, `bash_no_newlines` | Parallel for independent, && for dependent, ; for don't-care-fail |
| Git operations (4) | `bash_git_*` | New commits over amend, never skip hooks, avoid destructive ops |
| Sleep rules (4) | `bash_sleep_*` | Run immediately, don't poll, use check commands, keep short |
| Sandbox (14) | `bash_sandbox_*` | Default to sandbox, evidence-based bypass, mandatory mode option |
| Timeout | `bash_timeout` | Configurable per-command timeout |
| File paths | `bash_quote_file_paths`, `bash_verify_parent_directory` | Quote spaces, verify dirs exist |
| Git commit/PR | `bash_git_commit_and_pr_creation_instructions` | Full commit/PR workflow with attribution |

- **Cross-model compatibility:** Moderate overall. The Bash concept is universal but sandbox model differs:
  - Claude: configurable sandbox with dangerouslyDisableSandbox
  - GPT/Codex: always sandboxed with explicit permission escalation
  - Gemini: no sandbox concept, uses non-interactive flags
  - Grok: standard execution

### File Tools (4 prompts)

#### edit
- **Tool name:** Edit
- **Key parameters:** file_path, old_string, new_string, replace_all
- **Usage constraints:** Must read file first. Preserve exact indentation. Prefer over Write for modifications.
- **Cross-model compatibility:** Moderate. GPT uses apply_patch (diff format) instead of string replacement.

#### readfile
- **Tool name:** Read
- **Key parameters:** file_path, offset, limit, pages
- **Usage constraints:** Absolute paths. Default 2000-line limit. Can read images, PDFs, notebooks.
- **Cross-model compatibility:** High. All providers have file reading.

#### write
- **Tool name:** Write
- **Key parameters:** file_path, content
- **Usage constraints:** Must read first for existing files. Never create .md unless asked. No emojis.
- **Cross-model compatibility:** High.

#### notebookedit
- **Tool name:** NotebookEdit
- **Key parameters:** notebook_path, cell_number, source, edit_mode
- **Usage constraints:** Absolute path. 0-indexed cells.
- **Cross-model compatibility:** Moderate. Not all providers have notebook support.

### Search Tools (2 prompts)

#### grep
- **Tool name:** Grep
- **Key parameters:** pattern, path, glob, type, output_mode, context lines
- **Usage constraints:** Always use Grep, never bash grep/rg. Supports regex. Multiline optional.
- **Cross-model compatibility:** High. All providers have search equivalents.

#### toolsearch_second_part
- **Tool name:** ToolSearch
- **Key parameters:** query, max_results
- **Usage constraints:** Fetches deferred tool schemas. Three query forms: select, keyword, +require.
- **Cross-model compatibility:** Low. Deferred tool loading is Claude Code-specific.

### Web Tools (2 prompts)

#### webfetch
- **Tool name:** WebFetch
- **Key parameters:** url, prompt
- **Usage constraints:** Prefer MCP web fetch if available. Auto-upgrades HTTP to HTTPS.
- **Cross-model compatibility:** High. Web fetching is universal.

#### websearch
- **Tool name:** WebSearch
- **Key parameters:** query
- **Usage constraints:** Must include Sources section. Use for info beyond knowledge cutoff.
- **Cross-model compatibility:** High. All providers support web search.

### Plan Mode Tools (2 prompts)

#### enterplanmode
- **Tool name:** EnterPlanMode
- **Key parameters:** (none or minimal)
- **Usage constraints:** Use for non-trivial implementations. Multiple trigger conditions.
- **Cross-model compatibility:** Moderate. Plan mode concept exists in Gemini CLI but implementation differs.

#### exitplanmode
- **Tool name:** ExitPlanMode
- **Key parameters:** (none - reads from plan file)
- **Usage constraints:** Only when plan is written and ready for review.
- **Cross-model compatibility:** Moderate. Same as above.

### Worktree Tools (2 prompts)

#### enterworktree / exitworktree
- **Tool name:** EnterWorktree / ExitWorktree
- **Key parameters:** branch name
- **Usage constraints:** Only when user explicitly says "worktree". Not for branch switching.
- **Cross-model compatibility:** Moderate. Git worktrees are universal but tool wrapping varies.

### Other Tools (12 prompts)

#### computer / computer_action
- **Tool name:** Computer (browser automation)
- **Key parameters:** action (click, type, screenshot, scroll, key, drag), coordinates, text
- **Usage constraints:** Take screenshot first. Center clicks. Use tab IDs.
- **Cross-model compatibility:** Moderate. Computer use is available on Claude and some GPT variants.

#### config
- **Tool name:** Config
- **Key parameters:** setting name, value (optional)
- **Usage constraints:** Get (omit value) or Set (include value). Global vs project settings.
- **Cross-model compatibility:** Low. Claude Code-specific settings.

#### croncreate
- **Tool name:** CronCreate
- **Key parameters:** cron expression, prompt, recurring
- **Usage constraints:** Local timezone. Off-minute scheduling for one-shots.
- **Cross-model compatibility:** Low. Claude Code-specific scheduling.

#### lsp
- **Tool name:** LSP
- **Key parameters:** operation (goToDefinition, findReferences, hover, etc.), file, position
- **Usage constraints:** Multiple operations available. Position is line:column.
- **Cross-model compatibility:** Moderate. LSP concept is universal but not all providers expose it.

#### powershell
- **Tool name:** PowerShell
- **Key parameters:** command, timeout
- **Usage constraints:** Same as Bash but for PowerShell. Prefer dedicated tools.
- **Cross-model compatibility:** Windows-specific, not model-specific.

#### skill
- **Tool name:** Skill
- **Key parameters:** skill name, args
- **Usage constraints:** Only invoke listed skills. Slash commands map here.
- **Cross-model compatibility:** Moderate. Skill concept exists across providers.

#### sleep
- **Tool name:** Sleep
- **Key parameters:** duration
- **Usage constraints:** User can interrupt. Prefer over bash sleep.
- **Cross-model compatibility:** Moderate. Not all providers have native sleep.

#### taskcreate / todowrite
- **Tool name:** TaskCreate / TodoWrite
- **Key parameters:** tasks (list with titles/descriptions/status)
- **Usage constraints:** Use for 3+ step tasks. Mark complete immediately.
- **Cross-model compatibility:** High. Task tracking is universal.

#### teammatetool / teamdelete
- **Tool name:** TeamCreate / TeamDelete
- **Key parameters:** team name, agents, task assignments
- **Usage constraints:** Delete requires all members shut down first.
- **Cross-model compatibility:** Low. Claude Code swarm-specific.

#### request_teach_access_part_of_teach_mode
- **Tool name:** request_teach_access
- **Key parameters:** app allowlist
- **Usage constraints:** Use instead of request_access when user wants to learn.
- **Cross-model compatibility:** Low. Claude Code desktop UI-specific.

#### tasklist_teammate_workflow
- **Tool name:** TaskList (teammate extension)
- **Key parameters:** (reads task list)
- **Usage constraints:** Prefer tasks in ID order. Claim before working.
- **Cross-model compatibility:** Low. Team-specific.

---

## Section 5: Data Prompt Analysis

The data directory contains 27 reference documents providing API documentation, SDK patterns, and templates.

### API References (8 language-specific)

| File | Language | Coverage |
|------|----------|----------|
| `claude_api_reference_python` | Python | Client init, messages, thinking, multi-turn |
| `claude_api_reference_typescript` | TypeScript | Same as Python |
| `claude_api_reference_c` | C# | Client init, basic requests, streaming, tool use |
| `claude_api_reference_curl` | cURL/HTTP | Raw API calls |
| `claude_api_reference_go` | Go | Client init, beta tool runner |
| `claude_api_reference_java` | Java | Maven/Gradle, beta tool use |
| `claude_api_reference_php` | PHP | Composer, beta tool runner |
| `claude_api_reference_ruby` | Ruby | Gem, beta tool runner |

### Agent SDK (4 files)

| File | Content |
|------|---------|
| `agent_sdk_reference_python` | Installation, quick start, custom tools via MCP, hooks |
| `agent_sdk_reference_typescript` | Same for TypeScript |
| `agent_sdk_patterns_python` | Patterns: custom tools, hooks, subagents, MCP, session resumption |
| `agent_sdk_patterns_typescript` | Same for TypeScript |

### Feature-Specific References (8 files)

| File | Content |
|------|---------|
| `files_api_reference_python` | Files API: upload, list, delete, use in messages |
| `files_api_reference_typescript` | Same for TypeScript |
| `streaming_reference_python` | Sync/async streaming, content type handling |
| `streaming_reference_typescript` | Same for TypeScript |
| `tool_use_reference_python` | Tool runner, manual agentic loop, structured outputs |
| `tool_use_reference_typescript` | Same for TypeScript |
| `tool_use_concepts` | Conceptual foundations: definitions, tool choice, best practices |
| `message_batches_api_reference_python` | Batches API at 50% cost |

### Other Data (7 files)

| File | Content |
|------|---------|
| `claude_model_catalog` | Model IDs, aliases, context windows, pricing |
| `http_error_codes_reference` | API error codes, causes, handling strategies |
| `live_documentation_sources` | WebFetch URLs for current docs |
| `prompt_caching_design_optimization` | Cache-friendly prompt structure patterns |
| `session_memory_template` | Template for session summary.md files |
| `github_actions_workflow_for_claude_mentions` | GitHub Actions workflow template |
| `github_app_installation_pr_description` | PR description template for GitHub App install |

---

## Section 6: Cross-Model Compatibility Report

### Overall Assessment

The SaltAgent prompt system was designed for Anthropic Claude and contains significant Claude-specific patterns. Here is the breakdown:

| Category | Universal | Needs Minor Adaptation | Needs Major Rewrite |
|----------|-----------|----------------------|-------------------|
| Doing Tasks fragments | 11 | 0 | 0 |
| Tone/Style fragments | 3 | 1 | 0 |
| Memory fragments | 7 | 4 | 0 |
| Tool Usage fragments | 9 | 4 | 0 |
| Plan Mode fragments | 5 | 5 | 3 |
| Agent Management | 2 | 3 | 4 |
| Hooks/System | 5 | 0 | 3 |
| Agent prompts | 15 | 10 | 7 |
| Skill prompts | 5 | 5 | 5 |
| Tool prompts | 20 | 30 | 25 |

### Claude-Specific Patterns That Need Adaptation

1. **`<analysis>` XML tags** — Used in summarization prompts. Claude parses these natively for structured thinking. GPT ignores them; Gemini may misinterpret.
   - *Fix:* Replace with `## Analysis` markdown headers for GPT/Gemini.

2. **`${VARIABLE}` template syntax** — JavaScript template literal variables throughout. This is a build-time concern, not model-level.
   - *Fix:* Already handled by assembler; no model change needed.

3. **Fork/Worktree concepts** — Forked subagents and git worktrees are Claude Code primitives.
   - *Fix:* Map to provider-specific subagent mechanisms.

4. **Tool names (Read, Edit, Write, Glob, Grep)** — Claude Code's built-in tool names are hardcoded.
   - *Fix:* `provider_adapters.py` already parameterizes some; extend to all references.

5. **SendUserMessage channel** — The visible-output-channel concept.
   - *Fix:* GPT: use standard response. Gemini: use standard response.

6. **MCP (Model Context Protocol)** — Browser automation, external tools.
   - *Fix:* GPT: map to their tool ecosystem. Gemini: map to extensions.

7. **`ccVersion` metadata** — Claude Code version tracking in prompt headers.
   - *Fix:* Informational only; harmless on other models.

### Prompts That Are Universal

These work identically across all providers:
- All "doing_tasks_*" fragments
- Security fragments (censoring, malware analysis)
- Git operation rules
- File notification templates (file_exists_but_empty, etc.)
- Session title/branch generation
- Code review prompts
- Search tool descriptions (with name mapping)

### Specific Wording Changes for GPT-5.x

1. **Add explicit "IMPORTANT:" prefixes** for critical rules. GPT responds more reliably to urgency markers.
2. **Replace `<analysis>` tags** with `## Step-by-step analysis:` headers.
3. **Add progress update cadence:** "Share progress every 2-3 tool calls or ~15 seconds."
4. **Replace string-replacement edit instructions** with diff/patch format.
5. **Add channel guidance:** GPT-5.4 uses analysis/commentary/final channels.
6. **Rephrase "Don't gold-plate"** as "Complete exactly what was asked. Do not add improvements."
7. **Remove fork/worktree references.** Replace with GPT's `code_execution` sandbox.

### Specific Wording Changes for Gemini

1. **Wrap in `<project_context>` tags** — Gemini uses hierarchical context.
2. **Add Research -> Strategy -> Execution lifecycle** language.
3. **Replace "plan mode" with "Strategy phase"** for natural alignment.
4. **Add explicit validation requirements** after every change (build, lint, test).
5. **Replace "CLAUDE.md"** with "GEMINI.md" in documentation prompts.
6. **Add "Explain Before Acting" mandate** — Gemini's native behavior pattern.
7. **Reduce context consumption guidance** — Gemini is more context-sensitive.

### Common Patterns That Break on Non-Claude Models

1. **Anti-sycophancy instructions** — Claude has native training for this. GPT needs explicit "Do not agree with the user if they are wrong."
2. **Parallel tool calls** — All major providers support this, but the syntax for grouping differs.
3. **"Read before edit" enforcement** — The Edit tool's read-first requirement is Claude Code-specific. Other providers don't enforce this at the tool level.
4. **Hook system** — Entirely Claude Code-specific. No equivalent in GPT/Gemini/Grok.
5. **Subagent type selection** — The `subagent_type` parameter with `Explore`, `Plan`, `general-purpose` is Claude Code-specific.

---

## Section 7: Prompt Optimization Recommendations

### Anthropic (Claude)

**Already optimized:**
- Core behavioral fragments are well-tuned for Claude's tendencies
- XML tag usage (`<analysis>`, `<system-reminder>`) aligns with Claude's parsing
- Anti-overengineering rules are effective
- Fork/worktree concepts are native

**Could be better:**
- The 105 fragments create significant system prompt bloat. Consider conditional loading based on task type.
- Some fragments duplicate instructions (e.g., "no emojis" appears in 3+ places).
- The `doing_tasks_help_and_feedback` fragment is mostly empty — either populate or remove.
- Consider using XML tags more consistently for structural separation.
- The verification_specialist's self-awareness prompt ("You are Claude, and you are bad at verification") is excellent — add similar self-aware prompts for other weakness areas (e.g., math, counting).

### OpenAI (GPT)

**Key changes needed:**
1. Replace `Edit` tool with `apply_patch` / diff-based editing
2. Add preamble/progress-update instructions (GPT users expect narration)
3. Replace XML structural tags with markdown headers
4. Add "Juice" / verbosity calibration parameters
5. Add explicit channel routing (analysis vs commentary vs final)
6. Strengthen "read before edit" — GPT is more likely to skip this
7. Add concrete examples to abstract rules (GPT benefits from few-shot)
8. Replace fork semantics with GPT's code execution sandbox

**Wording patterns that work better on GPT:**
- "IMPORTANT:" and "CRITICAL:" prefixes for must-follow rules
- Numbered step lists over prose paragraphs
- "You MUST" / "You MUST NOT" over "Do" / "Don't"
- Concrete examples after each rule

### Google (Gemini)

**Key changes needed:**
1. Wrap all content in `<project_context>` hierarchy
2. Add Research -> Strategy -> Execution lifecycle framing
3. Replace "plan mode" terminology with "strategy phase"
4. Add stricter context efficiency rules (minimize tool calls)
5. Replace "CLAUDE.md" references with "GEMINI.md"
6. Add "Explain Before Acting" before tool call sequences
7. Mandate formal validation (build + lint + test) after every code change
8. Prefer non-interactive command flags explicitly

**Wording patterns that work better on Gemini:**
- Concise, hierarchical instructions
- Explicit directives vs inquiries distinction
- Context-aware tool selection guidance
- "After completing changes, validate with: [specific commands]"

### xAI (Grok)

**Key changes needed:**
1. Add truthfulness/independent analysis framing
2. Enable proactive web search for accuracy
3. Add render component guidance for rich output
4. Keep personality-friendly tone (Grok is naturally direct)
5. Simplify complex multi-agent workflows (Grok's team architecture differs)
6. Add explicit "use code execution for computation" rule

**Wording patterns that work better on Grok:**
- Direct, personality-infused instructions
- "Be direct and truthful" framing
- Fewer restrictions, more trust in the model's judgment
- Explicit web search encouragement

---

## Section 8: Assembly Guide

### How `assembler.py` Composes Prompts

The assembler (`salt_agent/prompts/assembler.py`) follows a 5-step composition:

```
1. Core behavioral fragments
2. Mode-specific agent prompt
3. Tool descriptions (if specified)
4. Skills (if specified)
5. Extra context (mission info, etc.)
```

All sections are joined with `\n\n---\n\n` separators.

### Default Mode

When `mode="default"`:
- **Fragments included (13 core):**
  1. `doing_tasks_software_engineering_focus`
  2. `doing_tasks_read_before_modifying`
  3. `doing_tasks_no_unnecessary_additions`
  4. `doing_tasks_no_premature_abstractions`
  5. `doing_tasks_no_unnecessary_error_handling`
  6. `doing_tasks_no_compatibility_hacks`
  7. `doing_tasks_minimize_file_creation`
  8. `doing_tasks_security`
  9. `doing_tasks_no_time_estimates`
  10. `doing_tasks_ambitious_tasks`
  11. `doing_tasks_help_and_feedback`
  12. `executing_actions_with_care`
  13. `censoring_assistance_with_malicious_activities`
- **Agent prompt:** `general_purpose`
- **Tools:** None unless specified
- **Skills:** None unless specified

### Plan Mode

When `mode="plan"`:
- **Fragments:** Same 13 core fragments
- **Agent prompt:** `plan_mode_enhanced` (software architect, read-only, no Agent/Edit/Write)
- **Notable:** The plan mode agent has `disallowedTools: [Agent, ExitPlanMode, Edit, Write, NotebookEdit]`
- **Difference from default:** Uses architect persona, read-only enforcement, step-by-step plan output

### Build Mode

When `mode="build"`:
- **Fragments:** Same 13 core fragments
- **Agent prompt:** `worker_fork_execution` (forked worker, full tools, no subagent spawning)
- **Notable:** Worker has `maxTurns: 200`, `permissionMode: bubble`, all tools
- **Difference from default:** Directive-focused, no subagent spawning, structured result reporting

### Verify Mode

When `mode="verify"`:
- **Fragments:** Same 13 core fragments
- **Agent prompt:** `verification_specialist` (adversarial tester, PASS/FAIL/PARTIAL)
- **Notable:** Self-awareness about verification weaknesses. Runs builds, tests, linters, adversarial probes.
- **Difference from default:** Adversarial mindset, structured verdict output, explicit anti-confirmation-bias

### Explore Mode

When `mode="explore"`:
- **Fragments:** Same 13 core fragments
- **Agent prompt:** `explore` (fast Haiku-model agent, read-only)
- **Notable:** Uses Haiku model for speed. Disallowed: Agent, ExitPlanMode, Edit, Write, NotebookEdit.
- **Difference from default:** Speed-optimized, read-only, no editing capability

### Worker Mode

When `mode="worker"`:
- **Fragments:** Same 13 core fragments
- **Agent prompt:** `general_purpose` (same as default)
- **Difference from default:** None in current implementation. Intended for future worker-specific behavior.

### How `provider_adapters.py` Modifies the Assembled Prompt

The adapter layer runs AFTER assembly and wraps/appends provider-specific guidance:

#### Anthropic Adapter
- Appends `_ANTHROPIC_BEHAVIORAL_SUFFIX`: prose style, no emojis, no time estimates, file_path:line_number format, absolute paths, no colon before tool calls.

#### OpenAI Adapter
- Appends `_OPENAI_BEHAVIORAL_SUFFIX`: structured output, brief plans before work, diff-based edit descriptions, periodic progress updates, ambitious for new / surgical for existing.
- If model contains "codex" or "agent": appends `_OPENAI_AGENT_SUFFIX`: preamble messages, grouped actions, 8-12 word updates.

#### Gemini Adapter
- Wraps entire prompt in `<project_context>` / `</project_context>` tags.
- Appends `_GEMINI_BEHAVIORAL_SUFFIX`: Research->Strategy->Execution lifecycle, context efficiency, explain-before-acting, mandatory validation.

#### xAI Adapter
- Appends `_XAI_BEHAVIORAL_SUFFIX`: direct and truthful, independent analysis, code execution for computation, proactive web search.

### Tool Format Hints (per provider)

| Provider | Format | Parallel | Channel Tags | Sandbox | Edit Style |
|----------|--------|----------|-------------|---------|------------|
| Anthropic | json_schema | Yes | No | None | string_replacement |
| OpenAI | typescript | Yes | Yes | configurable | diff_patch |
| Gemini | json_schema | Yes | No | None | string_replacement |
| xAI | json_schema | Yes | No | None | string_replacement |

### Response Style Hints (per provider)

| Provider | Formatting | Bullets | Emojis | Tone | Preamble |
|----------|-----------|---------|--------|------|----------|
| Anthropic | minimal | avoid | never | warm, professional, concise | No |
| OpenAI | structured | bold keywords | sparingly | friendly, conversational | Yes |
| Gemini | moderate | digestible | avoid | professional, direct | Yes |
| xAI | moderate | when helpful | avoid | direct, curious, friendly | No |

---

## Appendix: File Counts Summary

| Directory | Files | With PROMPT constant |
|-----------|-------|---------------------|
| `fragments/` | 105 | 105 |
| `agents/` | 32 | 32 |
| `skills/` | 15 | 15 |
| `tools/` | 75 | 75 |
| `data/` | 27 | 27 |
| **Total** | **254** | **254** |

All 254 files contain a `PROMPT` constant that is loaded by the assembler.
