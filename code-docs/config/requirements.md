# requirements.txt

**Path:** `requirements.txt`
**Purpose:** Python package dependencies for the JBCP runtime.

## Dependencies

| Package | Version | Why |
|---------|---------|-----|
| packaging | 26.0 | Version parsing utilities |
| setuptools | 82.0.1 | Build system |
| wheel | 0.46.3 | Build system |
| fastapi | 0.135.2 | Web framework for the API server (port 8718) |
| uvicorn | 0.42.0 | ASGI server to run FastAPI |
| anthropic | >=0.88.0 | Anthropic Python SDK for direct planning chat calls |
| openai | >=1.30.0 | OpenAI Python SDK for alternative planning chat provider |

Note: `rich` (used by cryptodash_renderer) and `httpx` (used by credentials and slack) are optional soft dependencies -- the code handles their absence gracefully.
