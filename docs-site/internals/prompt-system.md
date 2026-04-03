# Prompt System

SaltAgent includes 254 prompt fragments organized into 5 categories. These are loaded dynamically by the prompt assembler and composed into system prompts.

## Categories

| Category | Count | Purpose |
|----------|-------|---------|
| `fragments` | ~105 | Behavioral instructions (how the agent should act) |
| `tools` | ~75 | Tool-specific usage instructions |
| `agents` | ~32 | Subagent role prompts |
| `skills` | ~15 | Skill-related prompts |
| `data` | ~27 | Reference data (API docs, model catalogs, etc.) |

## Fragment Examples

Fragments are Python modules in `salt_agent/prompts/fragments/` with a `PROMPT` constant:

```python
# doing_tasks_software_engineering_focus.py
PROMPT = """The user will primarily request software engineering tasks..."""
```

Key behavioral fragments:

- `doing_tasks_software_engineering_focus` -- software engineering context
- `doing_tasks_read_before_modifying` -- always read before edit
- `doing_tasks_no_unnecessary_additions` -- don't add features beyond what was asked
- `censoring_assistance_with_malicious_activities` -- refuse harmful requests
- `auto_mode` -- behavior when in auto mode
- `buddy_mode` -- friendly collaboration mode
- `context_compaction_summary` -- how to produce compaction summaries

## Prompt Assembler

The `assemble_system_prompt()` function composes a complete system prompt:

```python
from salt_agent.prompts.assembler import assemble_system_prompt

prompt = assemble_system_prompt(
    mode="default",              # or "plan", "build", "verify", "explore", "worker"
    include_fragments=None,       # None = all core fragments
    include_tools=None,           # None = based on registered tools
    include_skills=None,          # None = none
    extra_context="",             # Additional context
)
```

### Assembly Order

1. Core behavioral fragments (always included)
2. Mode-specific system prompt
3. Tool description prompts (matched to registered tools)
4. Skill prompts (if any)
5. Extra context

## Core System Prompt

The base system prompt (`salt_agent/prompts/system_prompt.py`) defines:

- **Identity**: "You are SaltAgent, a general-purpose AI agent"
- **Core behavior**: concise, read-before-edit, no over-engineering
- **Task guidelines**: software engineering focus, what NOT to do
- **Security**: avoid introducing vulnerabilities
- **Tool usage**: searching, reading, editing, writing, bash guidelines
- **Output**: brief, direct, no emojis
- **Execution care**: consider reversibility and blast radius

## Prompt Registry

The registry provides search and listing across all prompt categories:

```python
from salt_agent.prompts.registry import list_prompts, get_prompt

# List all prompts
all_prompts = list_prompts()

# Filter by category
fragments = list_prompts(category="fragment")
tools = list_prompts(category="tool")

# Get a specific prompt
prompt = get_prompt("fragment", "doing_tasks_read_before_modifying")
```

Each prompt has metadata:

```python
{
    "name": "doing_tasks_read_before_modifying",
    "category": "fragments",
    "description": "Always read files before modifying them",
    "package": "fragments",
    "module": "doing_tasks_read_before_modifying",
}
```

## Data Prompts

Reference data for specialized tasks:

- `claude_api_reference_python` -- Claude API usage in Python
- `claude_api_reference_typescript` -- Claude API usage in TypeScript
- `agent_sdk_patterns_python` -- Agent SDK patterns
- `claude_model_catalog` -- Available Claude models
- `http_error_codes_reference` -- HTTP error code reference
- `github_actions_workflow_for_claude_mentions` -- CI/CD integration

## Agent Prompts

Role-specific prompts for subagents:

- Exploration agent
- Verification agent
- Worker agent
- Code review agent
- Summarization agent

## How Claude Code Does It

Claude Code uses a similar fragment-based system (prompts/ directory with ~250+ fragments). SaltAgent mirrors this architecture:

| Claude Code | SaltAgent |
|-------------|-----------|
| `src/prompts/fragments/` | `salt_agent/prompts/fragments/` |
| `src/prompts/tools/` | `salt_agent/prompts/tools/` |
| `src/prompts/agents/` | `salt_agent/prompts/agents/` |
| Prompt assembly at runtime | `assembler.py` + `registry.py` |
