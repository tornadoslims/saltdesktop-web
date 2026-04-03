# Anthropic Provider

The Anthropic adapter uses the `anthropic` Python SDK to communicate with Claude models.

## Configuration

```python
agent = create_agent(
    provider="anthropic",
    model="claude-sonnet-4-20250514",  # or any Claude model
    api_key="sk-ant-...",  # or set ANTHROPIC_API_KEY env var
    fallback_model="claude-3-haiku-20240307",  # cheaper fallback
)
```

## Default Model

`claude-sonnet-4-20250514` (Claude Sonnet 4)

## Prompt Caching

The Anthropic adapter automatically enables prompt caching by adding `cache_control: {"type": "ephemeral"}` to the system prompt. This means:

- The system prompt (project instructions + tool definitions) is cached across turns
- Subsequent turns in the same conversation pay only for the new content
- Subagent forks share the parent's prompt cache prefix (identical system prompt and tool definitions)

This is automatic -- no configuration needed.

## Retry Behavior

Retriable errors:

- `RateLimitError` -- API rate limit exceeded
- `APIConnectionError` -- network issues
- `InternalServerError` -- server-side errors

Retry schedule: 1s, 2s, 4s (exponential backoff, 3 attempts).

During retries, a recoverable `AgentError` event is yielded so the caller knows what's happening.

## Model Fallback

If all retries fail and a `fallback_model` is configured, the adapter automatically retries with the fallback model. This is useful for:

- Falling back from expensive models to cheaper ones on rate limits
- Using Haiku as a backup when Sonnet is overloaded

## Token Usage

After each successful API call, `last_usage` is populated:

```python
adapter = agent.provider
print(adapter.last_usage)
# {"input_tokens": 1234, "output_tokens": 567, "cache_read_input_tokens": 890, "cache_creation_input_tokens": 344}
```

## Cost Tracking

The `BudgetTracker` knows Anthropic pricing:

| Model | Input (per 1M tokens) | Output (per 1M tokens) |
|-------|----------------------|------------------------|
| claude-sonnet-4-20250514 | $3.00 | $15.00 |
| claude-3-5-sonnet-20241022 | $3.00 | $15.00 |
| claude-3-haiku-20240307 | $0.25 | $1.25 |

## Message Format

Anthropic uses its native message format:

```python
{
    "role": "user",  # or "assistant"
    "content": "text content"
    # or for tool results:
    "content": [
        {"type": "tool_result", "tool_use_id": "...", "content": "result text"}
    ]
}
```

The system prompt is sent separately (not in messages array) with cache control.
