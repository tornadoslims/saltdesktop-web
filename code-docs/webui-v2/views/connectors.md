# webui-v2/views/connectors.js

**Path:** `webui-v2/views/connectors.js`
**Purpose:** External service connectors view. Shows all 19+ supported services and their connection status.

## What It Renders

1. **Stats bar**: Connected count and available count
2. **Service groups**: Email & Communication, Productivity, Developer, Business, Cloud & Infrastructure, Databases
3. **Connector cards**: Each shows icon, name, category, auth type (OAuth/API Key/Connection String), connection status badge
4. **Click modal**: Connected services show details; disconnected services show instructions to use the Swift companion app

## API Calls Made

- `GET /api/connections` -- fetches all services with connection status

## Service Icons

Hardcoded emoji icons for each service (gmail: envelope, github: octopus, etc.)
