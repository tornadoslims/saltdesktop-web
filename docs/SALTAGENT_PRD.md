# SaltAgent — Product Requirements Document

**Version:** 1.0
**Date:** 2026-03-30
**Status:** Draft
**Owner:** Jim

---

## 1. Vision & Goals

### Why We Are Building This

Salt Desktop needs a general-purpose agent execution engine. Today, tools like Claude Code, Codex, and Gemini CLI are interactive terminals — not libraries. They can't be embedded in another application, extended with custom tools, or controlled programmatically.

SaltAgent is Salt Desktop's answer: a fully extensible, embeddable Python agent engine. It calls LLM provider APIs directly (Anthropic, OpenAI, Google), executes tools in-process, streams events back to the UI, and manages its own context window. No external binaries. No subprocess wrangling. No parsing terminal output.

While Salt Desktop's primary use case is building and deploying AI agents (the "Build It" phase), SaltAgent itself is general-purpose. It can be configured with any set of tools for any task — coding, research, analysis, data processing, web browsing. The tool registry is extensible: add a tool, and the agent can use it.

### What Success Looks Like

1. A user clicks "Build It" on a 5-component mission graph.
2. Five SaltAgent instances spin up (one per component, via ClawTeam worktrees).
3. Each agent creates `contract.py`, `main.py`, and `test_main.py` with passing tests.
4. The UI graph lights up in real-time -- yellow while building, green when tests pass, red on failure.
5. Average build time per component: under 3 minutes.
6. Test pass rate on first attempt: over 80%.
7. The user never sees a terminal, a PID, a token count, or an error traceback. They see "Your AI is building the Gmail Connector" and watch it happen.

### Key Architectural Principles

1. **General-purpose engine, purpose-built tools.** SaltAgent is a generic agent loop. What makes it specific to a task is the tool set you give it. Building components? Give it read/write/edit/bash. Researching APIs? Give it web_fetch/web_search. Analyzing data? Give it read/bash/python_eval.

2. **Extensible tool registry.** Any Python function can become a tool. Define the schema, register it, the LLM can use it. This is how Salt Desktop adds connector-specific tools (Gmail, Slack, etc.) and how third parties could extend the platform.

3. **Two engines in Salt Desktop.** SaltAgent handles the build phase (writing code, running tests). RunnerAgent (`jb_pipeline.py`) handles the run phase (executing deployed pipelines). They're separate because build needs an LLM loop and run doesn't.

### What SaltAgent Is NOT

- **Not tied to one task.** It's not "just a code builder." It's a general-purpose agent engine that Salt Desktop configures for different jobs.
- **Not a framework.** It is a library. You instantiate it, call `run()`, iterate over events.
- **Not user-facing.** The user never interacts with SaltAgent directly. They interact with Salt Desktop's UI. SaltAgent is the invisible engine.

---

## 2. Architecture Overview

SaltAgent's architecture is derived from patterns proven in Claude Code, the KODE Agent SDK, and learn-claude-code, simplified for the specific use case of building Salt Desktop components.

```
SaltAgent
  |
  +-- AgentLoop
  |     |-- ContextAssembler (system prompt, component spec, mission context, credentials, library)
  |     |-- ContextPressureManager (budgeting, summarization, compaction, compression)
  |     |-- ToolExecutor (parallel tool execution with sandboxing)
  |     +-- ErrorRecovery (test retry, import fix, rate limit backoff, compaction retry)
  |
  +-- ToolRegistry (BUILD tools only -- no runtime tools)
  |     |-- read_file, write_file, edit_file (filesystem)
  |     |-- bash (sandboxed shell execution)
  |     |-- glob, grep (search)
  |     |-- list_files (directory listing)
  |     |-- check_credentials, read_credentials (CredentialStore -- build-phase only)
  |     |-- run_tests (pytest runner)
  |     +-- report_build_progress (UI event emission)
  |
  +-- ProviderAdapter
  |     |-- AnthropicAdapter (Claude -- primary)
  |     |-- OpenAIAdapter (GPT -- alternative)
  |     +-- GeminiAdapter (Gemini -- alternative)
  |
  +-- EventBus
  |     |-- Progress channel: agent_thinking, tool_start, tool_end, file_written, progress
  |     |-- Build channel: test_started, test_passed, test_failed, component_built
  |     +-- Lifecycle channel: error, complete, checkpoint_saved, context_compacted
  |
  +-- Persistence
        |-- Checkpoint (save before each API call)
        |-- Transcript (full conversation log)
        +-- Resume (hydrate from checkpoint on crash)
```

---

## 3. The Agent Loop

### Core Loop

The agent loop is a synchronous iteration: assemble context, call the LLM, check for tool calls, execute tools, feed results back, repeat. The loop terminates when the model stops requesting tools (it believes the task is complete), when `max_turns` is reached, or when a fatal unrecoverable error occurs.

### Pseudocode

```python
class SaltAgent:
    async def run(self, prompt: str) -> AsyncIterator[AgentEvent]:
        messages = self.context_assembler.build_initial_messages(prompt)
        turn = 0

        while turn < self.config.max_turns:
            turn += 1

            # 1. Manage context pressure
            messages = self.pressure_manager.reduce(messages)

            # 2. Persist checkpoint (crash safety)
            await self.persistence.save_checkpoint(messages, turn)

            # 3. Call the LLM
            try:
                response = await self.provider.create(
                    messages=messages,
                    system=self.context_assembler.system_prompt(),
                    tools=self.tool_registry.schemas(),
                )
            except ContextTooLongError:
                messages = await self.pressure_manager.emergency_compact(messages)
                continue
            except RateLimitError as e:
                await self._backoff(e.retry_after)
                continue

            # 4. Append assistant response
            assistant_message = response.to_message()
            messages.append(assistant_message)
            yield AgentEvent(type="agent_thinking", content=response.text)

            # 5. Check for tool calls
            tool_calls = response.tool_calls
            if not tool_calls:
                # Model is done
                yield AgentEvent(type="complete", result=response.text)
                return

            # 6. Execute tools
            tool_results = []
            for call in tool_calls:
                yield AgentEvent(type="tool_start", tool_name=call.name, input=call.input)

                result = await self.tool_executor.run(call)
                tool_results.append(result)

                yield AgentEvent(type="tool_end", tool_name=call.name, output=result.output)

                # Emit specific events for UI updates
                if call.name == "write_file":
                    yield AgentEvent(type="file_written", path=call.input["path"])
                elif call.name == "run_tests":
                    if result.success:
                        yield AgentEvent(type="test_passed", path=call.input["path"])
                    else:
                        yield AgentEvent(type="test_failed", path=call.input["path"],
                                         error=result.output)

            # 7. Append tool results as user message
            messages.append({
                "role": "user",
                "content": [r.to_content_block() for r in tool_results],
            })

        # Max turns reached
        yield AgentEvent(type="error", message=f"Max turns ({self.config.max_turns}) reached")
```

### How Messages Are Assembled

Each turn, the messages list contains:

1. **System prompt** (injected via the `system` parameter, not in messages).
2. **User message #1**: The initial prompt with component spec, mission context, and instructions.
3. **Assistant message #1**: The model's first response (may include tool calls).
4. **User message #2**: Tool results from message #1's tool calls.
5. ... continuing for each turn.

The system prompt is rebuilt every turn (not cached) because it includes dynamic state like available credentials and build output from previous turns.

### How the Loop Terminates

