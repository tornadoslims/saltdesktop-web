"""
Context compaction -- summarize old conversation turns when the context window fills up.
Based on Claude Code's compaction approach, simplified to the essential layers.
"""

from __future__ import annotations

import re
from pathlib import Path

from salt_agent.config import AgentConfig


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token."""
    return len(text) // 4


# ---------------------------------------------------------------------------
# Microcompaction -- truncate old tool results to save tokens
# ---------------------------------------------------------------------------

def microcompact_tool_results(
    messages: list[dict],
    max_result_chars: int = 5000,
    recent_keep: int = 6,
) -> list[dict]:
    """Truncate old tool results to save tokens.

    Recent tool results (last ``recent_keep`` messages) are kept in full.
    Older results are truncated to keep the first and last portions.
    """
    cutoff = max(0, len(messages) - recent_keep)

    for i in range(cutoff):
        msg = messages[i]
        content = msg.get("content", "")
        if isinstance(content, list):
            for j, block in enumerate(content):
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    result_text = block.get("content", "")
                    if isinstance(result_text, str) and len(result_text) > max_result_chars:
                        truncated = (
                            result_text[:2000]
                            + "\n\n[...truncated...]\n\n"
                            + result_text[-1000:]
                        )
                        messages[i]["content"][j] = dict(block)
                        messages[i]["content"][j]["content"] = truncated

    return messages


class CompactionCache:
    """Cache microcompact results to avoid reprocessing already-compacted messages."""

    def __init__(self) -> None:
        self._compacted_indices: set[int] = set()  # message indices already compacted

    def microcompact_with_cache(
        self,
        messages: list[dict],
        max_result_chars: int = 5000,
        recent_keep: int = 6,
    ) -> list[dict]:
        """Only process messages not already compacted.

        Skips indices that were already truncated in a prior call, avoiding
        redundant string slicing on every turn.
        """
        cutoff = max(0, len(messages) - recent_keep)

        for i in range(cutoff):
            if i in self._compacted_indices:
                continue  # already compacted

            msg = messages[i]
            content = msg.get("content", "")
            did_work = False
            if isinstance(content, list):
                for j, block in enumerate(content):
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        result_text = block.get("content", "")
                        if isinstance(result_text, str) and len(result_text) > max_result_chars:
                            truncated = (
                                result_text[:2000]
                                + "\n\n[...truncated...]\n\n"
                                + result_text[-1000:]
                            )
                            messages[i]["content"][j] = dict(block)
                            messages[i]["content"][j]["content"] = truncated
                            did_work = True

            self._compacted_indices.add(i)

        return messages

    def invalidate(self) -> None:
        """Clear cache (call after full compaction changes message indices)."""
        self._compacted_indices.clear()


# ---------------------------------------------------------------------------
# History snip -- snip old assistant text responses at 60% capacity
# ---------------------------------------------------------------------------


def history_snip(messages: list[dict], context_window: int) -> list[dict]:
    """Snip old assistant text to summaries. Fires at 60% context capacity."""
    estimated = estimate_messages_tokens(messages)
    threshold = int(context_window * 0.60)

    if estimated < threshold:
        return messages  # Not needed yet

    # Only snip messages in the first half
    midpoint = len(messages) // 2

    for i in range(midpoint):
        msg = messages[i]
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", "")
        if isinstance(content, str) and len(content) > 300:
            messages[i] = dict(msg)
            messages[i]["content"] = content[:200] + "\n\n[...snipped for context]"
        elif isinstance(content, list):
            # Snip text blocks, keep tool_use blocks
            new_content = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text", "")
                    if len(text) > 300:
                        new_content.append({"type": "text", "text": text[:200] + "\n\n[...snipped]"})
                    else:
                        new_content.append(block)
                else:
                    new_content.append(block)  # keep tool_use blocks
            messages[i] = dict(msg)
            messages[i]["content"] = new_content

    return messages


# ---------------------------------------------------------------------------
# Context collapse -- collapse old tool call pairs at 70% capacity
# ---------------------------------------------------------------------------


def context_collapse(messages: list[dict], context_window: int) -> list[dict]:
    """Collapse old tool call pairs into summaries. Fires at 70%."""
    estimated = estimate_messages_tokens(messages)
    threshold = int(context_window * 0.70)

    if estimated < threshold:
        return messages

    # Find tool call/result pairs in the first half and collapse them
    midpoint = len(messages) // 2
    collapsed: list[dict] = []
    i = 0
    while i < len(messages):
        if i >= midpoint:
            collapsed.append(messages[i])
            i += 1
            continue

        msg = messages[i]
        content = msg.get("content", "")

        # Check if this is an assistant message with tool_use blocks
        if msg.get("role") == "assistant" and isinstance(content, list):
            tool_names = [
                b.get("name", "")
                for b in content
                if isinstance(b, dict) and b.get("type") == "tool_use"
            ]
            if tool_names and i + 1 < len(messages):
                # Next message should be tool results
                summary = f"[Tool calls: {', '.join(tool_names)}]"
                collapsed.append({"role": "assistant", "content": summary})
                i += 2  # Skip both messages
                continue

        collapsed.append(msg)
        i += 1

    return collapsed


# ---------------------------------------------------------------------------
# Emergency truncation -- last resort when compaction isn't enough
# ---------------------------------------------------------------------------

def emergency_truncate(messages: list[dict], target_tokens: int) -> list[dict]:
    """Last resort: drop old messages until under target tokens.

    Used when compaction fails or returns something too large.
    Keeps system messages and the most recent messages.
    """
    while estimate_messages_tokens(messages) > target_tokens and len(messages) > 2:
        # Remove the oldest non-system message
        for i, msg in enumerate(messages):
            if msg.get("role") != "system":
                messages.pop(i)
                break
        else:
            break  # only system messages left
    return messages


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


def _restore_post_compact(
    messages: list[dict],
    files_read: set[str] | None,
) -> list[dict]:
    """Reinject recently-read files after compaction.

    Restores up to 5 recently-read files (max 50K token budget total) so the
    agent doesn't lose awareness of files it was actively working on.
    """
    if not files_read:
        return messages

    TOKEN_BUDGET = 50_000
    MAX_FILE_CHARS = 10_000
    used = 0
    restorations: list[str] = []

    # Get the 5 most recently added files (sets are unordered, so list and take last 5)
    recent = list(files_read)[-5:]
    for path in recent:
        try:
            content = Path(path).read_text()[:MAX_FILE_CHARS]
            tokens = len(content) // 4
            if used + tokens > TOKEN_BUDGET:
                break
            restorations.append(f"[File restored post-compaction: {path}]\n{content}")
            used += tokens
        except Exception:
            pass

    if restorations:
        restoration_msg = {
            "role": "user",
            "content": (
                "[Post-compaction file restoration]\n\n"
                + "\n\n---\n\n".join(restorations)
            ),
        }
        # Insert before the last 2 messages (the current exchange)
        if len(messages) >= 3:
            messages.insert(-2, restoration_msg)
        else:
            messages.insert(0, restoration_msg)

    return messages


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

    # Format old messages for summarization -- pass full content (up to 10K per message)
    conversation_text = ""
    for msg in old_messages:
        role = msg.get("role", "?")
        content = msg.get("content", "")
        if isinstance(content, str):
            conversation_text += f"[{role}]: {content[:10000]}\n"
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        conversation_text += f"[{role}]: {block['text'][:10000]}\n"
                    elif block.get("type") == "tool_use":
                        conversation_text += (
                            f"[tool_call]: {block['name']}"
                            f"({str(block.get('input', ''))[:2000]})\n"
                        )
                    elif block.get("type") == "tool_result":
                        conversation_text += (
                            f"[tool_result]: {str(block.get('content', ''))[:2000]}\n"
                        )

    # Call the LLM to summarize
    files_read_set = files_read or set()
    summary_prompt = f"""{summarization_prompt}

