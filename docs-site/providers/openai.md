# OpenAI Provider

The OpenAI adapter uses the `openai` Python SDK to communicate with GPT models.

## Configuration

```python
agent = create_agent(
    provider="openai",
    model="gpt-4o",  # or gpt-4o-mini, gpt-4.1, etc.
    api_key="sk-...",  # or set OPENAI_API_KEY env var
    fallback_model="gpt-4o-mini",  # cheaper fallback
)
```

## Default Model

`gpt-4o`

## Lazy Initialization

The OpenAI client is created lazily on first use. This avoids import errors if the `openai` package is not installed when using other providers. If the package is missing, an `AgentError` is yielded.

## Message Format Conversion

SaltAgent uses Anthropic's message format internally. The OpenAI adapter converts:

- System prompt goes into a `{"role": "system", "content": "..."}` message
- Tool use blocks are converted to OpenAI's function calling format
- Tool results are converted from Anthropic's `tool_result` content blocks to OpenAI's `tool` role messages

## Streaming

The adapter uses OpenAI's streaming API (`stream=True`). Function call arguments are accumulated across delta chunks and parsed when complete.

## Retry Behavior

Retriable errors are caught with 3 retry attempts and exponential backoff (1s, 2s, 4s). The adapter detects OpenAI-specific error types from the SDK.

## Cost Tracking

| Model | Input (per 1M tokens) | Output (per 1M tokens) |
|-------|----------------------|------------------------|
| gpt-4o | $2.50 | $10.00 |
| gpt-4o-mini | $0.15 | $0.60 |
| gpt-4.1 | $2.00 | $8.00 |
| gpt-4.1-mini | $0.40 | $1.60 |
| gpt-4.1-nano | $0.10 | $0.40 |

## Token Usage

After each call, `last_usage` is populated from the API response:

```python
print(agent.provider.last_usage)
# {"input_tokens": 1234, "output_tokens": 567}
```

## Notes

- Uses `max_completion_tokens` instead of `max_tokens` (OpenAI convention)
- Temperature defaults to 0.0 for deterministic output
- The adapter handles both text responses and function call responses in the same stream