- **Natural completion**: The model responds with text only (no tool calls). This is the expected path -- the model writes the code, runs the tests, sees them pass, and reports "done."
- **Max turns**: Safety limit (default 30). Prevents runaway loops.
- **Fatal error**: Unrecoverable provider error after retries are exhausted.
- **Cancellation**: External signal from JBCP (e.g., user cancels the mission).

### Error Handling Inside the Loop

Errors are caught and retried inside the loop. Callers never implement retry logic.

| Error | Response |
|-------|----------|
| `ContextTooLongError` | Emergency compact, retry |
| `RateLimitError` | Exponential backoff, retry |
| `MaxOutputReachedError` | Increase max_tokens, retry |
| Tool timeout | Return error string to model, let it adapt |
| Tool permission denied | Return error string to model |

---

## 4. Tool Definitions

### Core Tools

#### `read_file`

Read file content from the filesystem.

```python
read_file(
    path: str,          # Absolute path to the file. Required.
    offset: int = 0,    # Line number to start reading from (0-indexed).
    limit: int = 2000,  # Maximum number of lines to read.
) -> str               # File content with line numbers (cat -n format).
```

**Constraints:**
- Path must be within the component working directory or an explicitly allowed path.
- Returns an error string if the file does not exist.
- Binary files return an error.

**Example usage by the model:**
```
read_file(path="/components/gmail_connector/main.py")
```

---

#### `write_file`

Create a new file or overwrite an existing file.

```python
write_file(
    path: str,       # Absolute path to the file. Required.
    content: str,    # Full file content to write. Required.
) -> str            # Confirmation message ("File written: {path}, {lines} lines").
```

**Constraints:**
- Path must be within the component working directory.
- For existing files, the model MUST have called `read_file` on that path earlier in the session. The tool executor tracks which files have been read and rejects blind overwrites. This prevents the model from destroying content it has not seen.
- Creates parent directories automatically (`mkdir -p`).

**Example:**
```
write_file(
    path="/components/gmail_connector/contract.py",
    content="from dataclasses import dataclass\n\n@dataclass\nclass Config:\n    ..."
)
```

---

#### `edit_file`

Perform an exact string replacement in an existing file.

```python
edit_file(
    path: str,             # Absolute path to the file. Required.
    old_string: str,       # The exact text to find and replace. Required.
    new_string: str,       # The replacement text. Required.
    replace_all: bool = False,  # If True, replace all occurrences. Default: first only.
) -> str                  # Confirmation message or error.
```

**Constraints:**
- The model MUST have called `read_file` on this path earlier in the session. Enforced by the tool executor.
- `old_string` must be unique in the file (unless `replace_all=True`). If it appears multiple times, the edit fails with an error message instructing the model to provide more surrounding context.
- `old_string` must be different from `new_string`.

**Why string replacement instead of line-based diffs:**
- Survives line number drift when multiple edits happen in sequence.
- Forces the model to read and understand surrounding context before editing.
- Prevents blind edits to code the model has not seen.

**Example:**
```
edit_file(
    path="/components/gmail_connector/main.py",
    old_string="def run(config):\n    pass",
    new_string="def run(config):\n    service = build_gmail_service(config.credentials)\n    return fetch_emails(service, config.max_results)"
)
```

---

#### `bash`

Execute a shell command and return stdout and stderr.

```python
bash(
    command: str,          # The shell command to execute. Required.
    timeout: int = 120000, # Timeout in milliseconds. Default 120s, max 600s.
) -> str                  # Combined stdout + stderr output, truncated at 30,000 characters.
```

**Constraints:**
- Commands execute in the component working directory.
- No `sudo`. No `rm -rf /`. No `shutdown`, `reboot`, or fork bombs. A blocklist of dangerous commands is enforced before execution.
- Network access is blocked except through credential-backed tools. The sandbox uses a restricted PATH and blocks raw `curl`/`wget` to external URLs not in the credential allowlist.
- Timeout default is 120 seconds. Maximum is 600 seconds.
- Output is truncated at 30,000 characters. If truncated, the last line indicates `[output truncated at 30,000 chars]`.
- Working directory is set to the component directory.

**Example:**
```
bash(command="python -m pytest test_main.py -v", timeout=60000)
```

---

#### `glob`

Find files matching a glob pattern.

```python
glob(
    pattern: str,          # Glob pattern (e.g., "**/*.py", "*.json"). Required.
    path: str = ".",       # Directory to search in. Default: component working directory.
) -> str                  # Newline-separated list of matching file paths, sorted by modification time.
```

**Constraints:**
- Path must be within the component working directory or allowed paths.
- Returns at most 500 results.

**Example:**
```
glob(pattern="**/*.py", path="/components/gmail_connector/")
```

---

#### `grep`

Search file contents using regular expressions.

```python
grep(
    pattern: str,                      # Regex pattern to search for. Required.
    path: str = ".",                    # File or directory to search in.
    type: str | None = None,           # File type filter (e.g., "py", "json").
    include: str | None = None,        # Glob pattern to filter files (e.g., "*.py").
    context: int = 0,                  # Lines of context before and after each match.
    case_insensitive: bool = False,    # Case-insensitive search.
) -> str                              # Matching lines with file paths and line numbers.
```

**Constraints:**
- Path must be within allowed boundaries.
- Results truncated at 200 matches.
- Uses ripgrep-compatible regex syntax.

**Example:**
```
grep(pattern="def run\\(", type="py", path="/components/")
```

---

#### `list_files`

List the contents of a directory.

```python
list_files(
    path: str,    # Absolute path to the directory. Required.
) -> str         # Newline-separated list of entries with type indicators (/ for dirs).
```

**Constraints:**
- Path must be within allowed boundaries.
- Non-recursive (one level only).

---

### Build-Specific Tools

#### `check_credentials`

Check whether credentials exist for a given service. Used during BUILD to decide whether the component can reference real credential fields or needs placeholder logic.

```python
check_credentials(
    service_id: str,    # The service identifier (e.g., "gmail", "telegram", "slack"). Required.
) -> str               # "available" or "not_configured".
```

**Constraints:**
- Read-only. Does not reveal credential values.
- Used by the agent to decide whether a component can be built with real credentials or needs mock/placeholder logic.

**Example:**
```
check_credentials(service_id="gmail")
# Returns: "available"
```

---

#### `read_credentials`

Read credential values for a configured service. Used during BUILD so the agent knows which config fields to reference (it never hardcodes values).

```python
read_credentials(
    service_id: str,    # The service identifier. Required.
) -> str               # JSON string of credential key-value pairs.
```

**Constraints:**
- Returns credentials only for services that the mission has been authorized to access.
- Read-only. The agent cannot write, modify, or delete credentials.
- Credentials are injected into the component's `Config` dataclass, not hardcoded in source files. The agent is instructed to use `config.{credential_field}` references, never literal values.
- Returns an error if the service is not configured.

**Example:**
```
read_credentials(service_id="gmail")
# Returns: '{"client_id": "...", "client_secret": "...", "refresh_token": "..."}'
```

---

#### `run_tests`

Run pytest on a file or directory and return structured results.

```python
run_tests(
    path: str,             # Path to test file or directory. Required.
    verbose: bool = True,  # Include full output. Default True.
) -> str                  # Pytest output including pass/fail counts, error messages, and tracebacks.
```

**Constraints:**
- Runs in the component working directory.
- Timeout: 120 seconds.
- Returns full pytest output including tracebacks for failures.
- Internally calls `python -m pytest {path} -v` (or `-q` if not verbose).

