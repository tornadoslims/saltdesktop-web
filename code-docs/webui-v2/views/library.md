# webui-v2/views/library.js

**Path:** `webui-v2/views/library.js`
**Purpose:** Component Library view -- a "trophy case" of everything built across all companies.

## What It Renders

1. **Summary stats**: Total components, built count, total lines of code
2. **Component groups by type**: Connectors, Processors, AI Modules, Outputs, Schedulers
3. **Component cards**: Each shows name, type badge, description, line count, associated mission, build time

## Data Source

Uses `State.getAllComponents()` which aggregates components across all workspaces.

## Type Icons

connector: lightning, processor: gear, ai: brain, output: outbox, scheduler: alarm clock
