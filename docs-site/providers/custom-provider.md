# Custom Provider

Create your own provider adapter to connect SaltAgent to any LLM backend.

## Interface

Implement the `ProviderAdapter` abstract class:

```python
from salt_agent.providers.base import ProviderAdapter
from salt_agent.events import AgentEvent, TextChunk, ToolUse, AgentError

class MyProviderAdapter(ProviderAdapter):
    def __init__(self, api_key: str = "", model: str = ""):
        self.api_key = api_key
        self.model = model
        self.last_usage = {"input_tokens": 0, "output_tokens": 0}

    async def stream_response(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> AsyncIterator[AgentEvent]:
        # Your implementation here
        ...
```

## Required: stream_response

This method must:

1. Send the system prompt, messages, and tool definitions to your LLM
2. Yield `TextChunk` events for generated text
3. Yield `ToolUse` events for tool calls
4. Yield `AgentError` events for errors
5. Populate `self.last_usage` with token counts

### Yielding Text

```python
yield TextChunk(text="Here is my response...")
```

### Yielding Tool Calls

```python
yield ToolUse(
    tool_id="call_123",      # unique ID for this tool call
    tool_name="read",         # must match a registered tool name
    tool_input={"file_path": "/path/to/file"},
)
```

### Yielding Errors

```python
yield AgentError(
    error="Rate limited, retrying...",
    recoverable=True,
)
```

## Optional: quick_query

Override for efficient non-streaming queries:

```python
async def quick_query(self, prompt: str, system: str = "", max_tokens: int = 500) -> str:
    # Efficient single-turn query for side operations
    response = await my_api.complete(prompt=prompt, system=system)
    return response.text
```

If not overridden, the default implementation collects `stream_response` output.

## Example: Ollama Provider

```python
import httpx
import json
from salt_agent.providers.base import ProviderAdapter
from salt_agent.events import TextChunk, ToolUse, AgentError

class OllamaAdapter(ProviderAdapter):
    def __init__(self, model: str = "llama3", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url
        self.last_usage = {"input_tokens": 0, "output_tokens": 0}

    async def stream_response(self, system, messages, tools, max_tokens=4096, temperature=0.0):
        ollama_messages = []
        if system:
            ollama_messages.append({"role": "system", "content": system})
        for msg in messages:
            ollama_messages.append({
                "role": msg["role"],
                "content": msg.get("content", ""),
            })

        try:
            async with httpx.AsyncClient() as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/api/chat",
                    json={"model": self.model, "messages": ollama_messages, "stream": True},
                    timeout=120,
                ) as resp:
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        data = json.loads(line)
                        if "message" in data:
                            text = data["message"].get("content", "")
                            if text:
                                yield TextChunk(text=text)
        except Exception as e:
            yield AgentError(error=str(e), recoverable=False)

    async def quick_query(self, prompt, system="", max_tokens=500):
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/api/chat",
                json={"model": self.model, "messages": messages, "stream": False},
                timeout=30,
            )
            data = resp.json()
            return data.get("message", {}).get("content", "")
```

## Using a Custom Provider

```python
from salt_agent import SaltAgent, AgentConfig

config = AgentConfig(
    working_directory=".",
    auto_mode=True,
)

agent = SaltAgent(config)
# Replace the provider after construction
agent.provider = OllamaAdapter(model="codellama")
```

!!! note
    Currently, `create_agent()` only supports `"anthropic"` and `"openai"` as provider strings. For custom providers, construct `SaltAgent` directly and replace `agent.provider`.

## Tool Format

Your provider receives tools in the format returned by `ToolRegistry.to_anthropic_tools()` (Anthropic format) or `to_openai_tools()` (OpenAI format), depending on the configured provider string. If your custom provider uses a different format, you'll need to convert the tool definitions in your `stream_response` implementation.

## Message Format

Messages arrive in Anthropic format:

```python
# User message
{"role": "user", "content": "Fix the bug in app.py"}

# Assistant message with text
{"role": "assistant", "content": "I'll look at the file..."}

# Assistant message with tool use
{"role": "assistant", "content": [
    {"type": "text", "text": "Let me read the file..."},
    {"type": "tool_use", "id": "call_123", "name": "read", "input": {"file_path": "/app.py"}},
]}

# Tool result
{"role": "user", "content": [
    {"type": "tool_result", "tool_use_id": "call_123", "content": "file content..."},
]}
```

Convert as needed for your backend.
