<h1 align="center">
  <br>
  🧂 SaltAgent (s_code)
  <br>
</h1>

<p align="center">
  <strong>A general-purpose AI agent execution engine for the terminal.</strong><br>
  42 tools · 72 commands · 17 skills · 1245 tests<br>
  Anthropic + OpenAI · MCP support · Plugin system
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue" alt="Python">
  <img src="https://img.shields.io/badge/tests-1245%20passing-green" alt="Tests">
  <img src="https://img.shields.io/badge/tools-42-cyan" alt="Tools">
  <img src="https://img.shields.io/badge/license-MIT-yellow" alt="License">
</p>

---

## What is SaltAgent?

SaltAgent is a standalone AI agent that can write code, run commands, search the web, manage files, and execute complex multi-step tasks — all from your terminal. Think of it as an open-source Claude Code / Codex CLI, built in Python, embeddable in any project.

```
  ███████╗ █████╗ ██╗  ████████╗
  ██╔════╝██╔══██╗██║  ╚══██╔══╝
  ███████╗███████║██║     ██║
  ╚════██║██╔══██║██║     ██║
  ███████║██║  ██║███████╗██║
  ╚══════╝╚═╝  ╚═╝╚══════╝╚═╝
```

---

## Quick Start

### Install

```bash
git clone https://github.com/tornadoslims/saltdesktop-web.git
cd saltdesktop-web
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Set your API key

```bash
# Option 1: Environment variable
export OPENAI_API_KEY="sk-..."
# or
export ANTHROPIC_API_KEY="sk-ant-..."

# Option 2: Config file
mkdir -p ~/.s_code
echo '{"provider": "openai", "model": "gpt-4o"}' > ~/.s_code/config.json
```

### Run

```bash
# Interactive mode (recommended)
python -m salt_agent

# One-shot mode
python -m salt_agent "Create a Python script that checks the weather"

# With specific provider/model
python -m salt_agent -p anthropic -m claude-sonnet-4-20250514 "Fix the failing tests"

# Auto mode (skip permission prompts)
python -m salt_agent --auto "Refactor the auth module"
```

---

## Features

### 42 Built-in Tools
| Category | Tools |
|----------|-------|
| **File ops** | read, write, edit, multi_edit, glob, grep, list_files |
| **Execution** | bash, python_repl |
| **Web** | web_search, web_fetch |
| **Git** | git_status, git_diff, git_commit |
| **Tasks** | task_create, task_list, task_get, task_output, task_stop, task_update |
| **Agent** | agent (subagents), skill, tool_search, ask_user |
| **Planning** | todo_write, enter/exit_plan_mode |
| **Teams** | team_create, team_delete, send_message |
| **System** | config, sleep, brief, clipboard, open, enter/exit_worktree |
| **Scheduling** | cron_create, cron_delete, cron_list |
| **MCP** | mcp_list_resources |
| **Notebook** | notebook_edit |

### 72 Slash Commands
```
/help /model /provider /auto /plan /approve /verify
/commit /review /diff /status /branch /log /pr
/tasks /tokens /budget /compact /cost /stats
/memory /forget /skills /tools /search /doctor
/cd /ls /cat /find /run /test /fix /format
... and 40 more
```

### Multi-Provider Support
- **Anthropic** (Claude) — prompt caching, streaming
- **OpenAI** (GPT) — function calling, streaming
- Automatic retry with exponential backoff
- Model fallback on failure
- Token budget tracking with auto-continue

### Advanced Features
- **Context compaction** — 5-layer system keeps long sessions alive
- **Memory system** — persistent project memory with LLM-powered relevance ranking
- **Session persistence** — crash recovery, resume, search across sessions
- **MCP integration** — connect to any MCP server for additional tools
- **Skills** — 17 bundled skills (commit, review, debug, test, deploy, etc.)
- **Subagents** — spawn focused child agents for parallel work
- **Background tasks** — run multiple agents simultaneously
- **Streaming tool execution** — safe tools start during model streaming
- **Hook engine** — 29 lifecycle events, in-process/shell/HTTP hooks
- **Plugin system** — extend with custom tools, hooks, and prompts
- **AI permission classifier** — smart bash command safety evaluation

---

## Embed in Your Python Project

SaltAgent is designed to be embedded. No CLI required.

```python
import asyncio
from salt_agent import create_agent

async def main():
    agent = create_agent(
        provider="openai",
        model="gpt-4o",
        working_directory="./my-project",
        system_prompt="You are a helpful coding assistant.",
    )

    async for event in agent.run("Add error handling to the API endpoints"):
        if event.type == "text_chunk":
            print(event.text, end="")
        elif event.type == "tool_start":
            print(f"\n  [Using {event.tool_name}]")

asyncio.run(main())
```

### Custom Tools

```python
from salt_agent import Tool, ToolDefinition, ToolParam, create_agent, ToolRegistry

class MyDatabaseTool(Tool):
    def definition(self):
        return ToolDefinition(
            name="db_query",
            description="Query the database",
            params=[ToolParam("sql", "string", "SQL query")],
        )

    def execute(self, **kwargs):
        # Your database logic here
        return "Query results..."

registry = ToolRegistry()
registry.register(MyDatabaseTool())
agent = create_agent(tools=registry)
```

### Hook into Agent Activity

```python
agent = create_agent(...)

# Track every tool call
agent.hooks.on("post_tool_use", lambda data:
    print(f"Agent used {data['tool_name']}: {data['result'][:100]}")
)

# Get notified on completion
agent.hooks.on("on_complete", lambda data:
    send_notification(f"Agent finished in {data['turns']} turns")
)
```

See the [full embedding guide](docs-site/embedding.md) for FastAPI, Flask, Celery, desktop app, and Jupyter examples.

---

## Configuration

Config file: `~/.s_code/config.json`

```json
{
  "provider": "openai",
  "model": "gpt-4o",
  "auto_mode": false,
  "max_turns": 30,
  "temperature": 0.0,
  "max_budget_usd": 5.0,
  "show_suggestions": false,
  "web_extractor": "trafilatura"
}
```

All settings can be overridden with CLI flags or changed at runtime with `/config`.

---

## Project Structure

```
salt_agent/
├── agent.py            # Core agent loop
├── config.py           # AgentConfig
├── cli.py              # Terminal interface (72 commands)
├── context.py          # Context assembly
├── compaction.py       # 5-layer compaction
├── hooks.py            # 29-event hook engine
├── memory.py           # Memory system + LLM ranking
├── permissions.py      # Permission rules + AI classifier
├── persistence.py      # JSONL session storage
├── security.py         # Bash command classifier
├── subagent.py         # Fresh spawn + fork
├── file_history.py     # Content-addressed snapshots
├── stop_hooks.py       # Post-turn processing
├── attachments.py      # 15 system-reminder types
├── state.py            # Reactive state store
├── token_budget.py     # Per-turn token tracking
├── coordinator.py      # Delegation-only mode
├── streaming_executor.py # Mid-stream tool execution
├── search_index.py     # Session search index
├── plugins.py          # Plugin discovery
├── tools/              # 42 tools
├── providers/          # Anthropic + OpenAI adapters
├── prompts/            # 254 system prompts + assembler
├── skills/             # 17 bundled skills
├── mcp/                # MCP server integration
├── tasks/              # Background task manager
└── tests/              # 1245 tests
```

---

## Running Tests

```bash
source .venv/bin/activate
python -m pytest salt_agent/tests/ -v
```

---

## License

MIT

---

Built with Claude Opus 4.6. Inspired by Claude Code's architecture.
