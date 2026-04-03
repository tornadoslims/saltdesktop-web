# webui-v2/views/myai.js

**Path:** `webui-v2/views/myai.js`
**Purpose:** "My AI" view showing the user's AI workforce. Displays building missions with worker swarms and running services. This route now redirects to the dashboard.

## What It Renders

1. **Building section**: Missions in building phase with swarm visualization -- shows workers (coders, researchers) with component assignments, progress bars
2. **Running section**: Deployed services with health status, schedule, run count

## Swarm Visualization

For each building mission, renders:
- Built components (dimmed, with checkmark and line count)
- Building components (with "Coder" role and "writing code" activity)
- Researcher worker (if planned components exist)
- Queued components
- Progress bar with completion percentage

## Note

The `myai` route is redirected to `dashboard` in the Router. This view exists but is not directly accessible.
