# Configuration

## Config File

SaltAgent reads configuration from `~/.s_code/config.json`:

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

## Config Fields

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `provider` | string | `"openai"` | LLM provider (`anthropic` or `openai`) |
| `model` | string | `""` | Model name (empty = provider default) |
| `auto_mode` | bool | `false` | Skip all permission prompts |
| `show_suggestions` | bool | `false` | Show follow-up suggestions after turns |
| `web_extractor` | string | `"trafilatura"` | HTML extraction method |
| `max_turns` | int | `30` | Maximum turns per run |
| `temperature` | float | `0.0` | Sampling temperature |
| `max_budget_usd` | float | `0.0` | Budget limit (0 = unlimited) |

## Setting Config

### Via CLI

```
salt> /config provider openai
salt> /config model gpt-4o-mini
salt> /config max_budget_usd 5.0
salt> /config auto_mode true
```

### Via config file

Edit `~/.s_code/config.json` directly.

### Via environment

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export OPENAI_API_KEY="sk-..."
```

### Via CLI flags (override config file)

```bash
python -m salt_agent -p anthropic -m claude-sonnet-4-20250514 "task"
```

## Precedence

Settings are resolved in this order (later overrides earlier):

1. Built-in defaults
2. Config file (`~/.s_code/config.json`)
3. Environment variables (API keys only)
4. CLI flags

## Directory Structure

```
~/.s_code/
  config.json       # User configuration
  sessions/         # Session JSONL files
  memory/           # Cross-session memory files
    MEMORY.md       # Memory index
  snapshots/        # File history backups
  skills/           # User-installed skills
```

## Project Instructions

Project-specific configuration is done through `SALT.md` or `CLAUDE.md` files (not the config file). See the [Memory System](../features/memory.md) docs for details.
