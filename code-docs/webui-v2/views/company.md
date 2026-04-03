# webui-v2/views/company.js

**Path:** `webui-v2/views/company.js`
**Purpose:** Company detail view. Shows agents (running services), in-progress missions, completed missions, and a "New Agent" button.

## What It Renders

1. **Company name and description**
2. **AGENTS section**: Running/deployed services with health status, run count, schedule, last run time
3. **IN PROGRESS section**: Building and planning missions with component counts and phase badges
4. **Completed section**: Missions with complete status showing "not deployed" label
5. **New Agent button**: Creates a new mission in the workspace

## Navigation

Clicking any mission row navigates to `mission/{id}`.

## Description Logic

Hardcoded descriptions based on workspace name patterns (Personal/Automation, Trading). Falls back to generic "AI-powered company workspace."
