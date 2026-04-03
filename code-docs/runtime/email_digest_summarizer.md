# runtime/email_digest_summarizer.py

**Path:** `runtime/email_digest_summarizer.py`
**Purpose:** Email summarizer for the digest bot. Categorizes and summarizes emails using Claude CLI.

## Constants

- `CATEGORIES`: `["action_items", "newsletters", "fyi"]`
- `SYSTEM_PROMPT`: Instructions for the LLM to categorize emails into three groups

## Functions

### `summarize_emails(emails, config) -> DigestSummary`
Calls the Claude CLI (`claude --print`) with a structured prompt to produce JSON-formatted categories.

**Config fields:** `model` (default "claude-sonnet-4-5"), `max_tokens` (default 1024), `digest_style` (default "grouped")

**Returns:** `{categories: [{name, items: [{from, subject, summary}]}], total_emails, generated_at}`

### `_build_prompt(emails, digest_style) -> str`
Constructs the prompt listing all emails with sender, subject, and truncated body (300 chars max).