**Example:**
```
run_tests(path="/components/gmail_connector/test_main.py")
```

---

#### `report_build_progress`

Emit a human-readable build progress message to the UI. Build-phase only.

```python
report_build_progress(
    message: str,    # Progress message (e.g., "Writing authentication logic"). Required.
) -> str            # "ok"
```

**Constraints:**
- No side effects beyond emitting an event.
- The message is forwarded to the event bus as an `AgentEvent(type="progress", message=...)`.
- The UI translates this into activity feed text: "Your AI: Writing authentication logic."

**Example:**
```
report_build_progress(message="Implementing OAuth2 flow for Gmail API")
```

**Note on tools SaltAgent does NOT have:** SaltAgent does not have runtime tools like `send_slack_message`, `read_gmail`, or `check_api`. Those are not tools — they are API calls that live inside component `run()` functions. SaltAgent WRITES the code that makes those calls. It does not make them itself.

---

## 5. Context Assembly

SaltAgent builds context for each turn from multiple sources. Context is assembled into the system prompt (static per session, rebuilt per turn) and the initial user message (the task prompt).

### System Prompt Structure

```
You are a coding agent building a Salt Desktop component. Your job is to produce
working, tested code that satisfies the component contract.

## Rules
- Write contract.py FIRST (typed dataclasses for Config, Input, Output).
- Write main.py with `def run(config, input_data, summary_chain) -> dict`.
- Write test_main.py with pytest unit tests.
- Run tests after writing code. If tests fail, read the error, fix the code, re-run.
- You have up to 3 retry cycles for test failures.
- Do NOT over-engineer. Write the simplest code that satisfies the contract.
- Do NOT add features beyond the specification.
- Do NOT hardcode credentials. Use config.{field} references.
- After completing the component, output a DECISIONS section listing significant
  choices you made and why.

## Component Specification
Name: {component_name}
Type: {component_type} (CONNECTOR | PROCESSOR | AI | OUTPUT | SCHEDULER)
Description: {component_description}

### Contract
Input Type: {input_type}
Input Schema:
{input_schema_json}

Output Type: {output_type}
Output Schema:
{output_schema_json}

Config Fields:
{config_fields_json}

## Mission Context
Goal: {mission_goal}
Overall Architecture: {component_graph_summary}
This component's role: {role_in_graph}
Upstream components: {upstream_names_and_output_types}
Downstream components: {downstream_names_and_input_types}

## Available Credentials
{list_of_configured_services_with_field_names}

## Existing Component Library
{list_of_previously_built_components_with_types_and_contracts}
(Reuse patterns from these if applicable. Do not copy code -- reference the approach.)

## Working Directory
{component_directory_path}
```

### Dynamic Context (Updated Per Turn)

These elements are injected into the system prompt or appended to tool results as system reminders:

- **Build output**: If tests were run in the previous turn, their results are summarized.
- **File context**: A list of files the agent has read or written in this session, with line counts.
- **Error history**: If the agent failed a test and is retrying, the previous error is summarized.

### Context Budget

| Source | Approximate Tokens | Priority |
|--------|-------------------|----------|
| System prompt (static) | 800 | Required |
| Component specification | 300-600 | Required |
| Mission context | 200-400 | Required |
| Credentials list | 50-100 | Required |
| Component library | 200-1000 | Desirable (compress if needed) |
| Build output | 200-2000 | Required when retrying |
| File context | Variable | Managed by pressure system |
| Conversation history | Variable | Managed by pressure system |

---

## 6. Context Pressure Management

SaltAgent uses a 4-layer progressive context reduction strategy. Layers are applied in order, with each layer stronger than the last. On a typical 30-turn component build, only Layers 1-2 will activate. Layers 3-4 handle edge cases.

### Layer 1: Tool Result Budgeting

**When:** Every turn, before the API call.
**What:** Truncate tool results that exceed 10,000 characters.

```python
def budget_tool_results(messages: list) -> list:
    for msg in messages:
        if msg["role"] == "user":
            for block in msg.get("content", []):
                if block.get("type") == "tool_result":
                    text = block.get("content", "")
                    if len(text) > 10_000:
                        # Keep first 4,000 and last 4,000 chars
                        block["content"] = (
                            text[:4000]
                            + "\n\n[... truncated ...]\n\n"
                            + text[-4000:]
                        )
    return messages
```

**Why this matters:** `bash` output from test runs and `read_file` on large files can produce enormous tool results. Without budgeting, a single test failure with a long traceback can consume 30% of the context window.

### Layer 2: File Content Summarization

**When:** Token count exceeds 60% of the context window.
**What:** Replace old `read_file` results (not the most recent read of each file) with a one-line summary.

```python
# Before:
{"type": "tool_result", "content": "1\timport os\n2\timport json\n3\t...500 lines..."}

# After:
{"type": "tool_result", "content": "[Previously read: main.py, 500 lines]"}
```

The most recent read of each unique file path is preserved in full. Only earlier reads of the same file are summarized. This ensures the model always has the current state of files it is working with.

### Layer 3: Auto-Compaction

**When:** Token count exceeds 80% of the context window.
**What:** Generate a structured summary of the entire conversation so far, then replace all messages with the summary as a single user message.

The compaction prompt asks the model to produce:
```
1. Task overview (what is being built, success criteria)
2. Current state (files created, tests run, what works, what does not)
3. Important discoveries (errors encountered, approaches tried, decisions made)
4. Next steps (what remains to be done)
5. Code snippets to preserve (any partially-written code that must not be lost)
```

**Post-compaction restoration:** After compacting, the system reinjects:
- The component specification (from the system prompt -- always present).
- The most recent content of every file the agent has written (re-read from disk).
- The last test output (if any).

This ensures the agent does not lose track of its own work after compaction.

### Layer 4: Turn Compression

**When:** Token count exceeds 80% AND the conversation has more than 15 turns.
**What:** Merge sequential tool call/result pairs from early turns into single summary blocks.

```python
# Before: 5 separate read_file calls from turns 2-4
# After: "[Turns 2-4: Read contract.py (45 lines), main.py (120 lines), test_main.py (80 lines)]"
```

This is the most aggressive reduction and only fires in unusually long sessions (complex components with multiple retry cycles).

---

## 7. Multi-Provider Support

SaltAgent supports three LLM providers through a common adapter interface.

### Provider Adapter Interface

```python
from dataclasses import dataclass
from typing import AsyncIterator

@dataclass
class ModelResponse:
    text: str                           # The model's text output
    tool_calls: list[ToolCall]          # Requested tool invocations
    input_tokens: int                   # Tokens consumed by the prompt
    output_tokens: int                  # Tokens generated
    stop_reason: str                    # "end_turn", "tool_use", "max_tokens"

    def to_message(self) -> dict:
        """Convert to the messages API format for appending to conversation."""
        ...

class ProviderAdapter:
    """Abstract base for LLM provider adapters."""

    async def create(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
    ) -> ModelResponse:
        """Send a completion request and return the full response."""
        ...

    def context_window_size(self) -> int:
        """Return the model's context window size in tokens."""
        ...

    def estimate_tokens(self, messages: list[dict]) -> int:
        """Estimate token count for a message list."""
        ...
```

### Anthropic Adapter (Primary)

Uses the `anthropic` Python SDK directly.

