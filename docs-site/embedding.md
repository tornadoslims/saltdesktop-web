# Embedding SaltAgent in Python Projects

SaltAgent is designed to be embedded as a library. The `create_agent()` factory function is the primary entry point.

## Basic Embedding

```python
from salt_agent import create_agent, AgentConfig

agent = create_agent(
    provider="openai",
    model="gpt-4o",
    api_key="sk-...",
    working_directory="/path/to/project",
    system_prompt="You are a code assistant for this project.",
)

# One-shot execution
import asyncio

async def run():
    async for event in agent.run("Fix the failing tests"):
        if event.type == "text_chunk":
            print(event.text, end="")
        elif event.type == "tool_start":
            print(f"\n[Using {event.tool_name}]")
        elif event.type == "complete":
            print(f"\nDone in {event.turns} turns")

asyncio.run(run())
```

## Event Types

Every call to `agent.run()` returns an `AsyncIterator[AgentEvent]`. The event types are:

| Event | Attributes | When |
|-------|-----------|------|
| `TextChunk` | `text` | Model generates text |
| `ToolStart` | `tool_name`, `tool_input` | Tool begins executing |
| `ToolEnd` | `tool_name`, `result`, `success` | Tool finishes |
| `ToolUse` | `tool_id`, `tool_name`, `tool_input` | Tool call detected in stream |
| `AgentComplete` | `final_text`, `turns`, `tools_used` | Agent finished |
| `AgentError` | `error`, `recoverable` | Error occurred |
| `ContextCompacted` | `old_tokens`, `new_tokens` | Context was compacted |
| `SubagentSpawned` | `mode`, `prompt` | Subagent started |
| `SubagentComplete` | `mode`, `result` | Subagent finished |
| `FileSnapshotted` | `file_path` | File backed up before edit |

## Web Server (FastAPI)

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from salt_agent import create_agent
import json

app = FastAPI()

@app.post("/agent/run")
async def run_agent(prompt: str, provider: str = "openai", model: str = "gpt-4o"):
    agent = create_agent(
        provider=provider,
        model=model,
        working_directory="/app/workspace",
        auto_mode=True,  # skip permission prompts in server context
    )

    async def stream():
        async for event in agent.run(prompt):
            data = {"type": event.type}
            if hasattr(event, "text"):
                data["text"] = event.text
            elif hasattr(event, "tool_name"):
                data["tool_name"] = event.tool_name
            elif hasattr(event, "final_text"):
                data["final_text"] = event.final_text
                data["turns"] = event.turns
            yield f"data: {json.dumps(data)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")
```

## Web Server (Flask)

```python
from flask import Flask, request, Response
from salt_agent import create_agent
import asyncio
import json

app = Flask(__name__)

@app.route("/agent/run", methods=["POST"])
def run_agent():
    prompt = request.json.get("prompt", "")
    agent = create_agent(provider="openai", auto_mode=True)

    def generate():
        loop = asyncio.new_event_loop()
        async def collect():
            results = []
            async for event in agent.run(prompt):
                results.append(event)
            return results

        events = loop.run_until_complete(collect())
        loop.close()
        for event in events:
            data = {"type": event.type}
            if hasattr(event, "text"):
                data["text"] = event.text
            yield f"data: {json.dumps(data)}\n\n"

    return Response(generate(), mimetype="text/event-stream")
```

## Web Server (Django)

```python
# views.py
from django.http import StreamingHttpResponse
from salt_agent import create_agent
import asyncio
import json

def agent_run(request):
    prompt = json.loads(request.body).get("prompt", "")
    agent = create_agent(provider="openai", auto_mode=True)

    def stream():
        loop = asyncio.new_event_loop()
        async def collect():
            results = []
            async for event in agent.run(prompt):
                results.append(event)
            return results
        events = loop.run_until_complete(collect())
        loop.close()
        for event in events:
            data = {"type": event.type}
            if hasattr(event, "text"):
                data["text"] = event.text
            yield f"data: {json.dumps(data)}\n\n"

    return StreamingHttpResponse(stream(), content_type="text/event-stream")
```

## CLI Tool (Build Your Own)

```python
#!/usr/bin/env python3
"""Custom CLI built on SaltAgent."""

import argparse
import asyncio
from salt_agent import create_agent

