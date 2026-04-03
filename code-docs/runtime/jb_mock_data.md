# runtime/jb_mock_data.py

**Path:** `runtime/jb_mock_data.py` (1,477 lines)
**Purpose:** Mock data for UI development. Returns realistic fake data for all API endpoints when mock mode is enabled.

## Overview

Provides two complete mock workspaces ("Personal Automation" and "Trading Tools") with:
- 6 missions across planning, building, complete, and deployed states
- 14 components across 4 types (connector, processor, ai, output, scheduler)
- 12+ tasks in various statuses
- 2 running services (Gmail checker and BTC alert)
- Mock signals for live activity simulation
- Chat history for planning conversations

## Mock Workspaces

| ID | Name | Stage | Missions |
|----|------|-------|----------|
| mock-ws-personal | Personal Automation | building | Gmail Alert, News Digest, Expense Tracker, General Chat |
| mock-ws-trading | Trading Tools | production | BTC Alert, General Chat |

## Key Functions

- `get_workspaces()`: Returns 2 workspaces with full metadata
- `get_workspace_missions(workspace_id)`: Returns missions for a workspace
- `get_workspace_components(workspace_id)`: Returns components with graph-ready data
- `get_workspace_graph(workspace_id)`: Returns nodes/edges for the component graph
- `get_mission_tasks(mission_id)`: Returns tasks for a mission
- `get_services()`: Returns 2 running services with run history
- `get_agents()`: Returns mock agent activity data
- `get_health()`: Returns mock health status
- `get_chat_history(workspace_id)`: Returns mock planning conversation
- `get_prompt_debug(workspace_id)`: Returns mock prompt injection debug info
- `get_next_mock_signal()`: Returns randomized tool/agent signals for live SSE
