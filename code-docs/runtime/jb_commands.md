# runtime/jb_commands.py

**Path:** `runtime/jb_commands.py`
**Purpose:** Command handling for the API chat endpoint. Mirrors the plugin commands in Python. All mutations go through the same runtime modules.

## Main Entry Point

### `handle_command(message, workspace_id) -> dict | None`
Parses a message for slash commands. Returns `{text, command: True, command_type}` if the message is a command, or `None` if it is a regular message (should be forwarded to LLM).

Supported commands: `/mission`, `/contextmem`, `/jbdebug`, `/status`

## Command Handlers

### `/mission` subcommands
- **`current` / `status`** (default): Shows workspace name, focused mission, status, planning mode
- **`list`**: Lists all missions in the workspace with status and focused indicator
- **`new <goal>`**: Creates a new mission in planning state, attaches to workspace, sets as focused, ensures context file. Blocks if another mission is already in planning.
- **`generate` / `gen`**: Calls `generate_mission_plan()` to generate components + tasks from conversation
- **`approve` / `go`**: Calls `approve_mission()` to create real components and tasks
- **`cancel`**: Marks mission as cancelled
- **`switch <name>` / `focus <name>`**: Fuzzy-matches a mission by goal text or ID prefix
- **`help`**: Shows all subcommands

### `/contextmem`
Shows context injection info for the workspace: company name, focused mission goal and status.

### `/jbdebug`
Toggles debug settings stored in `data/jbcp_settings.json`. Settings: `debug_footer`, `debug_signals`, `debug_tool_blocks`. Shows current state or toggles a specific setting.

### `/status`
Quick workspace summary: mission count, task counts (active/complete/failed), focused mission.