def main():
    parser = argparse.ArgumentParser(description="My AI Assistant")
    parser.add_argument("prompt", nargs="?", help="Task to perform")
    parser.add_argument("--provider", default="openai")
    parser.add_argument("--model", default="gpt-4o")
    args = parser.parse_args()

    agent = create_agent(
        provider=args.provider,
        model=args.model,
        system_prompt="You are a specialized assistant for my project.",
        auto_mode=True,
    )

    async def run():
        async for event in agent.run(args.prompt):
            if event.type == "text_chunk":
                print(event.text, end="", flush=True)
            elif event.type == "tool_start":
                print(f"\n> {event.tool_name}", flush=True)
        print()

    asyncio.run(run())

if __name__ == "__main__":
    main()
```

## Background Worker (Celery)

```python
from celery import Celery
from salt_agent import create_agent
import asyncio

app = Celery("tasks", broker="redis://localhost:6379/0")

@app.task
def run_agent_task(prompt: str, callback_url: str = ""):
    agent = create_agent(
        provider="openai",
        model="gpt-4o-mini",  # cheaper for background work
        auto_mode=True,
        persist=False,
    )

    loop = asyncio.new_event_loop()

    async def execute():
        result_text = ""
        async for event in agent.run(prompt):
            if event.type == "text_chunk":
                result_text += event.text
            elif event.type == "complete":
                return event.final_text or result_text
        return result_text

    result = loop.run_until_complete(execute())
    loop.close()

    if callback_url:
        import requests
        requests.post(callback_url, json={"result": result})

    return result
```

## Background Worker (RQ)

```python
from redis import Redis
from rq import Queue
from salt_agent import create_agent
import asyncio

redis_conn = Redis()
q = Queue(connection=redis_conn)

def agent_job(prompt: str):
    agent = create_agent(provider="openai", auto_mode=True, persist=False)
    loop = asyncio.new_event_loop()

    async def execute():
        result = ""
        async for event in agent.run(prompt):
            if event.type == "text_chunk":
                result += event.text
        return result

    result = loop.run_until_complete(execute())
    loop.close()
    return result

# Enqueue
job = q.enqueue(agent_job, "Analyze the codebase and write a summary")
```

## Desktop App (Swift/Tauri via subprocess)

```python
# agent_server.py -- run as a subprocess from your desktop app
import sys
import json
import asyncio
from salt_agent import create_agent

async def main():
    agent = create_agent(
        provider="openai",
        auto_mode=True,
        working_directory=sys.argv[1] if len(sys.argv) > 1 else ".",
    )

    # Read prompt from stdin
    prompt = sys.stdin.readline().strip()

    async for event in agent.run(prompt):
        # Write JSON events to stdout for the desktop app to parse
        data = {"type": event.type}
        if hasattr(event, "text"):
            data["text"] = event.text
        elif hasattr(event, "tool_name"):
            data["tool_name"] = event.tool_name
        elif hasattr(event, "final_text"):
            data["final_text"] = event.final_text
        print(json.dumps(data), flush=True)

asyncio.run(main())
```

## Jupyter Notebook

```python
# In a Jupyter cell:
from salt_agent import create_agent

agent = create_agent(
    provider="openai",
    model="gpt-4o-mini",
    working_directory=".",
    auto_mode=True,
)

async for event in agent.run("Explain the main function in app.py"):
    if event.type == "text_chunk":
        print(event.text, end="")
    elif event.type == "tool_start":
        print(f"\n[{event.tool_name}]", end="")
```

## Custom Tools

Register your own tools to give the agent new capabilities:

```python
from salt_agent import Tool, ToolDefinition, ToolParam, ToolRegistry, create_agent

class DatabaseQueryTool(Tool):
    def definition(self):
        return ToolDefinition(
            name="db_query",
            description="Query the PostgreSQL database",
            params=[
                ToolParam("sql", "string", "SQL query to execute"),
                ToolParam("limit", "integer", "Max rows to return", required=False),
            ],
        )

    def execute(self, **kwargs):
        import psycopg2
        conn = psycopg2.connect("dbname=mydb")
        cur = conn.cursor()
        sql = kwargs["sql"]
        limit = kwargs.get("limit", 100)
        cur.execute(f"{sql} LIMIT {limit}")
        rows = cur.fetchall()
        conn.close()
        return str(rows)

