"""
Context compaction -- summarize old conversation turns when the context window fills up.
Based on Claude Code's compaction approach, simplified to the essential layers.
"""

from __future__ import annotations

from salt_agent.config import AgentConfig


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token."""
    return len(text) // 4


def estimate_messages_tokens(messages: list[dict]) -> int:
    """Estimate total tokens in a message list."""
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += estimate_tokens(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    total += estimate_tokens(
                        str(
                            block.get("content", "")
                            or block.get("text", "")
                            or block.get("input", "")
                        )
                    )
                elif isinstance(block, str):
                    total += estimate_tokens(block)
    return total


def needs_compaction(messages: list[dict], config: AgentConfig) -> bool:
    """Check if context is approaching the limit."""
    estimated = estimate_messages_tokens(messages)
    threshold = int(config.context_window * 0.80)  # 80% of context window
    return estimated > threshold


async def compact_context(
    messages: list[dict],
    system_prompt: str,
    config: AgentConfig,
    provider,  # the provider adapter to use for summarization
    todo_state: str = "",
    files_read: set[str] | None = None,
) -> list[dict]:
    """
    Compact the conversation by summarizing old turns.

    Keeps:
    - The last user message (current task)
    - The todo state
    - Recently read files list

    Returns a new messages list with a summary replacing old turns.
    """
    if len(messages) < 4:
        return messages  # too few to compact

    # Keep the last 2 messages (current exchange)
    keep_messages = messages[-2:]
    old_messages = messages[:-2]

    # Build the summarization prompt
    from salt_agent.prompts import get_mode_prompt

    summarization_prompt = get_mode_prompt("summarize")

    # Format old messages for summarization
    conversation_text = ""
    for msg in old_messages:
        role = msg.get("role", "?")
        content = msg.get("content", "")
        if isinstance(content, str):
            conversation_text += f"[{role}]: {content[:500]}\n"
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        conversation_text += f"[{role}]: {block['text'][:300]}\n"
                    elif block.get("type") == "tool_use":
                        conversation_text += (
                            f"[tool_call]: {block['name']}"
                            f"({str(block.get('input', ''))[:200]})\n"
                        )
                    elif block.get("type") == "tool_result":
                        conversation_text += (
                            f"[tool_result]: {str(block.get('content', ''))[:200]}\n"
                        )

    # Call the LLM to summarize
    files_read_set = files_read or set()
    summary_prompt = f"""{summarization_prompt}

## Conversation to summarize:
{conversation_text[:10000]}

## Current state to preserve:
- Working directory context
- Files modified/read so far
{f'- {todo_state}' if todo_state else ''}
{f'- Files read: {", ".join(list(files_read_set)[:10])}' if files_read_set else ''}

Produce a concise summary that captures all essential context, decisions made, and current state.
"""

    summary_text = ""
    from salt_agent.events import TextChunk

    async for event in provider.stream_response(
        system="You are a context summarizer. Produce a concise summary.",
        messages=[{"role": "user", "content": summary_prompt}],
        tools=[],  # no tools for summarization
        max_tokens=2000,
    ):
        if isinstance(event, TextChunk):
            summary_text += event.text

    if not summary_text:
        # Fallback: just truncate old messages
        return messages[-6:]

    # Build compacted message list
    compacted = [
        {
            "role": "user",
            "content": (
                "[Context Summary - Previous conversation was compacted]\n\n"
                + summary_text
            ),
        },
        {
            "role": "assistant",
            "content": (
                "Understood. I have the context from the previous conversation. "
                "Continuing with the current task."
            ),
        },
    ]
    compacted.extend(keep_messages)

    return compacted
