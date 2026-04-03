# Getting Started

## Installation

### Prerequisites

- Python 3.11+
- An API key for Anthropic or OpenAI

### Install from source

```bash
git clone https://github.com/tornadoslims/saltdesktop-web.git
cd saltdesktop-web
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Set your API key

```bash
# For Anthropic (default provider)
export ANTHROPIC_API_KEY="sk-ant-..."

# For OpenAI
export OPENAI_API_KEY="sk-..."
```

## Quick Start

### One-shot mode

Run a single prompt and exit:

```bash
python -m salt_agent "Create a hello world script in Python"
```

With a specific provider and model:

```bash
python -m salt_agent -p openai -m gpt-4o "Build a web scraper for news headlines"
```

### Interactive mode

Start an interactive session with conversation history:

```bash
python -m salt_agent -i
```

You'll see a prompt where you can type messages and use slash commands:

```
salt> Fix the failing tests in tests/test_api.py
[Using bash: python -m pytest tests/test_api.py]
...
salt> /tokens
Input: 12,450  Output: 3,200  Cost: $0.08
salt> /quit
```

### CLI flags

| Flag | Description |
|------|-------------|
| `-p`, `--provider` | LLM provider: `anthropic` or `openai` |
| `-m`, `--model` | Model name (e.g., `gpt-4o`, `claude-sonnet-4-20250514`) |
| `-i`, `--interactive` | Interactive mode (default if no prompt given) |
| `--auto` | Auto mode -- skip all permission prompts |
| `--plan` | Plan mode -- agent must plan before acting |
| `--coordinator` | Coordinator mode -- delegation only, no direct writes |
| `--max-turns` | Maximum turns per run (default: 30) |
| `--session` | Resume a specific session by ID |
| `--no-persist` | Disable session persistence |

## Configuration

SaltAgent stores configuration in `~/.s_code/config.json`:

```json
{
  "provider": "openai",
  "model": "",
  "auto_mode": false,
  "show_suggestions": false,
  "web_extractor": "trafilatura",
  "max_turns": 30,
  "temperature": 0.0,
  "max_budget_usd": 0.0
}
```

You can edit this file directly or use the `/config` slash command:

```
salt> /config provider openai
salt> /config model gpt-4o-mini
salt> /config max_budget_usd 5.0
```

## Project Instructions

SaltAgent automatically loads project-specific instructions from `SALT.md` or `CLAUDE.md` files in the working directory (and parent directories, up to 10 levels). These instructions are injected at the top of the system prompt.

Create a `SALT.md` in your project root:

```markdown
# Project Instructions

This is a Python FastAPI project. The API server is in `src/api/`.
Tests are in `tests/`. Run tests with `pytest tests/ -v`.

## Conventions
- Use type hints on all function signatures
- Keep functions under 30 lines
- Write tests for every new endpoint
```

## First Run Walkthrough

1. **Navigate to your project directory:**
   ```bash
   cd ~/my-project
   ```

2. **Start interactive mode:**
   ```bash
   python -m salt_agent -i
   ```

3. **Try some commands:**
   ```
   salt> Explain the architecture of this project
   salt> /tools          # see available tools
   salt> /skills         # see available skills
   salt> /help           # see all slash commands
   ```

4. **Check your session later:**
   ```
   salt> /sessions       # list past sessions
   salt> /resume abc123  # resume a session
   ```

## Directory Structure

After first run, SaltAgent creates:

```
~/.s_code/
  config.json       # User configuration
  sessions/         # Session JSONL files for crash recovery
  memory/           # Cross-session memory files
    MEMORY.md       # Memory index
  snapshots/        # File history backups (for /undo)
  skills/           # User-installed skills
```

## Next Steps

- [Architecture](architecture.md) -- understand how the system works
- [Embedding](embedding.md) -- use SaltAgent as a library in your Python projects
- [Tools](tools/index.md) -- explore all 42 built-in tools
- [CLI Commands](cli/commands.md) -- all 72 slash commands
