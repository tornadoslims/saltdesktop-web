# CLI Usage

SaltAgent provides a polished terminal interface at `salt_agent.cli`.

## Running

```bash
# One-shot: run a prompt and exit
python -m salt_agent "Create a hello world script"

# Interactive mode
python -m salt_agent -i

# With provider and model
python -m salt_agent -p openai -m gpt-4o "Fix the tests"

# Auto mode (skip permission prompts)
python -m salt_agent --auto "Refactor the API module"

# Resume a session
python -m salt_agent --session abc-123
```

## CLI Flags

| Flag | Short | Description |
|------|-------|-------------|
| `--provider` | `-p` | LLM provider (`anthropic` or `openai`) |
| `--model` | `-m` | Model name |
| `--interactive` | `-i` | Interactive mode |
| `--auto` | | Skip all permission prompts |
| `--plan` | | Plan mode (agent must plan before acting) |
| `--coordinator` | | Coordinator mode (delegation only) |
| `--max-turns` | | Maximum turns (default 30) |
| `--session` | | Resume a specific session |
| `--no-persist` | | Disable session persistence |
| `--version` | `-V` | Show version |

## Interactive Mode

In interactive mode, you get a prompt where you can type messages and use slash commands. The conversation persists across turns.

Features:

- **Readline support** -- command history, line editing
- **Slash commands** -- 72 commands for common operations
- **Colored output** -- ANSI colors for tool output, errors, status
- **Token tracking** -- per-turn and cumulative costs
- **Session persistence** -- automatic checkpointing for crash recovery

## Output

The CLI uses ANSI escape codes for formatting:

- Blue -- tool names and status
- Cyan -- tool parameters
- Green -- success messages
- Red -- errors
- Yellow -- warnings
- Dim -- metadata and timestamps

Color can be disabled with the `NO_COLOR` environment variable.
