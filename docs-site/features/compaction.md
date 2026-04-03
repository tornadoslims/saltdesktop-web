# Context Compaction

SaltAgent uses a 5-layer compaction pipeline to manage context window pressure. As the conversation grows, each layer fires at increasing thresholds to keep the context within the model's window.

## The 5 Layers

### Layer 1: Microcompaction (every turn)

Truncates old tool results to save tokens. Recent results (last 6 messages) are kept in full; older results are trimmed to 3,000 characters (first 2,000 + last 1,000).

A `CompactionCache` avoids reprocessing messages that have already been microcompacted. The cache is invalidated when full compaction changes message indices.

**Trigger:** Every turn, applied to all messages except the most recent 6.

### Layer 2: History Snip (60% capacity)

Snips old assistant text responses in the first half of the conversation. Long text blocks (>300 chars) are trimmed to 200 characters with a `[...snipped for context]` marker.

Tool use blocks within assistant messages are preserved -- only text content is trimmed.

**Trigger:** Estimated tokens exceed 60% of `context_window`.

### Layer 3: Context Collapse (70% capacity)

Collapses old tool call/result pairs into compact summaries. An assistant message with tool calls followed by a tool result message becomes a single `[Tool calls: read, grep]` summary.

Only applied to the first half of the conversation to preserve recent context.

**Trigger:** Estimated tokens exceed 70% of `context_window`.

### Layer 4: Autocompact / LLM Summarization (80% capacity)

Uses the LLM itself to produce a condensed summary of old conversation. The summary preserves:

- Key decisions and outcomes
- File paths read or modified
- Active todo state
- Important error messages and their resolutions

**Trigger:** `needs_compaction()` returns True (estimated tokens > 80% of context window).

### Layer 5: Emergency Truncation (95% capacity)

Last resort when even LLM compaction produces something too large. Drops old messages from the beginning until under 70% capacity, keeping system messages and the most recent messages.

**Trigger:** After Layer 4, if tokens still exceed 95% of context window.

## Token Estimation

Token counts are estimated at ~4 characters per token. This is a rough approximation used for threshold checks, not for billing.

```python
def estimate_tokens(text: str) -> int:
    return len(text) // 4
```

## Events

| Event | When |
|-------|------|
| `on_compaction` / `context_compacted` | Layer 4 fires (LLM summarization) |
| `context_emergency` | Layer 5 fires (emergency truncation) |

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `context_window` | 200,000 | Model's context window size |
| `max_tool_result_chars` | 10,000 | Max per-tool-result truncation |

## How Claude Code Does It

Claude Code uses a similar layered approach (compaction.ts). SaltAgent's implementation mirrors the same thresholds and strategies:

- Microcompaction = Claude Code's tool result truncation
- History snip = Claude Code's old turn summarization
- Context collapse = Claude Code's tool pair folding
- Autocompact = Claude Code's LLM-based compaction
- Emergency truncation = Claude Code's fallback drop strategy