```python
import anthropic

class AnthropicAdapter(ProviderAdapter):
    def __init__(self, model: str = "claude-sonnet-4-20250514", api_key: str = None):
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self.model = model

    async def create(self, messages, system, tools) -> ModelResponse:
        response = await self.client.messages.create(
            model=self.model,
            system=system,
            messages=messages,
            tools=self._convert_tools(tools),
            max_tokens=8192,
        )
        return self._parse_response(response)
```

**Tool schema format (Anthropic):**
```json
{
    "name": "read_file",
    "description": "Read file content from the filesystem.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Absolute path to the file."},
            "offset": {"type": "integer", "description": "Line to start from.", "default": 0},
            "limit": {"type": "integer", "description": "Max lines to read.", "default": 2000}
        },
        "required": ["path"]
    }
}
```

### OpenAI Adapter (Alternative)

Uses the `openai` Python SDK.

```python
import openai

class OpenAIAdapter(ProviderAdapter):
    def __init__(self, model: str = "gpt-4.1", api_key: str = None):
        self.client = openai.AsyncOpenAI(api_key=api_key)
        self.model = model

    async def create(self, messages, system, tools) -> ModelResponse:
        # OpenAI uses "system" role in messages, not a separate parameter
        oai_messages = [{"role": "system", "content": system}] + messages
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=self._convert_messages(oai_messages),
            tools=self._convert_tools(tools),
            max_completion_tokens=8192,  # Note: OpenAI uses max_completion_tokens, not max_tokens
        )
        return self._parse_response(response)
```

**Key differences from Anthropic:**
- System prompt goes in messages as `{"role": "system", ...}`, not a separate parameter.
- Uses `max_completion_tokens` instead of `max_tokens`.
- Tool calls are in `response.choices[0].message.tool_calls` (array of objects with `function.name` and `function.arguments` as a JSON string).
- Tool results use role `"tool"` with a `tool_call_id` field.
- `stop_reason` is called `finish_reason` and uses `"stop"` instead of `"end_turn"`.

**Tool schema format (OpenAI):**
```json
{
    "type": "function",
    "function": {
        "name": "read_file",
        "description": "Read file content from the filesystem.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to the file."},
                "offset": {"type": "integer", "description": "Line to start from."},
                "limit": {"type": "integer", "description": "Max lines to read."}
            },
            "required": ["path"]
        }
    }
}
```

### Gemini Adapter (Alternative)

Uses the `google-genai` Python SDK.

```python
from google import genai

class GeminiAdapter(ProviderAdapter):
    def __init__(self, model: str = "gemini-2.5-pro", api_key: str = None):
        self.client = genai.Client(api_key=api_key)
        self.model = model

    async def create(self, messages, system, tools) -> ModelResponse:
        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=self._convert_messages(messages),
            config=genai.types.GenerateContentConfig(
                system_instruction=system,
                tools=self._convert_tools(tools),
                max_output_tokens=8192,
            ),
        )
        return self._parse_response(response)
```

**Key differences from Anthropic:**
- Uses `contents` instead of `messages`.
- System prompt is `system_instruction` in config.
- Tool declarations use `function_declarations` with a different schema structure.
- Tool results use `function_response` parts.
- Uses `max_output_tokens` instead of `max_tokens`.

### Model Selection

Default: Anthropic Claude Sonnet (best balance of coding quality and speed for component building).

Users can override in Salt Desktop settings:
- **Global default**: Applied to all new builds.
- **Per-mission override**: Set during planning or on the mission settings panel.

Available models (initial set):

| Provider | Model | Recommended For |
|----------|-------|-----------------|
| Anthropic | `claude-sonnet-4-20250514` | Default. Fast, good at coding. |
| Anthropic | `claude-opus-4-20250514` | Complex components, tricky logic. |
| OpenAI | `gpt-4.1` | Alternative if user prefers OpenAI. |
| Google | `gemini-2.5-pro` | Alternative if user prefers Gemini. |

---

## 8. Event Streaming

SaltAgent reports progress to the UI in real-time through an async event stream. Every call to `agent.run()` returns an `AsyncIterator[AgentEvent]` that the caller consumes.

### Event Types

```python
from dataclasses import dataclass, field
from typing import Any
from enum import Enum

class EventType(Enum):
    # Progress events (what the agent is doing)
    AGENT_THINKING = "agent_thinking"     # Model is generating text
    TOOL_START = "tool_start"             # Tool execution begins
    TOOL_END = "tool_end"                 # Tool execution completes
    FILE_WRITTEN = "file_written"         # A file was created or modified
    PROGRESS = "progress"                 # Human-readable progress message

    # Build events (component lifecycle)
    TEST_STARTED = "test_started"         # pytest is running
    TEST_PASSED = "test_passed"           # All tests passed
    TEST_FAILED = "test_failed"           # One or more tests failed
    COMPONENT_BUILT = "component_built"   # Component is complete with passing tests

    # Lifecycle events (agent state)
    ERROR = "error"                       # Recoverable or fatal error
    COMPLETE = "complete"                 # Agent finished successfully
    CHECKPOINT_SAVED = "checkpoint_saved" # State persisted for resume
    CONTEXT_COMPACTED = "context_compacted" # Context window was compacted

@dataclass
class AgentEvent:
    type: EventType
    timestamp: str = ""                   # ISO 8601 UTC
    component_id: str = ""                # Which component this relates to
    tool_name: str = ""                   # For TOOL_START/TOOL_END
    path: str = ""                        # For FILE_WRITTEN, TEST_*
    message: str = ""                     # Human-readable description
    content: str = ""                     # Raw content (model text, tool output)
    error: str = ""                       # For ERROR, TEST_FAILED
    result: Any = None                    # For COMPLETE (final output)
    metadata: dict = field(default_factory=dict)  # Additional data
```

### Event to UI Mapping

| Event | Graph Node Effect | Activity Feed Text | Sidebar Text |
|-------|-------------------|-------------------|--------------|
| `TOOL_START(write_file)` | Node turns yellow, shows "writing..." | "Writing gmail_connector.py" | "building..." |
| `TOOL_END(write_file)` | Progress bar increments | "Wrote gmail_connector.py (145 lines)" | -- |
| `TEST_STARTED` | Node shows test indicator | "Running tests..." | "testing..." |
| `TEST_PASSED` | Node turns green | "All tests passed" | "built" |
| `TEST_FAILED` | Node shows warning (stays yellow) | "Tests failed, retrying..." | "fixing..." |
| `FILE_WRITTEN(contract.py)` | -- | "Defined component contract" | -- |
| `PROGRESS` | -- | Whatever the agent wrote | -- |
| `ERROR` | Node turns red | Error message | "failed" |
| `COMPLETE` | Node turns green, marked as built | "Gmail Connector is ready" | "built" |

### Integration with JBCP Event Bus

SaltAgent events are forwarded to JBCP's event system for persistence and SSE streaming to the frontend:

```python
# In JBCP orchestrator (the caller)
async for event in agent.run(prompt):
    # Forward to JBCP event bus for SSE streaming
    jb_events.append({
        "type": f"saltagent.{event.type.value}",
        "component_id": component_id,
        "mission_id": mission_id,
        "data": event.to_dict(),
    })

    # Update component status in JBCP
    if event.type == EventType.TOOL_START and event.tool_name == "write_file":
        jb_components.update_status(component_id, "building")
    elif event.type == EventType.TEST_PASSED:
        jb_components.update_status(component_id, "built")
    elif event.type == EventType.ERROR:
        jb_components.update_status(component_id, "failed")
```

