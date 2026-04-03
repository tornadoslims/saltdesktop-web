# webui-v2/views/dashboard.js

**Path:** `webui-v2/views/dashboard.js`
**Purpose:** Dashboard view -- the home page. Shows a greeting, running services, in-progress missions, planning missions, recent activity feed, and company cards.

## What It Renders

1. **Greeting**: "Good morning/afternoon/evening, Jim."
2. **What's Running**: Services with status=running. Shows name, run count, schedule, last run time.
3. **In Progress**: Missions in building phase. Shows component progress bar and current building component.
4. **Planning**: Missions in planning phase with timestamp.
5. **Recent Activity**: Live-updating feed from SSE events (max 12 items).
6. **Your Companies**: Card grid of all workspaces with running/building counts.
7. **Global chat bar**: Input field at bottom (placeholder).

## Event Handling

`onEvent(data)`: Prepends new activity items to the feed when receiving SSE events with `ceo_text`.

## Navigation

Clicking a mission row navigates to `mission/{id}`. Clicking a company card navigates to `company/{id}`. Clicking a service row finds the associated mission and navigates to it.

## Empty State

When no workspaces exist, shows a welcome message with a "Create Company" CTA button.
