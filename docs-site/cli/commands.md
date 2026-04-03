# Slash Commands

SaltAgent provides 72 slash commands organized by category. Type `/help` in interactive mode to see the full list.

## Session Management

| Command | Description |
|---------|-------------|
| `/sessions` | List recent sessions with titles and dates |
| `/resume [id]` | Resume a previous session |
| `/history` | Show conversation summary |
| `/clear` | Clear conversation history |
| `/search <query>` | Search past sessions |

## Git

| Command | Description |
|---------|-------------|
| `/commit` | Invoke the commit skill |
| `/review` | Invoke the review skill |
| `/diff` | Show git diff output |
| `/status` | Show git status output |
| `/branch` | Show current git branch |
| `/log [n]` | Show last n git commits |
| `/stash` | Run git stash |
| `/undo` | Rewind file changes (uses file_history) |
| `/pr` | Create a pull request via gh |
| `/merge` | Merge current branch into main |
| `/rebase` | Rebase current branch on main |
| `/amend` | Amend last commit with staged changes |

## Tasks

| Command | Description |
|---------|-------------|
| `/tasks` | List background tasks and their status |
| `/stop` | Stop all background tasks |

## Model & Provider

| Command | Description |
|---------|-------------|
| `/model [name]` | Show or change current model |
| `/provider [name]` | Show or change current provider |
| `/tokens` | Show token usage stats |
| `/budget` | Show budget tracker stats |
| `/cost` | Show token usage this session |
| `/compact` | Force context compaction now |

## Memory

| Command | Description |
|---------|-------------|
| `/memory` | List memory files |
| `/memories` | List memory files (alias) |
| `/forget <file>` | Delete a memory file |

## Mode

| Command | Description |
|---------|-------------|
| `/auto` | Toggle auto mode (skip all permission prompts) |
| `/plan` | Enable plan mode (agent must plan before acting) |
| `/approve` | Approve plan and let agent proceed |
| `/verify` | Spawn verification specialist to review code |
| `/mode` | Show or change agent mode |
| `/coordinator` | Enter coordinator mode |

## System

| Command | Description |
|---------|-------------|
| `/doctor` | Run health checks |
| `/version` | Show version |
| `/config [key] [value]` | Get or set config |
| `/export` | Export conversation as markdown |
| `/tools` | List available tools |
| `/skills` | List available skills |
| `/help` | Show available commands |
| `/quit` | Exit |

## Project

| Command | Description |
|---------|-------------|
| `/init` | Initialize SaltAgent in current directory |
| `/scaffold` | Create basic project structure (README, tests/, src/) |

## Quick Access

| Command | Description |
|---------|-------------|
| `/cd <path>` | Change working directory |
| `/ls [path]` | Quick directory listing |
| `/cat <file>` | Quick file view |
| `/find <pattern>` | Quick glob search |
| `/run <cmd>` | Quick bash command |
| `/test` | Run tests in the working directory |
| `/format` | Format code in the working directory |

## Conversation

| Command | Description |
|---------|-------------|
| `/retry` | Retry the last failed turn |
| `/continue` | Continue from where the agent stopped |
| `/redo` | Redo the last prompt |
| `/fix` | Fix the last error (re-run with fix instructions) |
| `/summarize` | Summarize the current conversation |
| `/save <path>` | Save conversation to a file |
| `/load <path>` | Load conversation from a file |

## Tools & MCP

| Command | Description |
|---------|-------------|
| `/tool <name>` | Show detailed info about a tool |
| `/mcp` | List MCP servers and their tools/resources |

## Display

| Command | Description |
|---------|-------------|
| `/theme` | Toggle dark/light color intensity |
| `/wrap` | Toggle word wrap |
| `/width <n>` | Set max output width |

## Debug

| Command | Description |
|---------|-------------|
| `/context` | Show context window usage |
| `/state` | Show full agent state |
| `/debug` | Toggle verbose/debug mode |
| `/env` | Show relevant environment variables |
| `/about` | Show about/credits |
| `/changelog` | Show what's new |
| `/stats` | Show session stats (turns, tokens, tools, time) |

## Files

| Command | Description |
|---------|-------------|
| `/recent` | Show recently modified files |
| `/changed` | Show files changed in this session |