The frontend subscribes to `GET /api/events/stream?mission_id=X` and receives these events via SSE, using them to update graph node colors, the activity feed, and sidebar status text.

---

## 9. Error Recovery

### Test Failure Retry

The most common error during component building. The agent writes code, runs tests, tests fail. SaltAgent does not handle this at the harness level -- instead, the system prompt instructs the model to retry:

```
If tests fail:
1. Read the full error output.
2. Identify the root cause.
3. Fix the code (edit_file or write_file).
4. Re-run tests.
5. Repeat up to 3 times.
If tests still fail after 3 attempts, report what you tried and what failed.
```

The model naturally follows this pattern because it sees the test failure output in the conversation and wants to fix it. The 3-retry limit is enforced by the system prompt, not the harness. If the model exceeds 3 retries, it will typically stop and explain the issue (which becomes the task failure reason in JBCP).

### Import Error Recovery

When tests fail due to a missing dependency:

```
If you see an ImportError or ModuleNotFoundError:
1. Check if the dependency is in requirements.txt.
2. If not, add it to requirements.txt.
3. Run: pip install -r requirements.txt
4. Re-run tests.
```

### API Rate Limiting

Handled at the provider adapter level with exponential backoff:

```python
async def _backoff(self, retry_after: float | None):
    wait = retry_after or self._next_backoff()
    self.event_bus.emit(AgentEvent(
        type=EventType.PROGRESS,
        message=f"Rate limited. Waiting {wait:.0f}s..."
    ))
    await asyncio.sleep(wait)

def _next_backoff(self) -> float:
    """Exponential backoff: 1s, 2s, 4s, 8s, 16s, max 60s."""
    delay = min(2 ** self._retry_count, 60)
    self._retry_count += 1
    return delay
```

### Context Too Long

When the provider rejects the request because the prompt exceeds the context window:

1. Trigger emergency compaction (Layer 3 from section 6).
2. Re-read critical files from disk (post-compact restoration).
3. Retry the API call.
4. If it still fails after compaction, emit a fatal error.

### Timeout

Tool-level timeouts (bash commands, test runs) return error strings to the model. The model can adapt (e.g., increase timeout, simplify the test, skip a slow test).

Agent-level timeout (the entire `run()` call exceeds a wall-clock limit): save checkpoint, emit error event, allow JBCP to retry later via `resume()`.

### The "I'm Stuck" Pattern

If the model produces the same failing test output twice in a row, or if it edits the same file 5+ times without making progress, the system prompt includes:

```
If you find yourself stuck in a loop (same error repeating, same edit not working):
1. Step back and reconsider your approach.
2. Read the component specification again.
3. Try a fundamentally different implementation strategy.
4. If the specification is ambiguous, make a reasonable decision and document it
   in your DECISIONS section.
```

This is a behavioral instruction, not a harness mechanism. The model's self-correction is driven by seeing the pattern in its own conversation history.

---

## 10. Component Building Workflow

This is the specific workflow SaltAgent executes when building a Salt Desktop component. It is the primary use case and the one the system prompt is optimized for.

### Step-by-Step

**1. Receive task.**
JBCP dispatches a task with: component name, component type, contract specification (input/output schemas, config fields), mission context (goal, architecture, upstream/downstream components), and working directory path.

**2. Create component directory.**
```
components/{slug}/
```
The directory is created by JBCP before SaltAgent starts. SaltAgent writes files into it.

**3. Write `contract.py` first.**
Typed dataclasses defining `Config`, `Input`, and `Output`. This is the single source of truth for what the component accepts and produces.

```python
# components/gmail_connector/contract.py
from dataclasses import dataclass, field

@dataclass
class Config:
    credentials_json: str
    max_results: int = 50

@dataclass
class Input:
    pass  # No input -- this is a source connector

@dataclass
class Output:
    emails: list[dict]
    summary: str = ""
```

**4. Write `main.py` with the `run` function.**
Single entry point that accepts config, input data, and the summary chain.

```python
# components/gmail_connector/main.py
from contract import Config, Input, Output

def run(config: Config, input_data: Input = None, summary_chain: list[str] = None) -> dict:
    """Fetch emails from Gmail using the configured credentials."""
    if summary_chain is None:
        summary_chain = []

    # ... implementation ...

    result = Output(
        emails=fetched_emails,
        summary=f"Fetched {len(fetched_emails)} emails"
    )
    return {
        "data": result,
        "summary_chain": summary_chain + [result.summary],
    }
```

**5. Write `test_main.py` with unit tests.**

```python
# components/gmail_connector/test_main.py
import pytest
from contract import Config, Input
from main import run

def test_run_returns_output():
    config = Config(credentials_json='{"mock": true}', max_results=10)
    result = run(config)
    assert "data" in result
    assert "summary_chain" in result
    assert isinstance(result["summary_chain"], list)

def test_summary_chain_propagation():
    config = Config(credentials_json='{"mock": true}')
    result = run(config, summary_chain=["Previous step done"])
    assert len(result["summary_chain"]) == 2
    assert result["summary_chain"][0] == "Previous step done"
```

**6. Run tests.**
```
run_tests(path="test_main.py")
```

**7. If tests fail: fix and retry (up to 3 times).**
The model reads the error output, identifies the issue, edits the code, and re-runs tests. This is the most common loop in component building.

**8. Report decisions.**
After the component is complete, the model outputs a DECISIONS section:

```
DECISIONS:
- Used Gmail API v1 with oauth2client for authentication (most widely documented approach)
- Mocked the Gmail service in tests using unittest.mock.patch (avoids real API calls in tests)
- Set default max_results to 50 (reasonable for periodic checking, configurable via Config)
- Included full email headers in output (downstream components may need sender, subject, date)
```

These decisions are stored in the task result and displayed in the component slideout panel in the UI.

**9. Mark component as built.**
The agent emits `COMPLETE`. JBCP updates the component status to "built" and the graph node turns green.

### Building an LLM-Powered Component

Some components need LLM intelligence at runtime (email classifiers, content summarizers, intent parsers). SaltAgent handles these identically to any other component — it WRITES the code, including the LLM API call inside the `run()` function. There is no special "AI mode" or "live agent" concept.

**Example: SaltAgent builds an email classifier component:**

```python
# SaltAgent BUILDS this file: components/email_classifier/main.py
def run(config, input_data, summary_chain):
    from anthropic import Anthropic
    client = Anthropic(api_key=config.get("api_key"))
    
    emails = input_data["emails"]
    response = client.messages.create(
        model=config.get("model", "claude-sonnet-4-20250514"),
        messages=[{"role": "user", "content": f"Classify: {emails}"}]
    )
    classified = parse(response)
    return {"classified": classified, "summary": f"Classified {len(emails)} emails"}
```

The key insight: the LLM call is just another API call inside a `run()` function. Same as calling Gmail API or Slack API. The RunnerAgent executes this function in the pipeline without knowing or caring that it makes an LLM call internally. No agent loop at runtime. No tools at runtime. Just a Python function that happens to call an LLM.

---

### SaltAgent vs RunnerAgent

The system has exactly two engines. They never overlap.

| | SaltAgent | RunnerAgent |
|---|---|---|
| Purpose | Build components | Execute pipelines |
| When | Build phase ("Build It" clicked) | Run phase (deployed agent runs on schedule) |
| Has agent loop | Yes (LLM → tools → repeat) | No (just calls run() functions in order) |
| Has tools | Yes (read, write, edit, bash, grep, glob, run_tests) | No |
| Uses LLM | Yes (to write code) | No (but components CAN call LLMs in their run() functions) |
| Already built | No (this PRD) | Yes (jb_pipeline.py) |

