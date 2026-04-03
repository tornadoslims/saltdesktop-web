# webui-v2/index.html

**Path:** `webui-v2/index.html`
**Purpose:** Entry point HTML for the Salt Desktop web UI. Defines the page structure: sidebar, main content area, and status bar.

## Structure

- **Sidebar (`#sidebar`)**: Contains app logo, top navigation (Dashboard), company/mission list (`#sidebar-companies`), bottom navigation (Component Library, Connectors, Settings)
- **Main content (`#main-content`)**: Contains `#view-container` where views are rendered by the router
- **Status bar (`#status-bar`)**: Bottom ticker strip with event feed and connection status dot

## Script Loading Order

1. `app.js` -- Core: API client, State, Router, Sidebar, Ticker, SSE, GraphRenderer
2. `views/dashboard.js` -- Dashboard view
3. `views/company.js` -- Company detail view
4. `views/mission.js` -- Mission view (phase-adaptive)
5. `views/library.js` -- Component library view
6. `views/connectors.js` -- External connectors view
7. `views/settings.js` -- Settings view

All scripts loaded with `?v=12` cache buster. App initialized with `SaltApp.init()`.
