# webui-v2/views/settings.js

**Path:** `webui-v2/views/settings.js`
**Purpose:** Settings view with configuration options.

## What It Renders

1. **Mock Data Mode toggle**: Switch between real and mock data for UI development. Calls `POST /api/mock/enable` or `/api/mock/disable`.
2. **Planning Model settings**: Provider dropdown (Anthropic/OpenAI) and model input field. Calls `GET/POST /api/settings/planning-model`.
3. **API Server info**: Shows connected to localhost:8718
4. **Theme**: Shows "Dark (default)"
5. **Version**: Shows "Salt Desktop v0.1"

## API Calls Made

- `GET /api/mock/status`
- `POST /api/mock/enable` / `POST /api/mock/disable`
- `GET /api/settings/planning-model`
- `POST /api/settings/planning-model`