class SlackPostTool(Tool):
    def definition(self):
        return ToolDefinition(
            name="slack_post",
            description="Post a message to a Slack channel",
            params=[
                ToolParam("channel", "string", "Channel name (e.g., #general)"),
                ToolParam("message", "string", "Message text to post"),
            ],
        )

    def execute(self, **kwargs):
        import requests
        requests.post("https://slack.com/api/chat.postMessage", json={
            "channel": kwargs["channel"],
            "text": kwargs["message"],
        }, headers={"Authorization": f"Bearer {SLACK_TOKEN}"})
        return f"Posted to {kwargs['channel']}"

# Create agent with custom tools
registry = ToolRegistry()
registry.register(DatabaseQueryTool())
registry.register(SlackPostTool())

agent = create_agent(provider="openai")
# Merge custom tools into the agent's default registry
for name in registry.names():
    agent.tools.register(registry.get(name))
```

## Custom Providers

For other LLM backends (local models, custom APIs):

```python
from salt_agent.providers.base import ProviderAdapter
from salt_agent.events import TextChunk, ToolUse, AgentError

class OllamaAdapter(ProviderAdapter):
    def __init__(self, model: str = "llama3"):
        self.model = model
        self.last_usage = {"input_tokens": 0, "output_tokens": 0}

    async def stream_response(self, system, messages, tools, max_tokens=4096, temperature=0.0):
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.post("http://localhost:11434/api/chat", json={
                "model": self.model,
                "messages": [{"role": "system", "content": system}] + messages,
                "stream": True,
            })
            async for line in resp.aiter_lines():
                import json
                data = json.loads(line)
                if "message" in data:
                    yield TextChunk(text=data["message"].get("content", ""))
```

## Hook Integration

Track agent activity in your application:

```python
agent = create_agent(provider="openai")

# Log all tool usage
agent.hooks.on("post_tool_use", lambda data:
    print(f"Agent used {data['tool_name']}: {data.get('result', '')[:100]}")
)

# Notify when done
agent.hooks.on("on_complete", lambda data:
    send_notification(f"Agent finished: {data.get('turns', 0)} turns")
)

# Block specific tools
from salt_agent import HookResult

def block_dangerous_tools(data):
    if data["tool_name"] == "bash":
        cmd = data["tool_input"].get("command", "")
        if "rm" in cmd:
            return HookResult(action="block", reason="rm commands are blocked")
    return None

agent.hooks.on("pre_tool_use", block_dangerous_tools)

# HTTP webhook for monitoring
agent.hooks.register_http_hook(
    "post_tool_use",
    "https://my-app.com/webhooks/agent-activity"
)

# Shell hook for custom processing
agent.hooks.register_shell_hook(
    "on_complete",
    "python /path/to/my_handler.py"
)
```

## State Observation

Monitor agent state in real-time:

```python
agent = create_agent(provider="openai")

# Subscribe to state changes
def on_state_change(field_name, new_value):
    print(f"State: {field_name} = {new_value}")

agent.state.subscribe(on_state_change)

# Check state at any time
snapshot = agent.state.snapshot()
print(f"Status: {snapshot['status']}")
print(f"Turn: {snapshot['turn_count']}")
print(f"Cost: ${snapshot['total_cost']:.4f}")
```

## MCP Integration

Auto-discover MCP servers from a `.mcp.json` file:

```python
# Create .mcp.json in your project:
# {
#     "mcpServers": {
#         "postgres": {
#             "command": "npx",
#             "args": ["-y", "@modelcontextprotocol/server-postgres", "postgresql://localhost/mydb"]
#         },
#         "filesystem": {
#             "command": "npx",
#             "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/files"]
#         }
#     }
# }

agent = create_agent(
    working_directory="/my/project",  # will find .mcp.json here
    enable_mcp=True,
)
# Agent now has postgres and filesystem tools automatically
```

## Session Persistence and Resume

```python
from salt_agent import create_agent, SaltAgent

# First session
agent = create_agent(provider="openai", persist=True)
async for event in agent.run("Start building the API"):
    pass
session_id = agent.persistence.session_id
print(f"Session: {session_id}")

# Later: resume the session
agent2, messages, system = SaltAgent.resume(session_id)
async for event in agent2.run("Continue where we left off"):
    pass
```

## Multi-Agent Orchestration via Tasks

```python
agent = create_agent(provider="openai")