**There is no "live agent" mode.** Everything deployed is a pipeline. If a pipeline node needs LLM intelligence, the component's `run()` function calls the API directly — it is just another function that happens to make an LLM call. No tools at runtime. No agent loop at runtime. Just Python functions chained together.

**The N8N model:** Everything is nodes in a pipeline. Some nodes call APIs. Some nodes call LLMs. Some just transform data. All are the same thing — `def run()` functions.

---

## 11. Multi-Agent / Parallel Building

SaltAgent instances run in parallel when ClawTeam coordinates the build phase. Each instance is independent -- separate process, separate conversation, separate context window -- but they share the mission context and dependency graph.

### How It Works

1. **JBCP analyzes the component graph** and identifies which components can be built in parallel (no dependency between them).

2. **ClawTeam creates a git worktree per component.** Each SaltAgent instance gets its own copy of the repository to write to, preventing file conflicts.

3. **Each SaltAgent instance runs independently:**
   ```python
   # Launched by JBCP orchestrator via ClawTeam
   agent = SaltAgent(config=AgentConfig(
       provider="anthropic",
       model="claude-sonnet-4-20250514",
       max_turns=30,
       tools=DEFAULT_COMPONENT_TOOLS,
       working_directory="/path/to/worktree/components/gmail_connector",
   ))

   async for event in agent.run(prompt=component_build_prompt):
       forward_to_jbcp_event_bus(event)
   ```

4. **Dependency-aware scheduling:** If component B depends on component A's output type, B is not dispatched until A completes. JBCP handles this via the task dependency graph (already implemented in `jb_queue.py`).

5. **Shared context, independent conversations:** All agents receive the same mission context (goal, architecture, credential list). But each agent's conversation is independent -- they do not see each other's tool calls or decisions.

6. **Merge after completion:** When all components in a worktree are built, ClawTeam merges the worktree branch back into the main branch.

### Wave-Based Execution

For a 5-component graph with dependencies:

```
Wave 1 (parallel):  Gmail Connector, Slack API Researcher
Wave 2 (parallel):  Email Filter, Content Summarizer    (depend on Wave 1)
Wave 3 (serial):    Notification Sender                  (depends on Wave 2)
```

Three SaltAgent instances run in Wave 1. When both complete, two more run in Wave 2. Then one in Wave 3. Total wall-clock time is dominated by the longest component in each wave, not the sum of all components.

### Resource Limits

- **Max concurrent agents:** Configurable, default 5. Bounded by API rate limits and system resources.
- **Each agent uses one API connection.** No connection pooling between agents.
- **Memory per agent:** Approximately 50-100 MB (conversation history + tool state). Five concurrent agents use 250-500 MB.

---

## 12. Security & Sandboxing

### Filesystem Boundaries

Every SaltAgent instance is restricted to its component working directory. The tool executor enforces path boundaries before every file operation:

```python
def validate_path(requested_path: str, working_dir: str, allowed_paths: list[str]) -> str:
    """Resolve and validate a path. Raises SecurityError if out of bounds."""
    resolved = Path(requested_path).resolve()

    # Must be within working directory or an explicitly allowed path
    allowed = [Path(working_dir).resolve()] + [Path(p).resolve() for p in allowed_paths]
    if not any(is_subpath(resolved, a) for a in allowed):
        raise SecurityError(f"Path {resolved} is outside allowed boundaries")

    return str(resolved)
```