## Conversation to summarize:
{conversation_text[:80000]}

## Current state to preserve:
- Working directory context
- Files modified/read so far
{f'- {todo_state}' if todo_state else ''}
{f'- Files read: {", ".join(list(files_read_set)[:10])}' if files_read_set else ''}

First, write your analysis inside <analysis> tags, examining the conversation chronologically. Then produce the final summary outside the tags.

CRITICAL: Do NOT call any tools. Only produce text output.
"""

    summary_text = ""
    from salt_agent.events import TextChunk

    async for event in provider.stream_response(
        system=(
            "You are a context summarizer. Produce a detailed summary that preserves "
            "all essential context. CRITICAL: Do NOT call any tools. Only produce text output."
        ),
        messages=[{"role": "user", "content": summary_prompt}],
        tools=[],  # no tools for summarization
        max_tokens=20000,
    ):
        if isinstance(event, TextChunk):
            summary_text += event.text

    if not summary_text:
        # Fallback: just truncate old messages
        return messages[-6:]

    # Strip <analysis> scratchpad block from the summary (keep only the actual summary)
    summary_text = re.sub(
        r"<analysis>.*?</analysis>",
        "",
        summary_text,
        flags=re.DOTALL,
    ).strip()

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

    # Fix 3: Post-compact file restoration
    compacted = _restore_post_compact(compacted, files_read)

    return compacted