async def orchestrate():
    # The coordinator creates background tasks
    async for event in agent.run(
        "Create three background tasks: "
        "1) Analyze the test coverage "
        "2) Find all TODO comments in the codebase "
        "3) Check for security vulnerabilities in dependencies"
    ):
        if event.type == "text_chunk":
            print(event.text, end="")

import asyncio
asyncio.run(orchestrate())
```

## Coordinator Mode

Strip write/execute tools and use only delegation:

```python
agent = create_agent(
    provider="openai",
    coordinator_mode=True,  # only read + delegation tools
)

# This agent can read code, create tasks, and send messages,
# but cannot write files or run bash commands directly.
```

## Plugin System

Create a reusable plugin:

```python
# my_plugin.py
from salt_agent import SaltPlugin, Tool, ToolDefinition, ToolParam

class MyDatabaseTool(Tool):
    def definition(self):
        return ToolDefinition(
            name="my_db",
            description="Query my database",
            params=[ToolParam("query", "string", "SQL query")],
        )
    def execute(self, **kwargs):
        return "query result..."

class MyPlugin(SaltPlugin):
    def name(self):
        return "my-plugin"

    def tools(self):
        return [MyDatabaseTool()]

    def hooks(self):
        return [
            ("post_tool_use", lambda data: print(f"Tool used: {data['tool_name']}")),
        ]

    def prompts(self):
        return ["Always check the database before making assumptions."]
```

Load it:

```python
agent = create_agent(
    provider="openai",
    plugin_dirs=["/path/to/plugins"],
)
```

Or install via pip entry points:

```toml
# pyproject.toml
[project.entry-points."salt_agent.plugins"]
my_plugin = "my_package.plugin:MyPlugin"
```

## Skill-Based Automation

```python
# Create a skill directory
# ~/.s_code/skills/deploy/SKILL.md:
# ---
# name: deploy
# description: Deploy the application to production
# ---
# Follow these steps to deploy:
# 1. Run tests: `pytest tests/ -v`
# 2. Build: `docker build -t myapp .`
# 3. Push: `docker push myapp:latest`
# 4. Deploy: `kubectl rollout restart deployment/myapp`

agent = create_agent(provider="openai")
# The agent can now use the "deploy" skill via the skill tool
```

## Configuration Reference

All `create_agent()` / `AgentConfig` parameters:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `provider` | str | `"anthropic"` | LLM provider |
| `model` | str | `""` | Model name (empty = provider default) |
| `api_key` | str | `""` | API key (empty = read from env) |
| `max_turns` | int | `30` | Maximum turns per run |
| `max_tokens` | int | `4096` | Max output tokens per turn |
| `temperature` | float | `0.0` | Sampling temperature |
| `working_directory` | str | `"."` | Working directory for tools |
| `system_prompt` | str | `""` | Additional system prompt text |
| `context_window` | int | `200000` | Context window size (tokens) |
| `bash_timeout` | int | `30` | Bash command timeout (seconds) |
| `max_tool_result_chars` | int | `10000` | Max tool result length |
| `persist` | bool | `True` | Enable session persistence |
| `session_id` | str | `""` | Session ID (auto-generated if empty) |
| `sessions_dir` | str | `""` | Sessions directory |
| `memory_dir` | str | `""` | Memory directory |
| `include_web_tools` | bool | `True` | Include WebFetch and WebSearch |
| `web_extractor` | str | `"trafilatura"` | HTML extractor backend |
| `auto_mode` | bool | `False` | Skip all permission prompts |
| `fallback_model` | str | `""` | Fallback model on failure |
| `plan_mode` | bool | `False` | Require plan before execution |
| `coordinator_mode` | bool | `False` | Delegation-only mode |
| `include_git_tools` | bool | `True` | Include git tools |
| `plugin_dirs` | list | `[]` | Plugin directories |
| `enable_mcp` | bool | `True` | Enable MCP server discovery |
| `mcp_config_path` | str | `""` | Override .mcp.json location |
| `skill_dirs` | list | `[]` | Additional skill directories |
| `max_budget_usd` | float | `0.0` | Budget limit (0 = unlimited) |
| `show_suggestions` | bool | `False` | Show follow-up suggestions |
| `bash_sandbox` | BashSandbox | `None` | Bash execution sandbox config |
| `permission_rules` | list | `None` | Custom permission rules |
| `permission_ask_callback` | callable | `None` | Permission prompt callback |