**Allowed paths** (in addition to the component directory):
- The `components/` parent directory (for reading other components' contracts during dependency-aware builds).
- The project's `requirements.txt`.
- No access to: home directory, system files, other users' data, Salt Desktop application code.

### Bash Sandboxing

The `bash` tool applies multiple layers of restriction:

1. **Command blocklist:**
   ```python
   BLOCKED_COMMANDS = [
       "sudo", "su",
       "rm -rf /", "rm -rf /*",
       "shutdown", "reboot", "halt",
       "mkfs", "dd if=",
       "> /dev/", "chmod 777",
       "curl", "wget",  # Use credential-backed tools instead
       "ssh", "scp", "rsync",
   ]
   ```

2. **Timeout enforcement:** Default 120 seconds, maximum 600 seconds. Commands that exceed the timeout are killed with SIGTERM, then SIGKILL after 5 seconds.

3. **Working directory:** Always set to the component directory. The agent cannot `cd` to arbitrary locations (shell state does not persist between bash calls).

4. **Output truncation:** 30,000 character limit prevents memory exhaustion from runaway output.

5. **No background processes that outlive the agent.** Background bash is not supported in SaltAgent (unlike Claude Code). All commands are synchronous.

### Credential Access

- **Read-only.** The agent can check if credentials exist and read their values. It cannot create, modify, or delete credentials.
- **Scoped to the mission.** Only credentials that the user has explicitly linked to the mission are accessible.
- **Never in source code.** The system prompt instructs the agent to use `config.{field}` references. The tool executor does not enforce this (it cannot parse code intent), but the prompt is explicit about it.

### What the Agent CANNOT Do

- Access the network directly (no curl, wget, raw sockets).
- Read or write files outside the component directory and allowed paths.
- Execute commands as root.
- Install system packages (only pip install within the project virtualenv).
- Spawn persistent background processes.
- Access other users' data or Salt Desktop's internal state.

---

## 13. Persistence & Resume

### Checkpoint Before Every API Call

Before each LLM API call, SaltAgent saves a checkpoint containing:

```python
@dataclass
class Checkpoint:
    agent_id: str              # Unique agent instance identifier
    component_id: str          # Which component is being built
    turn: int                  # Current turn number
    messages: list[dict]       # Full conversation history
    files_read: set[str]       # Paths of files read (for edit enforcement)
    files_written: set[str]    # Paths of files written
    timestamp: str             # ISO 8601 UTC
```

Checkpoints are saved as JSON files to `data/saltagent_checkpoints/{agent_id}.json`.

### Resume on Crash

If the process crashes (or is killed), JBCP can resume the agent from the last checkpoint:

```python
agent = SaltAgent.resume(
    checkpoint_path="data/saltagent_checkpoints/{agent_id}.json",
    config=original_config,
)
async for event in agent.run():  # No prompt needed -- resumes from checkpoint
    forward_to_jbcp_event_bus(event)
```

On resume:
1. The checkpoint is loaded.
2. Any incomplete tool calls (tool_use blocks without corresponding tool_result) are sealed with an error result: `"Agent was interrupted. This tool call did not complete."`.
3. The agent loop continues from the last turn.

### Session Transcripts

The full conversation transcript is saved after the agent completes (or fails). Stored at `data/saltagent_transcripts/{agent_id}.jsonl`, one message per line. This enables:
- Debugging: review exactly what the agent did and why.
- Build logs: the user can view the transcript in a detail panel.
- Training data: transcripts of successful builds can inform future prompt improvements.

### Build Logs

A simplified, human-readable summary of the build is generated from the event stream:

```
[00:00] Started building Gmail Connector
[00:02] Wrote contract.py (Config, Input, Output dataclasses)
[00:05] Wrote main.py (Gmail API integration, 145 lines)
[00:08] Wrote test_main.py (3 tests)
[00:09] Running tests...
[00:11] 2 of 3 tests passed, 1 failed (test_empty_inbox: KeyError)
[00:14] Fixed main.py (handle empty response)
[00:15] Running tests...
[00:17] All 3 tests passed
[00:17] DECISIONS:
        - Used Gmail API v1 with oauth2client
        - Mocked Gmail service in tests
[00:17] Component built successfully
```

Stored at `data/saltagent_builds/{component_id}.log`. Accessible from the component slideout in the UI.

---

## 14. Configuration

All SaltAgent configuration is managed through a single `AgentConfig` dataclass. Users set these values through Salt Desktop's settings panel.

```python
@dataclass
class AgentConfig:
    # Provider
    provider: str = "anthropic"                 # "anthropic", "openai", "gemini"
    model: str = "claude-sonnet-4-20250514"     # Model identifier
    api_key: str = ""                           # Provider API key (from CredentialStore)

    # Generation
    max_tokens: int = 8192                      # Max output tokens per turn
    temperature: float = 0.0                    # Deterministic by default for code

    # Agent behavior
    max_turns: int = 30                         # Maximum turns per component build
    test_retry_limit: int = 3                   # Max test failure retries (prompt-enforced)

    # Tool permissions
    tools: list[str] = field(default_factory=lambda: DEFAULT_COMPONENT_TOOLS)
    bash_timeout: int = 120000                  # Bash command timeout (ms)
    bash_max_output: int = 30000                # Bash output truncation (chars)

    # Context management
    context_budget_threshold: float = 0.6       # Start file summarization at 60%
    context_compact_threshold: float = 0.8      # Start auto-compaction at 80%
    tool_result_max_chars: int = 10000          # Truncate tool results above this

    # Filesystem
    working_directory: str = ""                 # Component directory (set per invocation)
    allowed_paths: list[str] = field(default_factory=list)  # Additional readable paths

    # Persistence
    checkpoint_dir: str = "data/saltagent_checkpoints"
    transcript_dir: str = "data/saltagent_transcripts"
    build_log_dir: str = "data/saltagent_builds"

DEFAULT_COMPONENT_TOOLS = [
    "read_file", "write_file", "edit_file",
    "bash", "glob", "grep", "list_files",
    "check_credentials", "read_credentials",
    "run_tests", "report_build_progress",
]
```

### Settings Exposed to Users

| Setting | Default | Where |
|---------|---------|-------|
| Default model | Claude Sonnet | Settings > AI > Default Model |
| Per-mission model override | (inherit global) | Mission settings panel |
| Max build time per component | 30 turns | Settings > AI > Build Limits |
| Provider API keys | (user enters) | Settings > Credentials |

Advanced settings (hidden by default, available in developer mode):
- Temperature
- Max tokens
- Bash timeout
- Context pressure thresholds
- Tool permissions

---

## 15. API Surface

### Instantiation

```python
from salt_agent import SaltAgent, AgentConfig

config = AgentConfig(
    provider="anthropic",
    model="claude-sonnet-4-20250514",
    api_key=credential_store.get("anthropic_api_key"),
    working_directory="/path/to/components/gmail_connector",
    allowed_paths=["/path/to/components", "/path/to/requirements.txt"],
)

agent = SaltAgent(config=config)
```

### Running (Async Event Stream)

```python
async for event in agent.run(prompt=build_prompt):
    match event.type:
        case EventType.TOOL_START:
            update_graph_node(component_id, "building", event.tool_name)
        case EventType.FILE_WRITTEN:
            update_activity_feed(f"Writing {Path(event.path).name}")
        case EventType.TEST_PASSED:
            update_graph_node(component_id, "tested")
        case EventType.TEST_FAILED:
            update_activity_feed(f"Tests failed, retrying...")
        case EventType.COMPLETE:
            mark_component_built(component_id, event.result)
        case EventType.ERROR:
            mark_component_failed(component_id, event.error)
```

### Cancellation

```python
# From another coroutine or thread
agent.cancel()
# The agent saves a checkpoint and stops at the next yield point.
# A CANCELLED event is emitted.
```

### Resume

```python
agent = SaltAgent.resume(
    checkpoint_path="data/saltagent_checkpoints/abc123.json",
    config=config,  # Same config as the original run
)
async for event in agent.run():
    ...
```

### Running Multiple Agents

```python
import asyncio

async def build_component(component, mission_context):
    config = AgentConfig(
        working_directory=f"/worktrees/{component.slug}/components/{component.slug}",
        ...
    )
    agent = SaltAgent(config=config)
    async for event in agent.run(prompt=build_prompt_for(component, mission_context)):
        forward_to_jbcp(event, component.id)

# Build Wave 1 in parallel
await asyncio.gather(
    build_component(gmail_connector, mission),
    build_component(slack_researcher, mission),
)

# Build Wave 2 in parallel (depends on Wave 1)
await asyncio.gather(
    build_component(email_filter, mission),
    build_component(content_summarizer, mission),
)

# Build Wave 3 (depends on Wave 2)
await build_component(notification_sender, mission)
```

---

## 16. Implementation Phases

### Phase 1: MVP (1 week)

**Goal:** A working agent that can build a single component with passing tests.

**Deliverables:**
- `salt_agent/agent.py` -- Core `SaltAgent` class with the agent loop.
- `salt_agent/tools/` -- Tool implementations: `read_file`, `write_file`, `edit_file`, `bash`, `glob`, `grep`, `list_files`, `run_tests`, `report_build_progress`.
- `salt_agent/providers/anthropic.py` -- Anthropic adapter using the `anthropic` SDK.
- `salt_agent/events.py` -- `AgentEvent` and `EventType` definitions.
- `salt_agent/config.py` -- `AgentConfig` dataclass.
- Basic context assembly: system prompt with component spec and mission context.
- No compaction (context will not overflow for simple components).
- Event streaming to caller via `async for`.
- Read-before-edit enforcement.
- Path sandboxing on all file tools.
- Integration point: JBCP can instantiate and run a SaltAgent for a single task.

**Acceptance criteria:**
- Given a component spec for a Gmail Connector, the agent produces `contract.py`, `main.py`, and `test_main.py` with passing tests.
- Events stream to the caller in real-time.
- Build completes in under 5 minutes.

### Phase 2: Robust (1 week)

**Goal:** Multi-provider support, context management, and error recovery.

**Deliverables:**
- `salt_agent/providers/openai.py` -- OpenAI adapter.
- `salt_agent/providers/gemini.py` -- Gemini adapter.
- `salt_agent/context.py` -- Context pressure manager (Layers 1-2: tool result budgeting, file content summarization).
- `salt_agent/tools/credentials.py` -- `check_credentials` and `read_credentials` tools.
- Error recovery: rate limit backoff, context-too-long compaction, tool timeout handling.
- Read-before-edit tracking persisted across tool calls.
- Decision logging in the system prompt.
- Token estimation per provider.

**Acceptance criteria:**
- Agent builds components using OpenAI and Gemini models (not just Anthropic).
- A 25-turn build session with large file reads does not overflow the context window.
- Rate limit errors are retried with backoff.

### Phase 3: Production (1 week)

**Goal:** Full compaction, persistence, and parallel execution.

**Deliverables:**
- Full compaction stack (Layers 3-4: auto-compaction with post-compact restoration, turn compression).
- `salt_agent/persistence.py` -- Checkpoint save/load, transcript storage, build log generation.
- `SaltAgent.resume()` class method for crash recovery.
- `SaltAgent.cancel()` method for graceful cancellation.
- ClawTeam integration: JBCP orchestrator launches multiple SaltAgent instances in parallel worktrees.
- Bash command blocklist enforcement.
- Path boundary enforcement on all tools.
- Build log generation from event stream.

**Acceptance criteria:**
- An agent that crashes mid-build can be resumed from checkpoint and complete successfully.
- Five agents build five components in parallel via ClawTeam worktrees.
- No agent can read or write files outside its allowed paths.

### Phase 4: Advanced (Ongoing)

**Goal:** Optimization and advanced patterns.

**Deliverables (prioritized backlog):**
- **Verification specialist subagent.** After the main agent marks a component as built, a second agent (using a cheaper model) runs the tests independently and checks for edge cases. This catches the model's natural tendency to write tests that mirror the implementation rather than test it.
- **Streaming tool execution.** Start executing tools before the model finishes generating its response. When the model emits a complete `tool_use` block, schedule the tool immediately while the model continues generating the next block. Major latency reduction for multi-tool turns.
- **Prompt cache sharing between agents.** When multiple agents share the same system prompt prefix (mission context), use Anthropic's prompt caching to avoid re-encoding the shared prefix for each agent.
- **Adaptive model selection.** Use a cheaper/faster model (Haiku) for simple components (type: SCHEDULER, few config fields) and a stronger model (Opus) for complex components (type: AI, many dependencies).

---

## 17. Success Metrics

| Metric | Target | How Measured |
|--------|--------|-------------|
| Build a 3-file component | 100% of attempts produce contract.py, main.py, test_main.py | Automated test |
| Tests pass on first try | > 80% | Track across all builds |
| Average build time per component | < 3 minutes | Event timestamps |
| Max build time per component | < 10 minutes | Event timestamps |
| External binary dependencies | Zero | Package manifest |
| Provider support | Anthropic, OpenAI, Gemini | Integration tests |
| Context overflow rate | < 5% of builds | Monitor compaction events |
| Crash recovery | Resume succeeds > 95% | Automated resume test |
| Parallel build speedup | > 2x for 3+ component missions | Wall-clock comparison |

---

## 18. Risks & Mitigations

### Model Quality Variation Across Providers

**Risk:** GPT or Gemini may produce worse code than Claude for certain component types, leading to more test failures and longer build times.

**Mitigation:** Default to Claude Sonnet. Allow per-mission model override so users can switch if one provider works better for their use case. Track test-pass rates per provider to inform recommendations.

### API Rate Limits

**Risk:** Heavy usage (5 parallel agents, each making 30 API calls) hits provider rate limits, stalling builds.

**Mitigation:** Exponential backoff with jitter at the adapter level. JBCP queue management: limit concurrent agents to stay within rate limits. Spread agents across providers if the user has multiple API keys configured.

### Context Window Overflow

**Risk:** Complex components with many files and long test outputs exceed the context window, causing the agent to lose track of its work.

**Mitigation:** 4-layer context pressure management (section 6). Post-compaction restoration reinjects critical files. For very complex components, use a model with a larger context window (Claude with 200K, Gemini with 1M).

### Security: Bash Tool Exploitation

**Risk:** A model prompt-injected by malicious file content could use the bash tool to damage the system.

**Mitigation:** Command blocklist, path sandboxing, timeout enforcement, no sudo, no network access via bash. The working directory is isolated to the component directory. Bash output is truncated to prevent memory exhaustion.

### Credential Leakage

**Risk:** The model writes credential values directly into source code instead of using config references.

**Mitigation:** The system prompt explicitly forbids hardcoding credentials. Post-build validation: scan written files for credential patterns (API keys, tokens) and flag any matches in the build log. This is a warning, not a blocker -- the user decides whether to redact and rebuild.

### Model Hallucination in Contracts

**Risk:** The model writes a contract that does not match the specification, causing downstream components to fail.

**Mitigation:** The contract specification is in the system prompt with exact field names and types. Post-build validation: parse the generated `contract.py` and verify it matches the specification's schema. If it does not match, the component is marked as failed with a clear error.

---

## Appendix A: Dependencies

### Required

| Package | Version | Purpose |
|---------|---------|---------|
| `anthropic` | >= 0.40.0 | Anthropic Claude API |
| `openai` | >= 1.50.0 | OpenAI GPT API |
| `google-genai` | >= 1.0.0 | Google Gemini API |

### Standard Library (no install needed)

- `asyncio` -- async agent loop
- `subprocess` -- bash tool
- `pathlib` -- path operations
- `json` -- serialization
- `dataclasses` -- config, events, checkpoints
- `re` -- credential pattern scanning

### No Other Dependencies

SaltAgent intentionally has no framework dependencies. No LangChain, no LlamaIndex, no agent frameworks. The agent loop is ~100 lines. The tool executor is ~200 lines. The provider adapters are ~150 lines each. The total library is under 2,000 lines of Python.

---

## Appendix B: File Structure

```
salt_agent/
  __init__.py              # Public API: SaltAgent, AgentConfig, AgentEvent, EventType
  agent.py                 # Core SaltAgent class with agent loop
  config.py                # AgentConfig dataclass
  events.py                # AgentEvent, EventType
  context.py               # ContextAssembler, ContextPressureManager
  persistence.py           # Checkpoint, Transcript, BuildLog, Resume
  providers/
    __init__.py            # ProviderAdapter base class
    anthropic.py           # AnthropicAdapter
    openai.py              # OpenAIAdapter
    gemini.py              # GeminiAdapter
  tools/
    __init__.py            # ToolRegistry, Tool base class
    filesystem.py          # read_file, write_file, edit_file, list_files
    search.py              # glob, grep
    bash.py                # bash (sandboxed)
    credentials.py         # check_credentials, read_credentials
    testing.py             # run_tests
    progress.py            # report_build_progress
    sandbox.py             # Path validation, command blocklist
  tests/
    test_agent.py          # Agent loop tests (mock provider)
    test_tools.py          # Tool execution tests
    test_context.py        # Context pressure management tests
    test_providers.py      # Provider adapter tests (mock HTTP)
    test_sandbox.py        # Security boundary tests
    test_persistence.py    # Checkpoint/resume tests
```

---

## Appendix C: Glossary

| Term | Definition |
|------|-----------|
| **SaltAgent** | The Python library that executes the agent loop for building components. Build-phase only — never runs at deploy time. |
| **RunnerAgent** | The pipeline executor (`jb_pipeline.py`) that runs deployed agents by calling component `run()` functions in order. No agent loop, no tools, no LLM (though components may call LLMs internally). |
| **Agent loop** | The core cycle: call LLM, check for tools, execute tools, repeat. |
| **Component** | A Salt Desktop building block: `contract.py` + `main.py` + `test_main.py`. |
| **Contract** | Typed dataclass definitions for a component's Config, Input, and Output. |
| **Provider adapter** | Abstraction layer that normalizes differences between Anthropic, OpenAI, and Gemini APIs. |
| **Context pressure** | The set of strategies for keeping the conversation within the model's context window. |
| **Compaction** | Summarizing the conversation history to free context space. |
| **Checkpoint** | A snapshot of the agent's state saved before each API call for crash recovery. |
| **Wave** | A set of components that can be built in parallel (no dependencies between them). |
| **ClawTeam** | External multi-agent coordination framework that manages parallel SaltAgent instances in git worktrees. |
| **Summary chain** | The list of human-readable summaries passed forward through the component graph during pipeline execution. |
| **JBCP** | JB Command Processor -- the orchestration backend that dispatches tasks to SaltAgent. |
