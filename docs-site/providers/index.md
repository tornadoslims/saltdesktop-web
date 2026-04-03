# Providers Overview

SaltAgent supports multiple LLM providers through the `ProviderAdapter` abstraction. Each provider translates SaltAgent's internal message format to the provider's API format and streams responses back as `AgentEvent` objects.

## Built-in Providers

| Provider | Default Model | API Key Env Var |
|----------|--------------|-----------------|
| [Anthropic](anthropic.md) | `claude-sonnet-4-20250514` | `ANTHROPIC_API_KEY` |
| [OpenAI](openai.md) | `gpt-4o` | `OPENAI_API_KEY` |

## Selecting a Provider

```python
# Via create_agent
agent = create_agent(provider="anthropic", model="claude-sonnet-4-20250514")
agent = create_agent(provider="openai", model="gpt-4o")

# Via CLI
python -m salt_agent -p anthropic -m claude-sonnet-4-20250514 "Fix the bug"
python -m salt_agent -p openai -m gpt-4o-mini "Explain this code"

# Via config file (~/.s_code/config.json)
{"provider": "openai", "model": "gpt-4o"}
```

## Provider Interface

All providers implement the `ProviderAdapter` ABC:

```python
from salt_agent.providers.base import ProviderAdapter
from salt_agent.events import AgentEvent

class ProviderAdapter(ABC):
    @abstractmethod
    async def stream_response(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> AsyncIterator[AgentEvent]:
        """Stream a response from the LLM, yielding events."""
        ...

    async def quick_query(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 500,
    ) -> str:
        """Non-streaming query for side-queries."""
        ...
```

### stream_response

The primary method. Yields a stream of:

- `TextChunk(text="...")` -- model-generated text
- `ToolUse(tool_id="...", tool_name="...", tool_input={...})` -- tool call request
- `AgentError(error="...", recoverable=True/False)` -- errors

### quick_query

A lightweight non-streaming query used for:

- Memory file relevance ranking
- Memory extraction from conversations
- Session title generation
- AI bash command classification
- Follow-up suggestion generation

The default implementation collects `stream_response` output. Providers can override for efficiency.

## Common Features

All providers share:

- **Retry with exponential backoff** -- 3 retries for rate limits and server errors
- **Model fallback** -- automatically switch to `fallback_model` when the primary fails
- **Token usage tracking** -- `last_usage` dict populated after each call
- **API key from environment** -- falls back to `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` if not provided
